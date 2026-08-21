import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { Context, ScopeResult } from '../caskada'

type State = { count?: number; nested?: string[]; [key: string]: unknown }

describe('v3 deterministic serial execution', () => {
  it('takes implicit links through one run-owned state record', async () => {
    const initialState: State = { count: 0, nested: [] }
    const seenState: State[] = []
    const first = node<State>((context) => {
      seenState.push(context.state)
      context.state.count = 1
    })
    const second = node<State>(async (context) => {
      seenState.push(context.state)
      context.state.count = context.state.count! + 1
      context.state.nested!.push('shared')
    })
    first.link(second)

    const state = await new Flow(first).run(initialState)

    assert.deepEqual(state, { count: 2, nested: ['shared'] })
    assert.equal(state, seenState[0])
    assert.equal(state, seenState[1])
    assert.notEqual(state, initialState)
    assert.deepEqual(initialState, { count: 0, nested: ['shared'] })
  })

  it('passes explicit and forwarded branch input by identity', async () => {
    const seen: unknown[] = []
    const producer = node<State>((context) => context.emit('work', { value: 7 }))
    const forwarding = node<State, unknown>((context) => {
      seen.push(context.input)
      context.emit()
    })
    const consumer = node<State, unknown>((context) => {
      seen.push(context.input)
      context.state.seen = context.input
    })
    producer.link(forwarding, 'work')
    forwarding.link(consumer)

    const state = await new Flow(producer).run({})

    assert.deepEqual(state.seen, { value: 7 })
    assert.equal(seen[0], seen[1])
  })

  it('makes hard Ends bypass links and distinguish omitted output', async () => {
    const observed: ScopeResult[] = []
    const finish = node<State>((context) => {
      context.end()
      context.end(undefined)
    })
    finish.link(
      node<State>((context) => {
        context.state.ran = true
      }),
    )
    const flow = new Flow(finish, {
      combine(context, result) {
        observed.push(result)
        context.state.outputs = result.outputs.slice()
      },
    })

    const state = await flow.run({})

    assert.equal('ran' in state, false)
    assert.deepEqual(state.outputs, [undefined])
    const [first, second] = observed[0]!.terminals
    assert.deepEqual([first!.type, first!.hasOutput, first!.output], ['end', false, undefined])
    assert.deepEqual([second!.type, second!.hasOutput, second!.output], ['end', true, undefined])
    assert.deepEqual([first!.sequence, second!.sequence], [1, 2])
    assert.deepEqual([first!.sourceActivationId, second!.sourceActivationId], [2, 2])
  })

  it('fans out in call order and preserves terminals after a zero-emission combine', async () => {
    const combined: ScopeResult[] = []
    const dispatch = node<State>((context) => {
      for (const value of [1, 2, 3]) context.emit('work', value)
    })
    dispatch.link(
      node<State, number>((context) => context.end(context.input * 10)),
      'work',
    )
    const flow = new Flow(dispatch, {
      combine(context, result) {
        combined.push(result)
        context.state.total = result.outputs.reduce<number>((total, value) => total + (value as number), 0)
      },
    })

    const state = await flow.run({})

    assert.equal(state.total, 60)
    assert.deepEqual(combined[0]!.outputs, [10, 20, 30])
    assert.deepEqual(
      combined[0]!.terminals.map((terminal) => terminal.sequence),
      [1, 2, 3],
    )
  })

  it('lets a nested combiner replace terminals with one continuation', async () => {
    const dispatch = node<State>((context) => {
      context.emit('work', 1)
      context.emit('work', 2)
    })
    dispatch.link(
      node<State, number>((context) => context.end(context.input * 10)),
      'work',
    )
    const mapper = new Flow(dispatch, {
      combine(context, result) {
        context.emit({ input: result.outputs.slice() })
      },
    })
    mapper.link(
      node<State, unknown>((context) => {
        context.state.values = context.input
      }),
    )

    const state = await new Flow(mapper).run({})

    assert.deepEqual(state.values, [10, 20])
  })

  it('allows a declared named exit', async () => {
    const ask = node<State>((context) => context.emit('needs_input', { question: 'name?' }))
    const state = await new Flow(ask, { exits: ['needs_input'] }).run({ kept: true })
    assert.deepEqual(state, { kept: true })
  })

  it('closes Context while keeping an obtained state alias live', async () => {
    const contexts: Array<Context<State>> = []
    const aliases: State[] = []
    const retain = node<State>((context) => {
      contexts.push(context)
      aliases.push(context.state)
    })

    const state = await new Flow(retain).run({})

    assert.throws(() => contexts[0]!.state, /closed/)
    aliases[0]!.late = true
    assert.equal(aliases[0], state)
    assert.equal(state.late, true)
  })

  it('executes deeply nested Flows without recursive calls', async () => {
    const leaf = node<State>((context) => {
      context.state.visited = true
    })
    let nested = new Flow(leaf)
    for (let index = 0; index < 1_500; index += 1) nested = new Flow(nested)

    const state = await nested.compile().run({}, { maxDepth: 1_501 })

    assert.deepEqual(state, { visited: true })
  })
})
