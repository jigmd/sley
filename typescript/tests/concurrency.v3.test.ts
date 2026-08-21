import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { RunResult } from '../caskada'

type State = { recovered?: boolean; [key: string]: unknown }

function deferred(): { readonly promise: Promise<void>; readonly resolve: () => void } {
  let resolve!: () => void
  const promise = new Promise<void>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

describe('v3 topology-aware concurrency', () => {
  it('derives the global ceiling from the root scope width', async () => {
    const { peak, result } = await gatedFanout(8)

    assert.equal(peak, 8)
    assert.equal(result.stats.peakCallbacks, 8)
  })

  it('does not let a serial parent throttle a parallel child', async () => {
    const { peak, result } = await gatedFanout(8, { nested: true })

    assert.equal(peak, 8)
    assert.equal(result.stats.peakCallbacks, 8)
  })

  it('applies an explicit global ceiling independently of local width', async () => {
    const { peak, result } = await gatedFanout(8, { maxConcurrency: 3 })

    assert.equal(peak, 3)
    assert.equal(result.stats.peakCallbacks, 3)
  })

  it('keeps callback execution serial when every scope has width one', async () => {
    let active = 0
    let peak = 0
    const first = node<State>(async () => {
      active += 1
      peak = Math.max(peak, active)
      await Promise.resolve()
      active -= 1
    })
    const second = node<State>(async () => {
      active += 1
      peak = Math.max(peak, active)
      await Promise.resolve()
      active -= 1
    })
    first.link(second)

    const result = await new Flow(new Flow(first, { concurrency: 1 }), { concurrency: 1 }).start({}, { maxConcurrency: 8 }).result

    assert.equal(result.status, 'completed')
    assert.equal(peak, 1)
    assert.equal(result.stats.peakCallbacks, 1)
  })

  it('releases the only callback permit while a retry is delayed', async () => {
    const order: string[] = []
    const dispatch = node<State>((context) => {
      context.emit('work', 'retry')
      context.emit('work', 'peer')
    })
    const worker = node<State, string>(
      async (context) => {
        order.push(`${context.input}:${context.attempt}`)
        if (context.input === 'retry' && context.attempt === 1) throw new Error('retry once')
      },
      {
        retry: {
          maxAttempts: 2,
          shouldRetry: () => true,
          delayMs: 10,
        },
      },
    )
    dispatch.link(worker, 'work')

    const result = await new Flow(dispatch, { concurrency: 2 }).start({}, { maxConcurrency: 1 }).result

    assert.equal(result.status, 'completed')
    assert.deepEqual(order, ['retry:1', 'peer:1', 'retry:2'])
    assert.equal(result.stats.peakCallbacks, 1)
  })

  it('admits a due retry before a waiting new activation', async () => {
    const order: string[] = []
    const blockerStarted = deferred()
    const releaseBlocker = deferred()
    const dispatch = node<State>((context) => {
      context.emit('work', 'retry')
      context.emit('work', 'blocker')
      context.emit('work', 'new')
    })
    const worker = node<State, string>(
      async (context) => {
        order.push(`${context.input}:${context.attempt}`)
        if (context.input === 'retry' && context.attempt === 1) throw new Error('retry once')
        if (context.input === 'blocker') {
          blockerStarted.resolve()
          await releaseBlocker.promise
        }
      },
      { retry: { maxAttempts: 2, shouldRetry: () => true, delayMs: 10 } },
    )
    dispatch.link(worker, 'work')
    const handle = new Flow(dispatch, { concurrency: 3 }).start({}, { maxConcurrency: 1 })

    await blockerStarted.promise
    await new Promise((resolve) => setTimeout(resolve, 20))
    releaseBlocker.resolve()
    const result = await handle.result

    assert.equal(result.status, 'completed')
    assert.deepEqual(order, ['retry:1', 'blocker:1', 'retry:2', 'new:1'])
  })

  it('rotates new callbacks between eligible scopes', async () => {
    const order: Array<readonly [string, number]> = []
    const rootDispatch = node<State>((context) => {
      context.emit('batch', 'A')
      context.emit('batch', 'B')
    })
    const childDispatch = node<State, string>((context) => {
      for (let index = 0; index < 3; index += 1) context.emit('work', [context.input, index] as const)
    })
    const worker = node<State, readonly [string, number]>(async (context) => {
      order.push(context.input)
      await Promise.resolve()
    })
    childDispatch.link(worker, 'work')
    const child = new Flow(childDispatch, { concurrency: 3 })
    rootDispatch.link(child, 'batch')

    const result = await new Flow(rootDispatch, { concurrency: 2 }).start({}, { maxConcurrency: 1 }).result

    assert.equal(result.status, 'completed')
    assert.ok(
      order.findIndex(([label, index]) => label === 'B' && index === 0) <
        order.findIndex(([label, index]) => label === 'A' && index === 2),
    )
  })

  it('signals a live sibling before entering Flow recovery', async () => {
    let siblingSignalled = false
    const dispatch = node<State>((context) => {
      context.emit('work', 'failure')
      context.emit('work', 'sibling')
    })
    const worker = node<State, string>(async (context) => {
      if (context.input === 'failure') {
        await Promise.resolve()
        throw new Error('failed')
      }
      await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
      siblingSignalled = context.cancellation.cancelled
    })
    dispatch.link(worker, 'work')
    const flow = new Flow(dispatch, {
      concurrency: 2,
      recover(context) {
        context.state.recovered = true
        context.end()
      },
    })

    const result = await flow.start({}).result

    assert.equal(result.status, 'completed')
    assert.equal(result.state.recovered, true)
    assert.equal(siblingSignalled, true)
    assert.equal(result.stats.peakCallbacks, 2)
  })
})

async function gatedFanout(
  width: number,
  options: { readonly nested?: boolean; readonly maxConcurrency?: number } = {},
): Promise<{ readonly peak: number; readonly result: RunResult<State> }> {
  let active = 0
  let peak = 0
  const threshold = options.maxConcurrency ?? width
  const started = deferred()
  const release = deferred()
  const dispatch = node<State>((context) => {
    for (let index = 0; index < width; index += 1) context.emit('work', index)
  })
  const worker = node<State, number>(async () => {
    active += 1
    peak = Math.max(peak, active)
    if (active === threshold) started.resolve()
    await release.promise
    active -= 1
  })
  dispatch.link(worker, 'work')
  let flow = new Flow(dispatch, { concurrency: width })
  if (options.nested === true) flow = new Flow(flow, { concurrency: 1 })
  const handle = flow.start({}, options.maxConcurrency === undefined ? undefined : { maxConcurrency: options.maxConcurrency })
  await started.promise
  release.resolve()
  const result = await handle.result
  return { peak, result }
}
