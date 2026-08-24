import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import * as sley from '../sley'
import { DuplicateLinkError, Flow, GraphDefinitionError, node, RunError } from '../sley'

import type { Context, ScopeFailure, ScopeResult } from '../sley'

interface State {
  [key: string]: unknown
  count?: number
  nested?: string[]
}

describe('graph definitions', () => {
  it('exports only the intentional runtime values', () => {
    assert.deepEqual(Object.keys(sley).sort(), [
      'DuplicateLinkError',
      'Flow',
      'GraphDefinitionError',
      'GraphElement',
      'Node',
      'RunError',
      'SleyError',
      'node',
    ])
  })

  it('creates named node occurrences and validates options', () => {
    function handler(_context: Context<State>): void {}
    assert.equal(node(handler).name, 'handler')
    assert.equal(node(handler, { name: 'configured' }).name, 'configured')
    assert.throws(() => node(handler, { name: '' }), GraphDefinitionError)
    assert.throws(() => node(handler, { recover: 1 as never }), GraphDefinitionError)
    assert.throws(() => node(handler, { unknown: true } as never), GraphDefinitionError)
    assert.throws(() => node(handler, { retry: { maxAttempts: 0 } }), GraphDefinitionError)
  })

  it('keeps target-first links ordered and unique', () => {
    const source = node<State>(() => {})
    const unlabelled = node<State>(() => {}, { name: 'unlabelled' })
    const named = node<State>(() => {}, { name: 'named' })
    source.link(unlabelled)
    source.link(named, 'review')

    assert.deepEqual(
      source.links().map((link) => [link.action, link.target.name]),
      [
        [null, 'unlabelled'],
        ['review', 'named'],
      ],
    )
    assert.throws(() => source.link(node<State>(() => {})), DuplicateLinkError)
    assert.throws(
      () =>
        source.link(
          node<State>(() => {}),
          'review',
        ),
      DuplicateLinkError,
    )
    assert.throws(
      () =>
        source.link(
          node<State>(() => {}),
          '',
        ),
      GraphDefinitionError,
    )
    assert.throws(() => source.link({} as never), GraphDefinitionError)
  })

  it('captures and validates Flow configuration', () => {
    const entry = node<State>(() => {})
    const exits = ['done']
    const flow = new Flow(entry, { name: 'batch', exits, concurrency: 3, maxActivations: 10 })
    exits.push('later')

    assert.equal(flow.name, 'batch')
    assert.deepEqual(flow.exits, ['done'])
    assert.equal(flow.concurrency, 3)
    assert.equal(flow.maxActivations, 10)
    assert.throws(() => new Flow(entry, { exits: ['done', 'done'] }), GraphDefinitionError)
    assert.throws(() => new Flow(entry, { concurrency: 0 }), GraphDefinitionError)
    assert.throws(() => new Flow(entry, { maxActivations: 0 }), GraphDefinitionError)
    assert.throws(() => new Flow(entry, { unknown: true } as never), GraphDefinitionError)
  })

  it('rejects recursive Flow containment', () => {
    const entry = node<State>(() => {})
    const recursive = new Flow(entry)
    entry.link(recursive)
    assert.throws(() => recursive.compile(), GraphDefinitionError)
  })

  it('snapshots topology and returns fresh descriptions', () => {
    const entry = node<State>(() => {}, { name: 'entry' })
    entry.link(node<State>(() => {}, { name: 'first' }))
    const compiled = new Flow(entry, { name: 'root' }).compile()
    const before = compiled.describe()

    entry.link(
      node<State>(() => {}, { name: 'later' }),
      'later',
    )
    assert.deepEqual(compiled.describe(), before)
    assert.notDeepEqual(new Flow(entry).compile().describe(), before)

    ;(before.elements as Record<string, unknown>[]).length = 0
    assert.notEqual(compiled.describe().elements.length, 0)
  })
})

