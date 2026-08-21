import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { Cancellation, Context, Failure, RunHandle, ScopeFailure } from '../caskada'

type State = { [key: string]: unknown }

function deferred(): { readonly promise: Promise<void>; readonly resolve: () => void } {
  let resolve!: () => void
  const promise = new Promise<void>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

describe('v3 cooperative cancellation', () => {
  it('skips application code when cancelled before admission', async () => {
    let called = false
    const handle = new Flow(
      node<State>(() => {
        called = true
      }),
    ).start({})

    handle.cancel()
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    if (result.status !== 'cancelled') throw new Error('caller cancellation must cancel')
    assert.equal(called, false)
    assert.equal(result.cancellation.reason, 'cancelled')
    assert.equal(result.cancellation.deadline, false)
    assert.deepEqual(result.terminals, [])
    assert.deepEqual(result.suppressed, [])
    assert.equal(result.stats.attempts, 0)
  })

  it('keeps the first reason and ignores later or post-settlement cancellation', async () => {
    const firstReason = { first: true }
    const handle = new Flow(node<State>(() => undefined)).start({})
    handle.cancel(firstReason)
    handle.cancel('later')
    const result = await handle.result
    handle.cancel('after settlement')

    assert.equal(handle.done, true)
    assert.equal(result.status, 'cancelled')
    if (result.status !== 'cancelled') throw new Error('caller cancellation must cancel')
    assert.equal(result.cancellation.reason, firstReason)
  })

  it('exposes callback metadata and a durable cooperative token', async () => {
    const started = deferred()
    const retained: Cancellation[] = []
    const observed: Record<string, unknown> = {}

    const worker = node<State>(async (context) => {
      retained.push(context.cancellation)
      Object.assign(observed, {
        runId: context.runId,
        scopeId: context.scopeId,
        activationId: context.activationId,
        parentActivationId: context.parentActivationId,
        attempt: context.attempt,
        phase: context.phase,
        remaining: context.remainingMs(),
        cancelled: context.cancellation.cancelled,
        reason: context.cancellation.reason,
      })
      started.resolve()
      await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
      context.cancellation.throwIfCancelled()
    })
    const handle = new Flow(worker).start({})
    await started.promise
    const reason = { shutdown: true }
    handle.cancel(reason)
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.match(String(observed.runId), /^run-[1-9][0-9]*$/)
    assert.deepEqual(observed, {
      runId: observed.runId,
      scopeId: 1,
      activationId: 2,
      parentActivationId: 1,
      attempt: 1,
      phase: 'handle',
      remaining: undefined,
      cancelled: false,
      reason: undefined,
    })
    assert.equal(retained[0]!.cancelled, true)
    assert.equal(retained[0]!.reason, reason)
    assert.throws(
      () => retained[0]!.throwIfCancelled(),
      (error) => error === reason,
    )
  })

  it('discards a callback buffer returned after the signal', async () => {
    const started = deferred()
    const worker = node<State>(async (context) => {
      context.end('must-not-commit')
      started.resolve()
      await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
    })
    const handle = new Flow(worker).start({})
    await started.promise
    handle.cancel('stop')
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.deepEqual(result.terminals, [])
    assert.equal(result.stats.transitions, 0)
  })

  it('records an unrelated post-signal error as suppression', async () => {
    const started = deferred()
    const cause = new Error('after signal')
    const worker = node<State>(async (context) => {
      started.resolve()
      await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
      throw cause
    })
    const handle = new Flow(worker).start({})
    await started.promise
    handle.cancel()
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    if (result.status !== 'cancelled') throw new Error('caller cancellation must remain controlling')
    assert.equal(result.suppressed.length, 1)
    assert.equal(result.suppressed[0]!.kind, 'handler')
    assert.equal(result.suppressed[0]!.cause, cause)
    assert.equal(result.suppressed[0]!.attempt, 1)
  })

  it('keeps prior terminals and discards later ready work', async () => {
    const waiting = deferred()
    const dispatch = node<State>((context) => {
      context.emit('done', 1)
      context.emit('wait', 2)
      context.emit('late', 3)
    })
    dispatch.link(
      node<State, number>((context) => context.end(context.input)),
      'done',
    )
    dispatch.link(
      node<State, number>(async (context) => {
        waiting.resolve()
        await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
      }),
      'wait',
    )
    dispatch.link(
      node<State, number>((context) => {
        context.state.late = context.input
      }),
      'late',
    )
    const handle = new Flow(dispatch).start({})
    await waiting.promise
    handle.cancel()
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.equal(result.terminals.length, 1)
    assert.equal(result.terminals[0]!.output, 1)
    assert.equal('late' in result.state, false)
  })

  it('wakes a retry delay and retains the handler packet', async () => {
    const scheduled = deferred()
    const worker = node<State>(
      () => {
        throw new Error('retry')
      },
      {
        retry: {
          maxAttempts: 2,
          delayMs(_attempt, _failure) {
            scheduled.resolve()
            return 4_294_967_295
          },
        },
      },
    )
    const handle = new Flow(worker).start({})
    await scheduled.promise
    handle.cancel()
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    if (result.status !== 'cancelled') throw new Error('retry cancellation must cancel')
    assert.equal(result.suppressed.length, 1)
    assert.equal(result.suppressed[0]!.kind, 'handler')
    assert.equal(result.stats.attempts, 1)
    assert.equal(result.stats.retries, 1)
  })

  it('retains active packets in Node and Flow recovery', async () => {
    for (const layer of ['node', 'flow'] as const) {
      const started = deferred()
      const fail = (): void => {
        throw new Error('handler')
      }
      const nodeRecovery = async (context: Context<State>, _failure: Failure): Promise<void> => {
        started.resolve()
        await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
        context.cancellation.throwIfCancelled()
      }
      const flowRecovery = async (context: Context<State>, _failure: ScopeFailure): Promise<void> => {
        started.resolve()
        await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
        context.cancellation.throwIfCancelled()
      }
      const entry = layer === 'node' ? node<State>(fail, { recover: nodeRecovery }) : node<State>(fail)
      const flow = layer === 'node' ? new Flow(entry) : new Flow(entry, { recover: flowRecovery })

      const handle = flow.start({})
      await started.promise
      handle.cancel()
      const result = await handle.result

      assert.equal(result.status, 'cancelled')
      if (result.status !== 'cancelled') throw new Error('recovery cancellation must cancel')
      assert.equal(result.suppressed.length, 1)
      assert.equal(result.suppressed[0]!.kind, 'handler')
    }
  })

  it('treats an unsignalled AbortError as an ordinary failure', async () => {
    const cause = new DOMException('not correlated', 'AbortError')
    const result = await new Flow(
      node<State>(() => {
        throw cause
      }),
    ).start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('unsignalled AbortError must fail')
    assert.equal(result.failure.kind, 'handler')
    assert.equal(result.failure.cause, cause)
  })

  it('uses exact signal identity for a cooperative abort', async () => {
    let handle!: RunHandle<State>
    const reason = { correlated: true }
    const worker = node<State>((context) => {
      handle.cancel(reason)
      context.cancellation.throwIfCancelled()
    })
    handle = new Flow(worker).start({})
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    if (result.status !== 'cancelled') throw new Error('correlated abort must cancel')
    assert.equal(result.cancellation.reason, reason)
    assert.deepEqual(result.suppressed, [])
  })
})
