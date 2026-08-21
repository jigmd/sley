import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node, RunError } from '../caskada'

import type { Context, FailedResult, ScopeResult } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 portable failure normalization', () => {
  it('settles handler throws as data without inspecting the cause', async () => {
    const cause = new Proxy(Object.create(null) as object, {
      get(_target, property) {
        if (property === 'message' || property === 'toString' || property === Symbol.toPrimitive) {
          throw new Error('Failure construction must not inspect its cause')
        }
        return undefined
      },
    })
    const fail = node<State>(() => {
      throw cause
    })

    const handle = new Flow(fail).start({})
    const result = await handle.result

    assert.equal(handle.done, true)
    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('handler throw must fail')
    assert.deepEqual(result.terminals, [])
    assert.deepEqual(result.suppressed, [])
    assert.deepEqual(result.diagnostics, [])
    assert.equal(result.failure.failureId, 1)
    assert.equal(result.failure.kind, 'handler')
    assert.equal(result.failure.message, 'Node handler raised')
    assert.equal(result.failure.cause, cause)
    assert.equal(result.failure.scopeId, 1)
    assert.equal(result.failure.activationId, 2)
    assert.equal(result.failure.elementId, 2)
    assert.equal(result.failure.attempt, 1)
    assert.equal(result.failure.detail, null)
    assert.equal(result.failure.previous, null)
    assert.equal(Object.isFrozen(result.failure), true)
    assert.equal(Object.getPrototypeOf(result.failure), null)
  })

  it('retains arbitrary primitive throws exactly', async () => {
    const fail = node<State>(() => {
      throw 0
    })

    const result = await new Flow(fail).start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('primitive throw must fail')
    assert.equal(result.failure.kind, 'handler')
    assert.equal(result.failure.cause, 0)
  })

  it('makes run throw one RunError retaining its exact failed result', async () => {
    const cause = { application: true }
    let calls = 0
    const fail = node<State>(() => {
      calls += 1
      throw cause
    })

    let projected: RunError<State> | undefined
    try {
      await new Flow(fail).run({})
    } catch (error) {
      assert(error instanceof RunError)
      projected = error
    }

    assert(projected !== undefined)
    assert.equal(projected.name, 'RunError')
    assert.equal(projected.message, 'Caskada run failed')
    assert.equal(projected.result.status, 'failed')
    assert.equal(projected.result.failure.cause, cause)
    assert.equal(calls, 1)
  })

  it('uses phase-specific details for wrong callback returns', async () => {
    const wrongHandler = node<State>((() => 1) as (context: Context<State>) => void)
    const handlerResult = await new Flow(wrongHandler).start({}).result

    assert.equal(handlerResult.status, 'failed')
    if (handlerResult.status !== 'failed') throw new Error('wrong handler return must fail')
    assert.equal(handlerResult.failure.kind, 'invalid_outcome')
    assert.deepEqual(handlerResult.failure.detail, { type: 'invalid_outcome', reason: 'wrong_return_type' })
    assert.equal(handlerResult.failure.cause, null)

    const wrongCombine = ((_: Context<State>, __: ScopeResult) => 1) as (context: Context<State>, result: ScopeResult) => void
    const combineResult = await new Flow(
      node<State>(() => {}),
      { combine: wrongCombine },
    ).start({}).result

    assert.equal(combineResult.status, 'failed')
    if (combineResult.status !== 'failed') throw new Error('wrong combine return must fail')
    assert.equal(combineResult.failure.kind, 'invalid_combination')
    assert.deepEqual(combineResult.failure.detail, {
      type: 'invalid_combination',
      reason: 'wrong_return_type',
    })
    assert.equal(combineResult.failure.activationId, 1)
    assert.equal(combineResult.failure.elementId, 1)
    assert.equal(combineResult.failure.attempt, null)
  })

  it('normalizes uncaught control and state misuse without a private cause', async () => {
    const invalidAction = node<State>(((context: Context<State>) => context.emit(0 as never)) as (context: Context<State>) => void)
    const actionResult = await new Flow(invalidAction).start({}).result

    assert.equal(actionResult.status, 'failed')
    if (actionResult.status !== 'failed') throw new Error('invalid action must fail')
    assert.equal(actionResult.failure.kind, 'invalid_outcome')
    assert.deepEqual(actionResult.failure.detail, { type: 'invalid_outcome', reason: 'invalid_action' })
    assert.equal(actionResult.failure.cause, null)

    const key = Symbol('bad')
    const invalidState = node<State>((context) => {
      Reflect.set(context.state, key, 1)
    })
    const stateResult = await new Flow(invalidState).start({}).result

    assert.equal(stateResult.status, 'failed')
    if (stateResult.status !== 'failed') throw new Error('invalid state operation must fail')
    assert.deepEqual(stateResult.failure.detail, { type: 'invalid_outcome', reason: 'state_record_misuse' })
    assert.equal(stateResult.failure.cause, null)
  })

  it('retains exact capture-trap errors as ordinary handler causes', async () => {
    const cause = { trap: true }
    const wrapper = new Proxy(
      { input: 1 },
      {
        getPrototypeOf() {
          throw cause
        },
      },
    )
    const fail = node<State>(((context: Context<State>) => context.emit(wrapper as never)) as (context: Context<State>) => void)

    const result = await new Flow(fail).start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('capture trap must fail')
    assert.equal(result.failure.kind, 'handler')
    assert.equal(result.failure.cause, cause)
    assert.equal(result.failure.detail, null)
  })

  it('gives Flow combine failures Flow provenance', async () => {
    const cause = { combine: true }
    const flow = new Flow(
      node<State>(() => {}),
      {
        combine() {
          throw cause
        },
      },
    )

    const result = await flow.start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('combine throw must fail')
    assert.equal(result.failure.kind, 'flow_combine')
    assert.equal(result.failure.message, 'Flow combine raised')
    assert.equal(result.failure.cause, cause)
    assert.equal(result.failure.scopeId, 1)
    assert.equal(result.failure.activationId, 1)
    assert.equal(result.failure.elementId, 1)
    assert.equal(result.failure.attempt, null)
  })

  it('makes unknown actions structured and transition-free', async () => {
    const route = node<State>((context) => context.emit('missing'))

    const result = await new Flow(route).start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('unknown action must fail')
    assert.equal(result.failure.kind, 'unknown_action')
    assert.equal(result.failure.message, 'Unknown action')
    assert.deepEqual(result.failure.detail, { type: 'unknown_action', action: 'missing' })
    assert.equal(result.failure.cause, null)
    assert.equal(result.failure.attempt, 1)
    assert.equal(result.stats.transitions, 0)
  })

  it('retains committed root terminals before a later branch fails', async () => {
    const dispatch = node<State>((context) => {
      context.emit('finish', 1)
      context.emit('fail', 2)
    })
    dispatch.link(
      node<State, number>((context) => context.end(context.input)),
      'finish',
    )
    dispatch.link(
      node<State, number>(() => {
        throw new Error('later')
      }),
      'fail',
    )

    const result = (await new Flow(dispatch).start({}).result) as FailedResult<State>

    assert.equal(result.status, 'failed')
    assert.equal(result.terminals.length, 1)
    assert.equal(result.terminals[0]!.output, 1)
  })
})