describe('state, input, and control', () => {
  it('uses one shallow-copied state object per run', async () => {
    const initial: State = { count: 0, nested: [] }
    const seen: State[] = []
    const first = node<State>((context) => {
      seen.push(context.state)
      context.state.count = 1
    })
    first.link(
      node<State>((context) => {
        seen.push(context.state)
        context.state.count! += 1
        context.state.nested!.push('shared')
      }),
    )

    const state = await new Flow(first).run(initial)
    assert.deepEqual(state, { count: 2, nested: ['shared'] })
    assert.equal(seen[0], seen[1])
    assert.notEqual(state, initial)
    assert.deepEqual(initial, { count: 0, nested: ['shared'] })
  })

  it('rejects non-record state and symbol keys before callbacks', () => {
    let calls = 0
    const flow = new Flow(node<State>(() => void calls++))
    assert.throws(() => flow.start([] as never), TypeError)
    assert.throws(() => flow.start(new Map() as never), /plain object/)
    assert.throws(() => flow.start(new Date() as never), /plain object/)
    assert.throws(() => flow.start({ [Symbol('key')]: true } as never), TypeError)
    assert.equal(calls, 0)
  })

  it('preserves a state field named then through Promise resolution', async () => {
    const then = () => 'application value'
    const state = await new Flow(node<{ then: unknown }>(() => {})).run({ then })
    assert.equal(state.then, then)
  })

  it('settles run when a handler freezes ordinary state', async () => {
    const state = await new Flow(
      node<Record<string, unknown>>((context) => {
        Object.freeze(context.state)
      }),
    ).run({})
    assert.equal(Object.isFrozen(state), true)
  })

  it('rejects an immutable callable then state instead of hanging', async () => {
    const then = () => 'application value'
    const flow = new Flow(
      node<{ then: unknown }>((context) => {
        Object.freeze(context.state)
      }),
    )
    await assert.rejects(flow.run({ then }), /callable then property must remain mutable/)
  })

  it('replaces and forwards branch input', async () => {
    const seen: unknown[] = []
    const producer = node<State>((context) => context.emit('work', { value: 7 }))
    const forwarding = node<State, unknown>((context) => {
      seen.push(context.input)
      context.emit()
    })
    const consumer = node<State, unknown>((context) => {
      seen.push(context.input)
      context.state.value = context.input
    })
    producer.link(forwarding, 'work')
    forwarding.link(consumer)

    const state = await new Flow(producer).run({})
    assert.deepEqual(state.value, { value: 7 })
    assert.equal(seen[0], seen[1])
  })

  it('replaces unlabelled input without an object wrapper', async () => {
    const producer = node<State>((context) => context.emit(undefined, 9))
    producer.link(
      node<State, number>((context) => {
        context.state.value = context.input
      }),
    )
    assert.deepEqual(await new Flow(producer).run({}), { value: 9 })
  })

  it('makes silent handlers follow the unlabelled link', async () => {
    const first = node<State>(() => {})
    first.link(
      node<State>((context) => {
        context.state.ran = true
      }),
    )
    assert.deepEqual(await new Flow(first).run({}), { ran: true })
  })

  it('makes end bypass links and distinguish omitted output', async () => {
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
    const result = await new Flow(finish, { combine: (_context, scope) => void observed.push(scope) }).start({}).result()

    assert.equal('ran' in result.state, false)
    assert.deepEqual(observed[0]!.outputs, [undefined])
    assert.deepEqual(
      result.terminals.map((terminal) => [terminal.hasOutput, terminal.output]),
      [
        [false, undefined],
        [true, undefined],
      ],
    )
  })

  it('closes Context after callback settlement', async () => {
    let retained!: Context<State>
    await new Flow(node<State>((context) => void (retained = context))).run({})
    assert.throws(() => retained.emit(), /closed/)
    assert.throws(() => retained.state, /closed/)
  })
})

