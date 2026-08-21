import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, GraphDefinitionError, node, OptionValidationError, RunError } from '../caskada'

import type { Context, Failure, RunHandle, RunOptions } from '../caskada'

type State = { [key: string]: unknown }

function deferred(): { readonly promise: Promise<void>; readonly resolve: () => void } {
  let resolve!: () => void
  const promise = new Promise<void>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

describe('v3 deadlines, attempt timeouts, and abandonment', () => {
  it('captures run options and preserves an explicit run id', async () => {
    const reads: string[] = []
    const source = Object.create(null) as Record<string, unknown>
    for (const [key, value] of [
      ['deadlineMs', undefined],
      ['cancelGraceMs', 0],
      ['runId', 'timer-run'],
    ] as const) {
      Object.defineProperty(source, key, {
        enumerable: true,
        get() {
          reads.push(key)
          return value
        },
      })
    }
    const seen: string[] = []
    const result = await new Flow(
      node<State>((context) => {
        seen.push(context.runId)
      }),
    ).start({}, source as RunOptions).result

    assert.equal(result.status, 'completed')
    assert.deepEqual(seen, ['timer-run'])
    assert.deepEqual(reads, ['deadlineMs', 'cancelGraceMs', 'runId'])
    assert.throws(() => new Flow(node<State>(() => undefined)).start({}, { deadlineMs: -1 }), OptionValidationError)
    assert.throws(() => new Flow(node<State>(() => undefined)).start({}, { cancelGraceMs: true } as never), OptionValidationError)
    assert.throws(() => new Flow(node<State>(() => undefined)).start({}, { maxActivations: 4_294_967_295 }), OptionValidationError)
  })

  it('lets a zero run deadline win before callback invocation', async () => {
    let called = false
    const result = await new Flow(
      node<State>(() => {
        called = true
      }),
    ).start({}, { deadlineMs: 0, cancelGraceMs: 0 }).result

    assert.equal(result.status, 'cancelled')
    if (result.status !== 'cancelled') throw new Error('zero deadline must cancel')
    assert.equal(called, false)
    assert.equal(result.cancellation.reason, 'deadline_exceeded')
    assert.equal(result.cancellation.deadline, true)
    assert.equal(result.stats.attempts, 0)
  })

  it('signals cooperative work and settles a deadline as cancellation', async () => {
    const worker = node<State>(async (context) => {
      await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
      context.cancellation.throwIfCancelled()
    })
    const result = await new Flow(worker).start({}, { deadlineMs: 5, cancelGraceMs: 100 }).result

    assert.equal(result.status, 'cancelled')
    if (result.status !== 'cancelled') throw new Error('deadline must control')
    assert.equal(result.cancellation.deadline, true)
    assert.deepEqual(result.suppressed, [])
  })

  it('abandons caller-cancelled work after grace and closes late control', async () => {
    const started = deferred()
    const release = deferred()
    const lateControlClosed = deferred()
    const worker = node<State>(async (context) => {
      started.resolve()
      await release.promise
      assert.throws(() => context.end('late'))
      lateControlClosed.resolve()
    })
    const handle = new Flow(worker).start({}, { cancelGraceMs: 0 })
    await started.promise
    handle.cancel('shutdown')
    const result = await handle.result

    assert.equal(result.status, 'abandoned')
    if (result.status !== 'abandoned') throw new Error('uncooperative callback must abandon')
    assert.equal('deadline' in result.cause, true)
    if ('deadline' in result.cause) assert.equal(result.cause.reason, 'shutdown')
    assert.deepEqual(result.terminals, [])
    release.resolve()
    await lateControlClosed.promise
  })

  it('lets zero grace win when a callback returns after self-cancellation', async () => {
    let handle!: RunHandle<State>
    const worker = node<State>(() => {
      handle.cancel('self')
    })
    handle = new Flow(worker).start({}, { cancelGraceMs: 0 })
    const result = await handle.result

    assert.equal(result.status, 'abandoned')
    if (result.status !== 'abandoned') throw new Error('zero grace must win equality')
    assert.equal('deadline' in result.cause, true)
    if ('deadline' in result.cause) assert.equal(result.cause.reason, 'self')
  })

  it('abandons uncooperative work at the run deadline', async () => {
    const release = deferred()
    const worker = node<State>(async () => {
      await release.promise
    })
    const result = await new Flow(worker).start({}, { deadlineMs: 5, cancelGraceMs: 0 }).result

    assert.equal(result.status, 'abandoned')
    if (result.status !== 'abandoned') throw new Error('deadline must abandon')
    assert.equal('deadline' in result.cause, true)
    if ('deadline' in result.cause) assert.equal(result.cause.deadline, true)
    release.resolve()
    await Promise.resolve()
  })

  it('requires a positive Node timeout', () => {
    assert.throws(() => node<State>(() => undefined, { timeoutMs: 0 }), GraphDefinitionError)
  })

  it('enters recovery after an attempt timeout with a fresh token', async () => {
    const recovered: Failure[] = []
    const worker = node<State>(
      async (context) => {
        await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
        context.cancellation.throwIfCancelled()
      },
      {
        timeoutMs: 5,
        recover(context, failure) {
          recovered.push(failure)
          assert.equal(context.cancellation.cancelled, false)
          context.end('recovered')
        },
      },
    )
    const result = await new Flow(worker).start({}, { cancelGraceMs: 100 }).result

    assert.equal(result.status, 'completed')
    assert.equal(recovered[0]!.kind, 'handler_timeout')
    assert.equal(result.terminals[0]!.output, 'recovered')
  })

  it('settles a timed-out attempt before retrying it', async () => {
    let live = 0
    let peak = 0
    const worker = node<State>(
      async (context) => {
        live += 1
        peak = Math.max(peak, live)
        if (context.attempt === 1) {
          await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
          live -= 1
          context.cancellation.throwIfCancelled()
        }
        live -= 1
        context.end('second')
      },
      { timeoutMs: 5, retry: { maxAttempts: 2 } },
    )
    const result = await new Flow(worker).start({}, { cancelGraceMs: 100 }).result

    assert.equal(result.status, 'completed')
    assert.equal(peak, 1)
    assert.equal(result.stats.attempts, 2)
    assert.equal(result.stats.retries, 1)
  })

  it('abandons an uncooperative timed-out attempt', async () => {
    const release = deferred()
    const worker = node<State>(async () => release.promise, { timeoutMs: 5 })
    const result = await new Flow(worker).start({}, { cancelGraceMs: 0 }).result

    assert.equal(result.status, 'abandoned')
    if (result.status !== 'abandoned') throw new Error('attempt timeout must abandon')
    assert.equal('kind' in result.cause, true)
    if ('kind' in result.cause) assert.equal(result.cause.kind, 'handler_timeout')
    release.resolve()
    await Promise.resolve()
  })

  it('keeps a post-timeout error suppressed behind the timeout primary', async () => {
    const cause = new Error('after timeout')
    const worker = node<State>(
      async (context) => {
        await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
        throw cause
      },
      { timeoutMs: 5 },
    )
    const result = await new Flow(worker).start({}, { cancelGraceMs: 100 }).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('timeout must remain primary')
    assert.equal(result.failure.kind, 'handler_timeout')
    assert.equal(result.suppressed.length, 1)
    assert.equal(result.suppressed[0]!.kind, 'handler')
    assert.equal(result.suppressed[0]!.cause, cause)
    assert.equal(result.suppressed[0]!.previous, result.failure)
  })

  it('reports the attempt deadline and then its grace remainder', async () => {
    const seen: Array<number | undefined> = []
    const worker = node<State>(
      async (context) => {
        seen.push(context.remainingMs())
        await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
        seen.push(context.remainingMs())
        context.cancellation.throwIfCancelled()
      },
      { timeoutMs: 20 },
    )
    const result = await new Flow(worker).start({}, { deadlineMs: 1_000, cancelGraceMs: 100 }).result

    assert.equal(result.status, 'failed')
    assert(seen[0] !== undefined && seen[0] <= 20)
    assert(seen[1] !== undefined && seen[1] <= 100)
  })

  it('gives a zero run deadline priority over an attempt timeout', async () => {
    let called = false
    const worker = node<State>(
      () => {
        called = true
      },
      { timeoutMs: 1 },
    )
    const result = await new Flow(worker).start({}, { deadlineMs: 0, cancelGraceMs: 0 }).result

    assert.equal(result.status, 'cancelled')
    assert.equal(called, false)
    if (result.status !== 'cancelled') throw new Error('run deadline must win')
    assert.equal(result.cancellation.deadline, true)
    assert.deepEqual(result.suppressed, [])
  })

  it('makes run project the exact abandoned result through RunError', async () => {
    const worker = node<State>(async () => new Promise<void>(() => undefined))

    await assert.rejects(
      () => new Flow(worker).run({}, { deadlineMs: 5, cancelGraceMs: 0 }),
      (error) => error instanceof RunError && error.message === 'Caskada run abandoned' && error.result.status === 'abandoned',
    )
  })
})
