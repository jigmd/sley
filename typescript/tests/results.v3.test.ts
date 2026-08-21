import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node, OptionValidationError } from '../caskada'

import type { Context } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 successful results and handles', () => {
  it('returns a pending handle before admitting callbacks and stores one result', async () => {
    let calls = 0
    const flow = new Flow(
      node<State>((context) => {
        calls += 1
        context.state.handled = true
      }),
    )

    const handle = flow.start({})

    assert.equal(handle.done, false)
    assert.equal(calls, 0)
    const first = await handle.result
    const second = await handle.result

    assert.equal(handle.done, true)
    assert.equal(first, second)
    assert.equal(first.status, 'completed')
    assert.deepEqual({ ...first.state }, { handled: true })
    assert.equal(calls, 1)
    handle.cancel()
  })

  it('preserves terminal output identity, absence, and plurality', async () => {
    const firstOutput = { value: 1 }
    const secondOutput = { value: 2 }
    const finish = node<State>((context) => {
      context.end(firstOutput)
      context.end()
      context.end(secondOutput)
    })

    const result = await new Flow(finish).start({}).result

    assert.equal(result.terminals.length, 3)
    assert.equal(result.terminals[0]!.hasOutput, true)
    assert.equal(result.terminals[0]!.output, firstOutput)
    assert.equal(result.terminals[1]!.hasOutput, false)
    assert.equal(result.terminals[1]!.output, undefined)
    assert.equal(result.terminals[2]!.output, secondOutput)
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.sequence),
      [1, 2, 3],
    )
    assert.equal(Object.isFrozen(result), true)
    assert.equal(Object.isFrozen(result.terminals), true)
    assert.equal(Object.getPrototypeOf(result), null)
  })

  it('projects one execution to the exact state carrier', async () => {
    let calls = 0
    let callbackState: State | undefined
    const mutate = node<State>((context) => {
      calls += 1
      callbackState = context.state
      context.state.value = 3
    })

    const state = await new Flow(mutate).run({})

    assert.equal(calls, 1)
    assert.equal(state, callbackState)
    assert.deepEqual({ ...state }, { value: 3 })
  })

  it('counts committed serial work', async () => {
    const first = node<State>(() => {})
    const second = node<State>(() => {})
    first.link(second)

    const result = await new Flow(first).start({}).result

    assert.deepEqual(
      {
        activations: result.stats.activations,
        attempts: result.stats.attempts,
        transitions: result.stats.transitions,
        retries: result.stats.retries,
        reports: result.stats.reports,
        scopes: result.stats.scopes,
        peakReady: result.stats.peakReady,
        peakCallbacks: result.stats.peakCallbacks,
      },
      {
        activations: 3,
        attempts: 2,
        transitions: 2,
        retries: 0,
        reports: 0,
        scopes: 1,
        peakReady: 1,
        peakCallbacks: 1,
      },
    )
    assert(result.stats.durationMs >= 0)
  })

  it('reuses a compiled snapshot while capturing a state per start', async () => {
    const compiled = new Flow(node<State>(() => {})).compile()

    const first = await compiled.start({ run: 1 }).result
    const second = await compiled.start({ run: 2 }).result

    assert.deepEqual({ ...first.state }, { run: 1 })
    assert.deepEqual({ ...second.state }, { run: 2 })
    assert.notEqual(first.state, second.state)
  })

  it('throws preflight errors synchronously without creating a callback', async () => {
    let calls = 0
    const flow = new Flow(
      node<State>(() => {
        calls += 1
      }),
    )

    assert.throws(() => flow.start({}, { unknown: true } as never), OptionValidationError)
    assert.throws(() => flow.run({}, { unknown: true } as never), OptionValidationError)
    await Promise.resolve()
    assert.equal(calls, 0)
  })

  it('keeps result settlement safe under Object.prototype.then pollution', async () => {
    let thenCalls = 0
    Object.defineProperty(Object.prototype, 'then', {
      value: (): void => {
        thenCalls += 1
      },
      configurable: true,
    })
    try {
      const handle = new Flow(node<State>(() => {})).start({ value: 1 })
      const result = await handle.result

      assert.equal(result.status, 'completed')
      assert.equal(result.state.value, 1)
      assert.equal(thenCalls, 0)
      assert.equal(Object.getPrototypeOf(result), null)
    } finally {
      delete (Object.prototype as State).then
    }
  })

  it('exposes the callback state through the successful result', async () => {
    let callbackState: State | undefined
    const inspect = node<State>((context: Context<State>) => {
      callbackState = context.state
    })

    const result = await new Flow(inspect).start({}).result

    assert.equal(result.state, callbackState)
    assert.deepEqual(result.diagnostics, [])
  })
})
