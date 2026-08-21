import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { RunStats } from '../caskada'

type State = { [key: string]: unknown }

function deferred(): { readonly promise: Promise<void>; readonly resolve: () => void } {
  let resolve!: () => void
  const promise = new Promise<void>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

describe('v3 RunStats', () => {
  it('counts every committed fact in a completed nested run', async () => {
    const child = new Flow(node<State>(() => {}))
    const result = await new Flow(child).start({}).result

    assert.equal(result.status, 'completed')
    assertStats(result.stats, {
      activations: 3,
      attempts: 1,
      transitions: 2,
      retries: 0,
      reports: 0,
      scopes: 2,
      peakReady: 1,
      peakCallbacks: 1,
    })
  })

  it('keeps only committed work in a failed result', async () => {
    const fail = node<State>(() => {
      throw new Error('failed')
    })
    const result = await new Flow(fail).start({}).result

    assert.equal(result.status, 'failed')
    assertStats(result.stats, {
      activations: 2,
      attempts: 1,
      transitions: 0,
      retries: 0,
      reports: 0,
      scopes: 1,
      peakReady: 1,
      peakCallbacks: 1,
    })
  })

  it('counts only opening facts after pre-admission cancellation', async () => {
    let calls = 0
    const handler = node<State>(() => {
      calls += 1
    })
    const handle = new Flow(handler).start({})
    handle.cancel('stop')
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.equal(calls, 0)
    assertStats(result.stats, {
      activations: 2,
      attempts: 0,
      transitions: 0,
      retries: 0,
      reports: 0,
      scopes: 1,
      peakReady: 1,
      peakCallbacks: 0,
    })
  })

  it('freezes abandonment stats before late work finishes', async () => {
    const entered = deferred()
    const release = deferred()
    const stubborn = node<State>(async () => {
      entered.resolve()
      await release.promise
    })
    const handle = new Flow(stubborn).start({}, { cancelGraceMs: 0 })
    await entered.promise
    handle.cancel('stop')
    const result = await handle.result

    assert.equal(result.status, 'abandoned')
    assertStats(result.stats, {
      activations: 2,
      attempts: 1,
      transitions: 0,
      retries: 0,
      reports: 0,
      scopes: 1,
      peakReady: 1,
      peakCallbacks: 1,
    })
    const terminalDuration = result.stats.durationMs
    release.resolve()
    await new Promise((resolve) => setTimeout(resolve, 10))
    assert.equal(result.stats.durationMs, terminalDuration)
  })
})

function assertStats(stats: RunStats, expected: Omit<RunStats, 'durationMs'>): void {
  assert.deepEqual(
    {
      activations: stats.activations,
      attempts: stats.attempts,
      transitions: stats.transitions,
      retries: stats.retries,
      reports: stats.reports,
      scopes: stats.scopes,
      peakReady: stats.peakReady,
      peakCallbacks: stats.peakCallbacks,
    },
    expected,
  )
  assert.ok(stats.durationMs >= 0)
}
