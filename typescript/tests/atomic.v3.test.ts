import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { Context, ScopeResult } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 atomic callback settlement', () => {
  it('rejects a complete handler batch when one arm is invalid', async () => {
    const source = node<State>((context) => {
      context.state.written = true
      context.emit('valid', 1)
      context.emit('missing', 2)
    })
    source.link(
      node<State, number>((context) => {
        context.state.ran = context.input
      }),
      'valid',
    )

    const result = await new Flow(source).start({}).result

    assert.equal(result.status, 'failed')
    assert.deepEqual({ ...result.state }, { written: true })
    assert.deepEqual(result.terminals, [])
    assert.equal(result.stats.activations, 2)
    assert.equal(result.stats.attempts, 1)
    assert.equal(result.stats.transitions, 0)
    assert.equal(result.stats.peakReady, 1)
  })

  it('discards every buffered arm when the handler throws', async () => {
    const cause = new Error('after emit')
    const source = node<State>((context) => {
      context.emit('valid')
      throw cause
    })
    source.link(
      node<State>((context) => {
        context.state.ran = true
      }),
      'valid',
    )

    const result = await new Flow(source).start({}).result

    assert.equal(result.status, 'failed')
    assert.equal('ran' in result.state, false)
    assert.equal(result.stats.transitions, 0)
    if (result.status !== 'failed') throw new Error('handler throw must fail')
    assert.equal(result.failure.cause, cause)
  })

  it('keeps prior intents when application code catches semantic misuse', async () => {
    const source = node<State>((context) => {
      context.emit('valid', 3)
      try {
        context.emit('')
      } catch (error) {
        assert(error instanceof TypeError)
      }
    })
    source.link(
      node<State, number>((context) => {
        context.state.value = context.input
      }),
      'valid',
    )

    const state = await new Flow(source).run({})

    assert.deepEqual({ ...state }, { value: 3 })
  })

  it('checks a controlling fence between input-wrapper reflection traps', async () => {
    const calls: string[] = []
    let handle: ReturnType<Flow<State>['start']>
    const wrapper = new Proxy(
      { input: 1 },
      {
        getPrototypeOf() {
          calls.push('prototype')
          handle.cancel('trap')
          return Object.prototype
        },
        ownKeys(target) {
          calls.push('keys')
          return Reflect.ownKeys(target)
        },
        getOwnPropertyDescriptor(target, key) {
          calls.push('descriptor')
          return Reflect.getOwnPropertyDescriptor(target, key)
        },
      },
    )
    const source = node<State>(((context: Context<State>) => {
      try {
        context.emit(wrapper as never)
      } catch {
        calls.push('caught')
      }
    }) as (context: Context<State>) => void)

    handle = new Flow(source).start({})
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.deepEqual(calls, ['prototype', 'caught'])
  })

  it('preserves original terminals when a combine replacement batch is rejected', async () => {
    const flow = new Flow(
      node<State>((context) => context.end('original')),
      {
        combine(context: Context<State>, _result: ScopeResult) {
          context.end('replacement')
          context.emit('missing')
        },
      },
    )

    const result = await flow.start({}).result

    assert.equal(result.status, 'failed')
    assert.equal(result.terminals.length, 1)
    assert.equal(result.terminals[0]!.output, 'original')
    assert.equal(result.stats.transitions, 1)
  })
})
