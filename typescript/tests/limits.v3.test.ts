import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { Context, FailedResult, LimitName, RunHandle, RunResult } from '../caskada'

type State = { [key: string]: unknown }

function assertLimit(result: RunResult<State>, limit: LimitName): asserts result is FailedResult<State> {
  assert.equal(result.status, 'failed')
  if (result.status !== 'failed') throw new Error('expected a failed run')
  assert.equal(result.failure.kind, 'limit')
  assert.equal(result.failure.message, 'Run limit exceeded')
  assert.equal(result.failure.cause, null)
  assert.deepEqual(result.failure.detail, { type: 'limit', limit })
}

describe('v3 resource limits', () => {
  it('accepts supported limits and requires root activation capacity', async () => {
    const result = await new Flow(node<State>(() => undefined)).start(
      {},
      {
        maxActivations: 2,
        maxConcurrency: 1,
        maxAttempts: 1,
        maxTransitions: 1,
        maxReady: 1,
        maxReports: 1,
        maxDepth: 1,
      },
    ).result

    assert.equal(result.status, 'completed')
    assert.throws(() => new Flow(node<State>(() => undefined)).start({}, { maxActivations: 1 }))
  })

  it('keeps caught emit overflow fenced and discards the buffer', async () => {
    let caught = false
    const source = node<State>((context) => {
      context.emit('next', 1)
      try {
        context.emit('next', 2)
      } catch {
        caught = true
      }
    })
    source.link(
      node<State>(() => undefined),
      'next',
    )

    const result = await new Flow(source).start({}, { maxTransitions: 1 }).result

    assert.equal(caught, true)
    assertLimit(result, 'max_transitions')
    assert.equal(result.stats.transitions, 0)
    assert.equal(result.stats.activations, 2)
    assert.deepEqual(result.terminals, [])
  })

  it('charges a synthetic default against transition capacity', async () => {
    const source = node<State>(() => undefined)
    source.link(node<State>(() => undefined))

    const result = await new Flow(source).start({}, { maxTransitions: 1 }).result

    assertLimit(result, 'max_transitions')
    assert.equal(result.stats.transitions, 1)
    assert.equal(result.stats.activations, 3)
    assert.equal(result.stats.attempts, 2)
  })

  it('rejects a complete batch at the run activation limit', async () => {
    const source = node<State>((context) => context.emit('next'))
    source.link(
      node<State>(() => undefined),
      'next',
    )

    const result = await new Flow(source).start({}, { maxActivations: 2 }).result

    assertLimit(result, 'max_activations')
    assert.equal(result.stats.activations, 2)
    assert.equal(result.stats.transitions, 0)
    assert.equal(result.stats.peakReady, 1)
  })

  it('uses a fresh direct-activation limit for each Flow scope', async () => {
    const source = node<State>((context) => context.emit('next'))
    source.link(
      node<State>(() => undefined),
      'next',
    )

    const result = await new Flow(source, { maxActivations: 1 }).start({}).result

    assertLimit(result, 'scope_max_activations')
    assert.equal(result.failure.scopeId, 1)
    assert.equal(result.stats.activations, 2)
    assert.equal(result.stats.transitions, 0)
  })

  it('rejects fanout atomically at the ready limit', async () => {
    const source = node<State>((context) => {
      context.emit('left')
      context.emit('right')
    })
    source.link(
      node<State>(() => undefined),
      'left',
    )
    source.link(
      node<State>(() => undefined),
      'right',
    )

    const result = await new Flow(source).start({}, { maxReady: 1 }).result

    assertLimit(result, 'max_ready')
    assert.equal(result.stats.activations, 2)
    assert.equal(result.stats.transitions, 0)
    assert.equal(result.stats.peakReady, 1)
  })

  it('uses the normative batch-capacity priority', async () => {
    const source = node<State>((context) => context.emit('next'))
    source.link(
      node<State>(() => undefined),
      'next',
    )

    const result = await new Flow(source, { maxActivations: 1 }).start({}, { maxActivations: 2, maxReady: 1 }).result

    assertLimit(result, 'max_activations')
  })

  it('allocates no child scope when nested depth is exhausted', async () => {
    const source = node<State>((context) => context.emit('child'))
    const child = new Flow(node<State>(() => undefined))
    source.link(child, 'child')

    const result = await new Flow(source).start({}, { maxDepth: 1 }).result

    assertLimit(result, 'max_depth')
    assert.equal(result.failure.scopeId, 1)
    assert.equal(result.failure.activationId, 3)
    assert.equal(result.stats.activations, 3)
    assert.equal(result.stats.transitions, 1)
    assert.equal(result.stats.scopes, 1)
  })

  it('admits no callback when the initial attempt budget is exhausted', async () => {
    const calls: string[] = []
    const source = node<State>((context) => {
      calls.push('source')
      context.emit('next')
    })
    source.link(
      node<State>(() => {
        calls.push('target')
      }),
      'next',
    )

    const result = await new Flow(source).start({}, { maxAttempts: 1 }).result

    assertLimit(result, 'max_attempts')
    assert.deepEqual(calls, ['source'])
    assert.equal(result.failure.attempt, null)
    assert.equal(result.failure.previous, null)
    assert.equal(result.stats.attempts, 1)
    assert.equal(result.stats.transitions, 1)
  })

  it('replaces a failed packet before retry delay or recovery', async () => {
    const calls: unknown[] = []
    const worker = node<State>(
      (context) => {
        calls.push(context.attempt)
        throw new Error('failed')
      },
      {
        retry: {
          maxAttempts: 2,
          shouldRetry() {
            calls.push('policy')
            return true
          },
          delayMs() {
            calls.push('delay')
            return 0
          },
        },
        recover() {
          calls.push('recover')
        },
      },
    )

    const result = await new Flow(worker).start({}, { maxAttempts: 1 }).result

    assertLimit(result, 'max_attempts')
    assert.deepEqual(calls, [1, 'policy'])
    assert.equal(result.failure.attempt, null)
    assert.equal(result.failure.previous?.kind, 'handler')
    assert.equal(result.stats.attempts, 1)
    assert.equal(result.stats.retries, 0)
  })

  it('charges terminal forwarding against transition capacity', async () => {
    const source = node<State>((context) => context.emit('child'))
    const child = new Flow(node<State>((context) => context.end('done')))
    source.link(child, 'child')

    const result = await new Flow(source).start({}, { maxTransitions: 2 }).result

    assertLimit(result, 'max_transitions')
    assert.equal(result.stats.transitions, 2)
    assert.deepEqual(result.terminals, [])
  })

  it('retains inherited packet suppression on a later batch limit', async () => {
    const source = node<State>(
      async (context) => {
        if (context.attempt === 1) {
          await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
          throw new Error('post-timeout')
        }
        context.emit('next')
      },
      { retry: { maxAttempts: 2 }, timeoutMs: 5 },
    )
    source.link(
      node<State>(() => undefined),
      'next',
    )

    const result = await new Flow(source).start({}, { maxActivations: 2, cancelGraceMs: 100 }).result

    assertLimit(result, 'max_activations')
    assert.equal(result.failure.previous?.kind, 'handler_timeout')
    assert.deepEqual(
      result.suppressed.map((failure) => failure.kind),
      ['handler'],
    )
  })

  it('keeps a committed limit fence ahead of later caller cancellation', async () => {
    let handle: RunHandle<State>
    const source = node<State>((context) => {
      context.emit()
      try {
        context.emit()
      } catch {
        // The hard limit remains committed even when application code catches the signal.
      }
      handle.cancel('later')
    })

    handle = new Flow(source).start({}, { maxTransitions: 1 })
    const result = await handle.result

    assertLimit(result, 'max_transitions')
  })
})
