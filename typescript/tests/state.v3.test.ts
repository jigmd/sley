import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node, OptionValidationError } from '../caskada'

import type { Context, ScopeResult } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 persistent state carrier', () => {
  it('supports ordinary record operations through one stable Proxy', async () => {
    let alias: State | undefined
    const mutate = node<State>((context) => {
      alias = context.state
      context.state.initial = 1
      Object.assign(context.state, { assigned: 2 })
      Object.defineProperty(context.state, 'defined', { value: 3, enumerable: true, configurable: true, writable: true })
      context.state.temporary = 4
      delete context.state.temporary
      context.state.__proto__ = 'data'
      assert.deepEqual(Object.keys(context.state), ['initial', 'assigned', 'defined', '__proto__'])
      assert.deepEqual(Object.entries(context.state), [
        ['initial', 1],
        ['assigned', 2],
        ['defined', 3],
        ['__proto__', 'data'],
      ])
      assert.equal(Object.prototype.hasOwnProperty.call(context.state, '__proto__'), true)
      const serialized = JSON.parse(JSON.stringify(context.state)) as Record<string, unknown>
      assert.equal(serialized.assigned, 2)
    })

    const state = await new Flow(mutate).run({})

    assert.equal(state, alias)
    state.after = 5
    assert.equal(alias!.after, 5)
    assert.equal(Object.getPrototypeOf(state), Object.prototype)
  })

  it('rejects symbol, accessor, prototype, and extensibility mutations atomically', async () => {
    const symbol = Symbol('state')
    const mutate = node<State>((context) => {
      context.state.kept = 1
      assert.throws(() => Reflect.set(context.state, symbol, 2), TypeError)
      assert.throws(
        () => Object.defineProperty(context.state, 'accessor', { get: () => 3, configurable: true, enumerable: true }),
        TypeError,
      )
      assert.throws(() => Object.setPrototypeOf(context.state, null), TypeError)
      assert.throws(() => Object.preventExtensions(context.state), TypeError)
      assert.throws(() => Object.seal(context.state), TypeError)
      assert.throws(() => Object.freeze(context.state), TypeError)
    })

    const state = await new Flow(mutate).run({})

    assert.deepEqual({ ...state }, { kept: 1 })
    assert.equal(Object.isExtensible(state), true)
    assert.deepEqual(Object.getOwnPropertySymbols(state), [])
  })

  it('captures initial data descriptors in exact reflection order without getters', async () => {
    const operations: string[] = []
    const sourceTarget = { first: 1, second: 2 }
    const source = new Proxy(sourceTarget, {
      getPrototypeOf(target) {
        operations.push('prototype')
        return Reflect.getPrototypeOf(target)
      },
      ownKeys(target) {
        operations.push('keys')
        return Reflect.ownKeys(target)
      },
      getOwnPropertyDescriptor(target, property) {
        operations.push(`descriptor:${String(property)}`)
        return Reflect.getOwnPropertyDescriptor(target, property)
      },
      get() {
        throw new Error('initial capture must not read property values through get')
      },
    })

    const state = await new Flow(node<State>(() => {})).run(source)

    assert.deepEqual(operations, ['prototype', 'keys', 'descriptor:first', 'descriptor:second'])
    assert.deepEqual({ ...state }, sourceTarget)

    let getterCalls = 0
    const accessor = {}
    Object.defineProperty(accessor, 'bad', {
      enumerable: true,
      get() {
        getterCalls += 1
        return 1
      },
    })
    assert.throws(() => new Flow(node<State>(() => {})).run(accessor), OptionValidationError)
    assert.equal(getterCalls, 0)
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