describe('Flow completion', () => {
  it('fans out and combines output-bearing terminals', async () => {
    const dispatch = node<State>((context) => {
      for (const value of [1, 2, 3]) context.emit('work', value)
    })
    dispatch.link(
      node<State, number>((context) => context.end(context.input * 10)),
      'work',
    )
    const result = await new Flow(dispatch, {
      combine(context, scope) {
        context.state.outputs = scope.outputs
      },
    })
      .start({})
      .result()

    assert.deepEqual(result.state.outputs, [10, 20, 30])
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      [10, 20, 30],
    )
  })

  it('lets combine replace nested terminals with one message', async () => {
    const dispatch = node<State>((context) => {
      context.emit('work', 2)
      context.emit('work', 3)
    })
    dispatch.link(
      node<State, number>((context) => context.end(context.input * 10)),
      'work',
    )
    const child = new Flow(dispatch, {
      combine(context, scope) {
        context.emit(
          undefined,
          scope.outputs.reduce<number>((sum, value) => sum + Number(value), 0),
        )
      },
    })
    child.link(
      node<State, number>((context) => {
        context.state.total = context.input
      }),
    )

    assert.deepEqual(await new Flow(child).run({}), { total: 50 })
  })

  it('accepts declared exits and fails unknown actions', async () => {
    const exit = node<State>((context) => context.emit('done', 4))
    const completed = await new Flow(exit, { exits: ['done'] }).start({}).result()
    assert.equal(completed.status, 'completed')
    assert.equal(completed.terminals[0]!.type, 'exit')

    const failed = await new Flow(exit).start({}).result()
    assert.equal(failed.status, 'failed')
    if (failed.status === 'failed') assert.equal(failed.failure.kind, 'unknown_action')
  })

  it('rejects an entire control batch when one route is unknown', async () => {
    const source = node<State>((context) => {
      context.emit('valid', 1)
      context.emit('missing', 2)
    })
    source.link(
      node<State, number>((context) => {
        context.state.ran = context.input
      }),
      'valid',
    )
    const result = await new Flow(source).start({}).result()

    assert.equal(result.status, 'failed')
    assert.equal('ran' in result.state, false)
    assert.deepEqual(result.terminals, [])
  })

  it('discards buffered control when a handler throws', async () => {
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
    const result = await new Flow(source).start({}).result()

    assert.equal(result.status, 'failed')
    assert.equal('ran' in result.state, false)
    if (result.status === 'failed') assert.equal(result.failure.cause, cause)
  })

  it('treats a non-undefined callback return as invalid', async () => {
    const invalid = (() => 42) as never
    const result = await new Flow(node<State>(invalid)).start({}).result()
    assert.equal(result.status, 'failed')
    if (result.status === 'failed') assert.equal(result.failure.kind, 'invalid_outcome')
  })
})

