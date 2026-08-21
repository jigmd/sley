import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { Context, GraphElement, ScopeFailure, ScopeResult } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 Flow failure packets and recovery', () => {
  it('recovers one failed child at the root boundary', async () => {
    const seen: ScopeFailure[] = []
    const handlerStates: State[] = []
    const recoveryStates: State[] = []
    const fail = node<State>((context) => {
      handlerStates.push(context.state)
      context.state.attempted = true
      throw new Error('child')
    })
    const flow = new Flow(fail, {
      recover(context, failure) {
        recoveryStates.push(context.state)
        seen.push(failure)
        assert.equal(context.input, undefined)
        assert.equal(context.attempt, null)
        context.end('recovered')
      },
    })

    const result = await flow.start({}).result

    assert.equal(result.status, 'completed')
    assert.deepEqual({ ...result.state }, { attempted: true })
    assert.equal(handlerStates[0], recoveryStates[0])
    assert.equal(seen.length, 1)
    const scoped = seen[0]!
    assert.equal(scoped.primary.kind, 'handler')
    assert.deepEqual(scoped.suppressed, [])
    assert.deepEqual(scoped.settledBeforeFence, [])
    assert.equal(scoped.result, null)
    assert.equal(scoped.failingActivationId, 2)
    assert.equal(Object.isFrozen(scoped), true)
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      ['recovered'],
    )
  })

  it('discards ready siblings and exposes terminals settled before the fence', async () => {
    const seen: ScopeFailure[] = []
    const dispatch = node<State>((context) => {
      context.emit('done', 1)
      context.emit('fail', 2)
      context.emit('late', 3)
    })
    dispatch.link(
      node<State, number>((context) => context.end(context.input)),
      'done',
    )
    dispatch.link(
      node<State, number>(() => {
        throw new Error('failed')
      }),
      'fail',
    )
    dispatch.link(
      node<State, number>((context) => {
        context.state.late = context.input
      }),
      'late',
    )
    const flow = new Flow(dispatch, {
      recover(context, failure) {
        seen.push(failure)
        context.end('replacement')
      },
    })

    const result = await flow.start({}).result

    assert.equal(result.status, 'completed')
    assert.equal('late' in result.state, false)
    assert.equal(seen[0]!.settledBeforeFence.length, 1)
    assert.equal(seen[0]!.settledBeforeFence[0]!.output, 1)
    assert.equal(seen[0]!.failingActivationId, 4)
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      ['replacement'],
    )
    assert.equal(result.stats.attempts, 3)
  })

  it('gives combine recovery the exact ScopeResult', async () => {
    const combined: ScopeResult[] = []
    const recovered: ScopeFailure[] = []
    const cause = { combine: true }
    const flow = new Flow(
      node<State>((context) => context.end(4)),
      {
        combine(_context, result) {
          combined.push(result)
          throw cause
        },
        recover(context, failure) {
          recovered.push(failure)
          const total = failure.result!.outputs.reduce<number>((sum, value) => sum + Number(value), 0)
          context.end(total)
        },
      },
    )

    const result = await flow.start({}).result

    assert.equal(result.status, 'completed')
    const scoped = recovered[0]!
    assert.equal(scoped.primary.kind, 'flow_combine')
    assert.equal(scoped.primary.cause, cause)
    assert.equal(scoped.result, combined[0])
    assert.equal(scoped.failingActivationId, null)
    assert.deepEqual(scoped.settledBeforeFence, combined[0]!.terminals)
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      [4],
    )
  })

  it('propagates the exact primary after zero recovery emissions', async () => {
    const seen: ScopeFailure[] = []
    const flow = new Flow(
      node<State>(() => {
        throw new Error('unhandled')
      }),
      {
        recover(_context, failure) {
          seen.push(failure)
        },
      },
    )

    const result = await flow.start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('zero-emission recovery must propagate')
    assert.equal(result.failure, seen[0]!.primary)
    assert.equal(result.suppressed, seen[0]!.suppressed)
    assert.deepEqual(result.terminals, seen[0]!.settledBeforeFence)
  })

  it('replaces the primary when Flow recovery throws', async () => {
    const seen: ScopeFailure[] = []
    const recoveryCause = { recovery: true }
    const flow = new Flow(
      node<State>(() => {
        throw new Error('handler')
      }),
      {
        recover(_context, failure) {
          seen.push(failure)
          throw recoveryCause
        },
      },
    )

    const result = await flow.start({}).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('recovery throw must fail')
    assert.equal(result.failure.kind, 'flow_recovery')
    assert.equal(result.failure.cause, recoveryCause)
    assert.equal(result.failure.attempt, null)
    assert.equal(result.failure.previous, seen[0]!.primary)
    assert.deepEqual(result.suppressed, [])
  })

  it('escalates a nested packet with its exact controlling input', async () => {
    const payload = { job: 8 }
    const childFailures: ScopeFailure[] = []
    const parentFailures: ScopeFailure[] = []
    const child = new Flow(
      node<State, object>((context) => {
        assert.equal(context.input, payload)
        throw new Error('nested')
      }),
      {
        recover(context, failure) {
          assert.equal(context.input, payload)
          childFailures.push(failure)
        },
      },
    )
    const dispatch = node<State>((context) => context.emit('child', payload))
    dispatch.link(child, 'child')
    const parent = new Flow(dispatch, {
      recover(context, failure) {
        assert.equal(context.input, payload)
        parentFailures.push(failure)
        context.end('parent-recovered')
      },
    })

    const result = await parent.start({}).result

    assert.equal(result.status, 'completed')
    assert.equal(parentFailures[0]!.primary, childFailures[0]!.primary)
    assert.equal(childFailures[0]!.failingActivationId, 4)
    assert.equal(parentFailures[0]!.failingActivationId, 3)
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      ['parent-recovered'],
    )
  })

  it('resumes the parent exactly once after nested recovery', async () => {
    let resumes = 0
    const child = new Flow(
      node<State>(() => {
        throw new Error('nested')
      }),
      {
        recover(context) {
          context.emit({ input: 11 })
        },
      },
    )
    child.link(
      node<State, number>((context) => {
        resumes += 1
        context.state.value = context.input
      }),
    )

    const result = await new Flow(child).start({}).result

    assert.equal(result.status, 'completed')
    assert.equal(resumes, 1)
    assert.deepEqual({ ...result.state }, { value: 11 })
  })

  it('delivers a thrown child recovery as one failed Flow to its parent', async () => {
    const childSeen: ScopeFailure[] = []
    const parentSeen: ScopeFailure[] = []
    const child = new Flow(
      node<State>(() => {
        throw new Error('handler')
      }),
      {
        recover(_context, failure) {
          childSeen.push(failure)
          throw new Error('child recovery')
        },
      },
    )
    const parent = new Flow(child, {
      recover(context, failure) {
        parentSeen.push(failure)
        context.end()
      },
    })

    const result = await parent.start({}).result

    assert.equal(result.status, 'completed')
    assert.equal(parentSeen[0]!.primary.kind, 'flow_recovery')
    assert.equal(parentSeen[0]!.primary.previous, childSeen[0]!.primary)
    assert.equal(parentSeen[0]!.failingActivationId, 2)
  })

  it('bypasses parent recovery for an invalid child recovery outcome', async () => {
    let parentCalled = false
    const child = new Flow(
      node<State>(() => {
        throw new Error('handler')
      }),
      {
        recover: (() => Object.create(null)) as (context: Context<State>, failure: ScopeFailure) => void,
      },
    )
    const parent = new Flow(child, {
      recover() {
        parentCalled = true
      },
    })

    const result = await parent.start({}).result

    assert.equal(result.status, 'failed')
    assert.equal(parentCalled, false)
    if (result.status !== 'failed') throw new Error('invalid recovery must fail')
    assert.equal(result.failure.kind, 'invalid_combination')
    assert.equal(result.failure.previous?.kind, 'handler')
  })

  it('keeps producing Flow IDs on nested boundary preflight failures', async () => {
    let parentCalled = false
    const child = new Flow(
      node<State>(() => {}),
      {
        combine(context) {
          context.emit('missing')
        },
      },
    )
    const result = await new Flow(child, {
      recover() {
        parentCalled = true
      },
    }).start({}).result

    assert.equal(result.status, 'failed')
    assert.equal(parentCalled, false)
    if (result.status !== 'failed') throw new Error('unknown combine action must fail')
    assert.equal(result.failure.kind, 'unknown_action')
    assert.equal(result.failure.scopeId, 2)
    assert.equal(result.failure.activationId, 2)
    assert.equal(result.failure.elementId, 2)
    assert.equal(result.failure.attempt, null)

    const recoveryResult = await new Flow(
      node<State>(() => {
        throw new Error('handler')
      }),
      {
        recover(context) {
          context.emit('missing')
        },
      },
    ).start({}).result

    assert.equal(recoveryResult.status, 'failed')
    if (recoveryResult.status !== 'failed') throw new Error('unknown recovery action must fail')
    assert.equal(recoveryResult.failure.kind, 'unknown_action')
    assert.equal(recoveryResult.failure.scopeId, 1)
    assert.equal(recoveryResult.failure.activationId, 1)
    assert.equal(recoveryResult.failure.elementId, 1)
    assert.equal(recoveryResult.failure.attempt, null)
    assert.equal(recoveryResult.failure.previous?.kind, 'handler')
  })

  it('propagates a deep failure without recursive scheduler calls', async () => {
    let element: GraphElement<State> = node<State>(() => {
      throw new Error('deep')
    })
    for (let index = 0; index < 1_500; index += 1) {
      element = new Flow(element, { name: `nested-${index}` })
    }
    const flow = new Flow(element, {
      recover(context, failure) {
        context.state.kind = failure.primary.kind
        context.end()
      },
    })

    const state = await flow.run({}, { maxDepth: 1_501 })

    assert.deepEqual({ ...state }, { kind: 'handler' })
  })
})
