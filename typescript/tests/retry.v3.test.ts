import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { Context, Failure, RetryOptions } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 retry policy and Node recovery', () => {
  it('reuses input and state while discarding failed-attempt buffers', async () => {
    const payload = { job: 1 }
    const states: State[] = []
    const inputs: unknown[] = []
    const policyFailures: Failure[] = []
    const delayCalls: Array<readonly [number, Failure]> = []

    const worker = node<State, object>(
      (context) => {
        states.push(context.state)
        inputs.push(context.input)
        context.state.calls = Number(context.state.calls ?? 0) + 1
        context.end(`attempt-${context.attempt}`)
        if (context.attempt !== 3) throw new Error(`failed-${context.attempt}`)
      },
      {
        retry: {
          maxAttempts: 3,
          shouldRetry(failure) {
            policyFailures.push(failure)
            return true
          },
          delayMs(attempt, failure) {
            delayCalls.push([attempt, failure])
            return 0
          },
        },
      },
    )
    const dispatch = node<State>((context) => context.emit('work', payload))
    dispatch.link(worker, 'work')

    const result = await new Flow(dispatch).start({}).result

    assert.equal(result.status, 'completed')
    assert.deepEqual({ ...result.state }, { calls: 3 })
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      ['attempt-3'],
    )
    assert.equal(result.stats.attempts, 4)
    assert.equal(result.stats.retries, 2)
    assert.equal(result.stats.transitions, 2)
    assert.deepEqual(inputs, [payload, payload, payload])
    assert.equal(states[0], states[1])
    assert.equal(states[1], states[2])
    assert.deepEqual(
      policyFailures.map((failure) => failure.attempt),
      [1, 2],
    )
    assert.equal(policyFailures[0]!.previous, null)
    assert.equal(policyFailures[1]!.previous, policyFailures[0])
    assert.deepEqual(delayCalls, [
      [1, policyFailures[0]],
      [2, policyFailures[1]],
    ])
  })

  it('skips policy at exhaustion and passes the exact packet to recovery', async () => {
    const policyCalls: Failure[] = []
    const delayCalls: Failure[] = []
    const recovered: Failure[] = []
    const worker = node<State>(
      () => {
        throw new Error('failed')
      },
      {
        retry: {
          maxAttempts: 2,
          shouldRetry(failure) {
            policyCalls.push(failure)
            return true
          },
          delayMs(_attempt, failure) {
            delayCalls.push(failure)
            return 0
          },
        },
        recover(context, failure) {
          recovered.push(failure)
          assert.equal(context.attempt, null)
        },
      },
    )

    const result = await new Flow(worker).start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('zero-emission recovery must propagate')
    assert.equal(policyCalls.length, 1)
    assert.equal(delayCalls.length, 1)
    assert.equal(recovered.length, 1)
    assert.equal(result.failure, recovered[0])
    assert.equal(result.failure.attempt, 2)
    assert.equal(result.failure.previous, policyCalls[0])
    assert.equal(result.stats.attempts, 2)
    assert.equal(result.stats.retries, 1)
  })

  it('skips delay after a false predicate and enters recovery', async () => {
    const cause = new Error('declined')
    let delayCalled = false
    const recovered: Failure[] = []
    const worker = node<State>(
      () => {
        throw cause
      },
      {
        retry: {
          maxAttempts: 3,
          shouldRetry: () => false,
          delayMs: () => {
            delayCalled = true
            return 0
          },
        },
        recover(context, failure) {
          recovered.push(failure)
          context.end('recovered')
        },
      },
    )

    const result = await new Flow(worker).start({}).result

    assert.equal(result.status, 'completed')
    assert.equal(delayCalled, false)
    assert.equal(recovered.length, 1)
    assert.equal(recovered[0]!.cause, cause)
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      ['recovered'],
    )
    assert.equal(result.stats.attempts, 1)
    assert.equal(result.stats.retries, 0)
  })

  it('consumes a packet only when the recovery emission commits', async () => {
    const payload = { job: 7 }
    const handlerStates: State[] = []
    const recoveryStates: State[] = []
    const recovered: Failure[] = []
    const worker = node<State, object>(
      (context) => {
        handlerStates.push(context.state)
        context.state.attempted = true
        throw new Error('temporary')
      },
      {
        recover(context, failure) {
          recoveryStates.push(context.state)
          recovered.push(failure)
          assert.equal(context.input, payload)
          assert.equal(context.attempt, null)
          context.emit('resume', 9)
        },
      },
    )
    worker.link(
      node<State, number>((context) => {
        context.state.value = context.input
        context.end()
      }),
      'resume',
    )
    const dispatch = node<State>((context) => context.emit('work', payload))
    dispatch.link(worker, 'work')

    const result = await new Flow(dispatch).start({}).result

    assert.equal(result.status, 'completed')
    assert.deepEqual({ ...result.state }, { attempted: true, value: 9 })
    assert.equal(handlerStates[0], recoveryStates[0])
    assert.equal(recovered[0]!.kind, 'handler')
    assert.equal(result.stats.attempts, 3)
    assert.equal(result.stats.transitions, 3)
  })

  it('makes policy failures unrecoverable replacements', async () => {
    const policyCause = { policy: true }
    let recoveryCalled = false
    const worker = node<State>(
      () => {
        throw new Error('handler')
      },
      {
        retry: {
          maxAttempts: 2,
          shouldRetry() {
            throw policyCause
          },
        },
        recover() {
          recoveryCalled = true
        },
      },
    )

    const result = await new Flow(worker).start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('policy failure must fail')
    assert.equal(recoveryCalled, false)
    assert.equal(result.failure.kind, 'retry_policy')
    assert.equal(result.failure.cause, policyCause)
    assert.equal(result.failure.attempt, 1)
    assert.equal(result.failure.previous?.kind, 'handler')
    assert.equal(result.stats.retries, 0)
  })

  it('does not coerce invalid or asynchronous policy values', async () => {
    const policies: RetryOptions[] = [
      { maxAttempts: 2, shouldRetry: (() => 1) as never },
      { maxAttempts: 2, shouldRetry: () => true, delayMs: (() => true) as never },
      { maxAttempts: 2, shouldRetry: (() => Promise.resolve(true)) as never },
    ]

    for (const retry of policies) {
      const worker = node<State>(
        () => {
          throw new Error('handler')
        },
        { retry },
      )
      const result = await new Flow(worker).start({}).result
      assert.equal(result.status, 'failed')
      if (result.status !== 'failed') throw new Error('invalid policy result must fail')
      assert.equal(result.failure.kind, 'retry_policy')
      assert.equal(result.failure.cause, null)
      assert.equal(result.failure.attempt, 1)
      assert.equal(result.failure.previous?.kind, 'handler')
    }
  })

  it('applies a callback delay before retry readmission', async () => {
    let calls = 0
    const worker = node<State>(
      (context) => {
        calls += 1
        if (calls === 1) throw new Error('retry')
        context.end()
      },
      { retry: { maxAttempts: 2, delayMs: () => 10 } },
    )
    const started = performance.now()
    const result = await new Flow(worker).start({}).result

    assert.equal(result.status, 'completed')
    assert(performance.now() - started >= 5)
    assert.equal(result.stats.retries, 1)
  })

  it('chunks a large delay instead of letting the host shorten it', async () => {
    let calls = 0
    const worker = node<State>(
      (context) => {
        calls += 1
        if (calls === 1) throw new Error('retry')
        context.end()
      },
      { retry: { maxAttempts: 2, delayMs: () => 4_294_967_295 } },
    )
    const delays: number[] = []
    const originalSetTimeout = globalThis.setTimeout
    globalThis.setTimeout = ((callback: () => void, delay?: number) => {
      delays.push(delay ?? 0)
      queueMicrotask(callback)
      return 0 as unknown as ReturnType<typeof setTimeout>
    }) as typeof setTimeout
    try {
      const result = await new Flow(worker).start({}).result
      assert.equal(result.status, 'completed')
    } finally {
      globalThis.setTimeout = originalSetTimeout
    }

    assert.deepEqual(delays, [2_147_483_647, 2_147_483_647, 1])
  })

  it('replaces the handler packet when recovery fails', async () => {
    const recoveryCause = { recovery: true }
    const fail = (): never => {
      throw new Error('handler')
    }
    const recoveryThrow = node<State>(fail, {
      recover() {
        throw recoveryCause
      },
    })
    const thrown = await new Flow(recoveryThrow).start({}).result

    assert.equal(thrown.status, 'failed')
    if (thrown.status !== 'failed') throw new Error('recovery throw must fail')
    assert.equal(thrown.failure.kind, 'node_recovery')
    assert.equal(thrown.failure.cause, recoveryCause)
    assert.equal(thrown.failure.attempt, null)
    assert.equal(thrown.failure.previous?.kind, 'handler')

    const wrongRecovery = node<State>(fail, {
      recover: (() => Object.create(null)) as (context: Context<State>, failure: Failure) => void,
    })
    const wrong = await new Flow(wrongRecovery).start({}).result

    assert.equal(wrong.status, 'failed')
    if (wrong.status !== 'failed') throw new Error('wrong recovery return must fail')
    assert.equal(wrong.failure.kind, 'invalid_outcome')
    assert.deepEqual(wrong.failure.detail, { type: 'invalid_outcome', reason: 'wrong_return_type' })
    assert.equal(wrong.failure.attempt, null)
    assert.equal(wrong.failure.previous?.kind, 'handler')
  })

  it('bypasses recovery for invalid outcomes and replaces on recovery preflight', async () => {
    let recoveryCalled = false
    const invalidHandler = node<State>((() => Object.create(null)) as (context: Context<State>) => void, {
      recover() {
        recoveryCalled = true
      },
    })
    const invalid = await new Flow(invalidHandler).start({}).result

    assert.equal(invalid.status, 'failed')
    assert.equal(recoveryCalled, false)
    if (invalid.status !== 'failed') throw new Error('invalid outcome must fail')
    assert.equal(invalid.failure.kind, 'invalid_outcome')

    const preflight = await new Flow(
      node<State>(
        () => {
          throw new Error('handler')
        },
        {
          recover(context) {
            context.emit('missing')
          },
        },
      ),
    ).start({}).result

    assert.equal(preflight.status, 'failed')
    if (preflight.status !== 'failed') throw new Error('recovery preflight must fail')
    assert.equal(preflight.failure.kind, 'unknown_action')
    assert.equal(preflight.failure.attempt, null)
    assert.equal(preflight.failure.previous?.kind, 'handler')
    assert.equal(preflight.stats.transitions, 0)
  })
})