describe('results, retry, and recovery', () => {
  it('defers start and returns one stable result', async () => {
    let calls = 0
    const handle = new Flow(
      node<State>((context) => {
        context.state.handled = true
        calls++
      }),
    ).start({})
    assert.equal(handle.done(), false)
    assert.equal(calls, 0)
    const first = await handle.result()
    const second = await handle.result()
    assert.equal(handle.done(), true)
    assert.equal(first, second)
    assert.deepEqual(first.state, { handled: true })
    assert.equal(calls, 1)
  })

  it('projects state or throws RunError with the exact failure', async () => {
    assert.deepEqual(
      await new Flow(
        node<State>((context) => {
          context.state.value = 1
        }),
      ).run({}),
      { value: 1 },
    )
    const cause = new Error('failed')
    await assert.rejects(
      new Flow(
        node<State>(() => {
          throw cause
        }),
      ).run({}),
      (error: unknown) => error instanceof RunError && error.result.failure.cause === cause,
    )
  })

  it('reuses compiled topology with fresh state', async () => {
    const compiled = new Flow(node<State>(() => {})).compile()
    const first = await compiled.run({ value: 1 })
    const second = await compiled.run({ value: 2 })
    assert.deepEqual(first, { value: 1 })
    assert.deepEqual(second, { value: 2 })
    assert.notEqual(first, second)
  })

  it('retries with the same input and discards failed buffers', async () => {
    let calls = 0
    const payload = {}
    const inputs: unknown[] = []
    const worker = node<State, object>(
      (context) => {
        calls++
        inputs.push(context.input)
        context.state.calls = calls
        context.end(`attempt-${calls}`)
        if (calls < 3) throw new Error('retry')
      },
      { retry: { maxAttempts: 3 } },
    )
    const dispatch = node<State>((context) => context.emit('work', payload))
    dispatch.link(worker, 'work')
    const result = await new Flow(dispatch).start({}).result()

    assert.deepEqual(result.state, { calls: 3 })
    assert.deepEqual(
      result.terminals.map((terminal) => terminal.output),
      ['attempt-3'],
    )
    assert.deepEqual(inputs, [payload, payload, payload])
  })

  it('lets a predicate decline retry and node recovery resume', async () => {
    const worker = node<State>(
      () => {
        throw new Error('declined')
      },
      {
        retry: { maxAttempts: 3, shouldRetry: () => false },
        recover: (context) => context.emit('resume', 9),
      },
    )
    worker.link(
      node<State, number>((context) => {
        context.state.value = context.input
      }),
      'resume',
    )
    assert.deepEqual(await new Flow(worker).run({}), { value: 9 })
  })

  it('turns a retry policy throw into a replacement failure', async () => {
    const policyError = new Error('policy')
    const worker = node<State>(
      () => {
        throw new Error('handler')
      },
      {
        retry: {
          maxAttempts: 2,
          shouldRetry() {
            throw policyError
          },
        },
      },
    )
    const result = await new Flow(worker).start({}).result()
    assert.equal(result.status, 'failed')
    if (result.status === 'failed') {
      assert.equal(result.failure.kind, 'retry_policy')
      assert.equal(result.failure.cause, policyError)
      assert.equal(result.failure.previous!.kind, 'handler')
    }
  })

  it('captures thrown non-Error values without coercing the cause', async () => {
    const cause = { reason: 'application value' }
    const result = await new Flow(
      node<State>(() => {
        throw cause
      }),
    )
      .start({})
      .result()
    assert.equal(result.status, 'failed')
    if (result.status === 'failed') assert.equal(result.failure.cause, cause)
  })

  it('gives Flow recovery settled terminals', async () => {
    const seen: ScopeFailure[] = []
    const source = node<State>((context) => {
      context.emit('done', 1)
      context.emit('fail', 2)
      context.emit('late', 3)
    })
    source.link(
      node<State, number>((context) => context.end(context.input)),
      'done',
    )
    source.link(
      node<State>(() => {
        throw new Error('failed')
      }),
      'fail',
    )
    source.link(
      node<State>((context) => {
        context.state.late = true
      }),
      'late',
    )
    const result = await new Flow(source, {
      recover(context, failure) {
        seen.push(failure)
        context.end('replacement')
      },
    })
      .start({})
      .result()

    assert.equal('late' in result.state, false)
    assert.deepEqual(
      seen[0]!.terminals.map((terminal) => terminal.output),
      [1],
    )
    assert.equal(result.terminals[0]!.output, 'replacement')
  })

  it('gives combine recovery the exact ScopeResult', async () => {
    let combined!: ScopeResult
    let recovered!: ScopeFailure
    const result = await new Flow(
      node<State>((context) => context.end(4)),
      {
        combine(_context, scope) {
          combined = scope
          throw new Error('combine')
        },
        recover(context, failure) {
          recovered = failure
          context.end(Number(failure.result!.outputs[0]))
        },
      },
    )
      .start({})
      .result()

    assert.equal(recovered.result, combined)
    assert.equal(recovered.primary.kind, 'flow_combine')
    assert.equal(result.terminals[0]!.output, 4)
  })
})

describe('local scheduling', () => {
  it('honors Flow-local concurrency', async () => {
    let active = 0
    let peak = 0
    let release!: () => void
    const gate = new Promise<void>((resolve) => (release = resolve))
    let started!: () => void
    const enoughStarted = new Promise<void>((resolve) => (started = resolve))
    const dispatch = node<State>((context) => {
      for (let value = 0; value < 4; value++) context.emit('work', value)
    })
    dispatch.link(
      node<State, number>(async (context) => {
        active++
        peak = Math.max(peak, active)
        if (active === 2) started()
        await gate
        active--
        context.end(context.input)
      }),
      'work',
    )

    const handle = new Flow(dispatch, { concurrency: 2 }).start({})
    await enoughStarted
    release()
    const result = await handle.result()
    assert.equal(peak, 2)
    assert.equal(result.terminals.length, 4)
  })

  it('keeps serial Flow callbacks from overlapping', async () => {
    let active = 0
    let peak = 0
    const dispatch = node<State>((context) => {
      context.emit('work', 1)
      context.emit('work', 2)
    })
    dispatch.link(
      node<State>(async () => {
        active++
        peak = Math.max(peak, active)
        await Promise.resolve()
        active--
      }),
      'work',
    )
    await new Flow(dispatch).run({})
    assert.equal(peak, 1)
  })

  it('stops a cycle at maxActivations', async () => {
    const looping = node<State>(() => {})
    looping.link(looping)
    const result = await new Flow(looping, { maxActivations: 3 }).start({}).result()
    assert.equal(result.status, 'failed')
    if (result.status === 'failed') assert.equal(result.failure.kind, 'activation_limit')
  })
})
