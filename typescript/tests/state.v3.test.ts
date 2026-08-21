import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node, OptionValidationError } from '../caskada'

import type { Context, ScopeResult } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 persistent state carrier', () => {
  it('uses one ordinary mutable record per run', async () => {
    let alias: State | undefined
    const mutate = node<State>((context) => {
      alias = context.state
      context.state.initial = 1
      Object.assign(context.state, { assigned: 2 })
      Object.defineProperty(context.state, 'defined', { value: 3, enumerable: true, configurable: true, writable: true })
      context.state.temporary = 4
      delete context.state.temporary
      assert.deepEqual(Object.keys(context.state), ['initial', 'assigned', 'defined'])
      assert.deepEqual(Object.entries(context.state), [
        ['initial', 1],
        ['assigned', 2],
        ['defined', 3],
      ])
      const serialized = JSON.parse(JSON.stringify(context.state)) as Record<string, unknown>
      assert.equal(serialized.assigned, 2)
    })

    const state = await new Flow(mutate).run({})

    assert.equal(state, alias)
    state.after = 5
    assert.equal(alias!.after, 5)
    assert.equal(Object.getPrototypeOf(state), Object.prototype)
  })

  it('uses native shallow-copy semantics for enumerable properties', async () => {
    let getterCalls = 0
    const accessor = {}
    Object.defineProperty(accessor, 'bad', {
      enumerable: true,
      get() {
        getterCalls += 1
        return 1
      },
    })
    const state = await new Flow(node<State>(() => {})).run(accessor)
    assert.equal(getterCalls, 1)
    assert.deepEqual(state, { bad: 1 })
    assert.throws(() => new Flow(node<State>(() => {})).run([] as never), OptionValidationError)
  })

  it('shallow-copies once and preserves nested and self aliases', async () => {
    const nested: string[] = []
    const initial: State = { nested }
    initial.self = initial
    const mutate = node<State>((context) => {
      ;(context.state.nested as string[]).push('shared')
      context.state.added = true
    })

    const state = await new Flow(mutate).run(initial)

    assert.notEqual(state, initial)
    assert.equal(state.nested, nested)
    assert.equal(state.self, initial)
    assert.deepEqual(nested, ['shared'])
    assert.equal('added' in initial, false)
  })

  it('passes the state carrier as exact input and output when requested', async () => {
    const identities: boolean[] = []
    const producer = node<State>((context) => context.emit({ input: context.state }))
    const consumer = node<State, unknown>((context) => {
      identities.push(context.input === context.state)
      context.end(context.state)
    })
    producer.link(consumer)
    const flow = new Flow(producer, {
      combine(context, result: ScopeResult) {
        identities.push(result.outputs[0] === context.state)
      },
    })

    await flow.run({})

    assert.deepEqual(identities, [true, true])
  })

  it('creates distinct top-level carriers for separate runs', async () => {
    const flow = new Flow(node<State>(() => {})).compile()
    const nested: unknown[] = []
    const initial: State = { nested }

    const first = await flow.run(initial)
    const second = await flow.run(initial)

    assert.notEqual(first, second)
    assert.notEqual(first, initial)
    assert.equal(first.nested, second.nested)
  })

  it('fulfills run with callable then data without assimilating it', async () => {
    let thenCalls = 0
    const applicationThen = (): void => {
      thenCalls += 1
    }
    const descriptor = { value: applicationThen, writable: true, enumerable: true, configurable: true }
    const initial: State = {}
    Object.defineProperty(initial, 'then', descriptor)
    let callbackState: State | undefined
    const flow = new Flow(
      node<State>((context) => {
        callbackState = context.state
      }),
    )
    const pending = flow.run(initial)
    const waiterIdentities: boolean[] = []
    void pending.then((state) => {
      waiterIdentities.push(state === callbackState)
    })

    const state = await pending

    assert.equal(state, callbackState)
    assert.equal(thenCalls, 0)
    assert.deepEqual(waiterIdentities, [true])
    assert.deepEqual(Object.getOwnPropertyDescriptor(state, 'then'), descriptor)
  })

  it('masks inherited then pollution and restores an absent own property', async () => {
    let thenCalls = 0
    Object.defineProperty(Object.prototype, 'then', {
      value: (): void => {
        thenCalls += 1
      },
      writable: true,
      configurable: true,
    })
    try {
      const state = await new Flow(node<State>(() => {})).run({ value: 1 })
      assert.equal(thenCalls, 0)
      assert.equal(Object.prototype.hasOwnProperty.call(state, 'then'), false)
      assert.equal(state.value, 1)
    } finally {
      delete (Object.prototype as State).then
    }
  })
})
