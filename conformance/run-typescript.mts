import { readFileSync } from 'node:fs'
import { Flow, node } from '../typescript/caskada.ts'

import type { Context, RunResult, ScopeFailure, ScopeResult, Terminal } from '../typescript/caskada.ts'

interface State {
  [key: string]: unknown
}

function terminalSnapshot(terminal: Terminal): Record<string, unknown> {
  return {
    type: terminal.type,
    action: terminal.type === 'exit' ? terminal.action : null,
    has_output: terminal.hasOutput,
    output: terminal.hasOutput ? (terminal.output ?? null) : null,
    sequence: terminal.sequence,
    source_activation_id: terminal.sourceActivationId,
  }
}

function resultSnapshot(result: RunResult<State>): Record<string, unknown> {
  return {
    status: result.status,
    state: result.state,
    terminals: result.terminals.map(terminalSnapshot),
    ...(result.status === 'failed'
      ? {
          failure: {
            kind: result.failure.kind,
            attempt: result.failure.attempt,
            previous_kind: result.failure.previous?.kind ?? null,
          },
        }
      : {}),
  }
}

async function implicitLink(): Promise<RunResult<State>> {
  const first = node<State>((context) => {
    context.state.count = 1
  })
  first.link(
    node<State>((context) => {
      context.state.count = Number(context.state.count) + 1
    }),
  )
  return new Flow(first).start({ count: 0 }).result()
}

async function namedInput(): Promise<RunResult<State>> {
  const source = node<State>((context) => context.emit('work', 7))
  source.link(
    node<State, number>((context) => {
      context.state.seen = context.input
    }),
    'work',
  )
  return new Flow(source).start({}).result()
}

async function unlabelledInput(): Promise<RunResult<State>> {
  const source = node<State>((context) => context.emit(undefined, 9))
  source.link(
    node<State, number>((context) => {
      context.state.seen = context.input
    }),
  )
  return new Flow(source).start({}).result()
}

async function fanoutEnds(): Promise<RunResult<State>> {
  const source = node<State>((context) => {
    context.emit('work', 1)
    context.emit('work', 2)
  })
  source.link(
    node<State, number>((context) => context.end(context.input * 10)),
    'work',
  )
  return new Flow(source).start({}).result()
}

async function outputPresence(): Promise<RunResult<State>> {
  return new Flow(
    node<State>((context) => {
      context.end()
      context.end(null)
    }),
  )
    .start({})
    .result()
}

async function combinePreserve(): Promise<RunResult<State>> {
  const source = node<State>((context) => {
    context.emit('work', 1)
    context.emit('work', 2)
  })
  source.link(
    node<State, number>((context) => context.end(context.input)),
    'work',
  )
  return new Flow(source, {
    combine(context, result) {
      context.state.total = result.outputs.reduce<number>((sum, value) => sum + Number(value), 0)
    },
  })
    .start({})
    .result()
}

async function nestedCombine(): Promise<RunResult<State>> {
  const source = node<State>((context) => {
    context.emit('work', 2)
    context.emit('work', 3)
  })
  source.link(
    node<State, number>((context) => context.end(context.input * 10)),
    'work',
  )
  const child = new Flow(source, {
    combine(context, result) {
      context.emit(
        undefined,
        result.outputs.reduce<number>((sum, value) => sum + Number(value), 0),
      )
    },
  })
  child.link(
    node<State, number>((context) => {
      context.state.total = context.input
    }),
  )
  return new Flow(child).start({}).result()
}

async function declaredExit(): Promise<RunResult<State>> {
  const source = node<State>((context) => context.emit('done', 4))
  return new Flow(source, { exits: ['done'] }).start({}).result()
}

async function unknownAction(): Promise<RunResult<State>> {
  return new Flow(node<State>((context) => context.emit('missing'))).start({}).result()
}

async function atomicUnknown(): Promise<RunResult<State>> {
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
  return new Flow(source).start({}).result()
}

async function retry(): Promise<RunResult<State>> {
  let calls = 0
  const work = node<State>(
    (context) => {
      calls++
      context.state.calls = calls
      context.end(`attempt-${calls}`)
      if (calls < 3) throw new Error('retry')
    },
    { retry: { maxAttempts: 3 } },
  )
  return new Flow(work).start({}).result()
}

async function nodeRecovery(): Promise<RunResult<State>> {
  const work = node<State>(
    () => {
      throw new Error('failed')
    },
    { recover: (context) => context.end('recovered') },
  )
  return new Flow(work).start({}).result()
}

async function flowRecovery(): Promise<RunResult<State>> {
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
  return new Flow(source, {
    recover(context, failure) {
      context.state.settled = failure.terminals.map((terminal) => terminal.output)
      context.end('replacement')
    },
  })
    .start({})
    .result()
}

async function combineRecovery(): Promise<RunResult<State>> {
  return new Flow(
    node<State>((context) => context.end(4)),
    {
      combine() {
        throw new Error('combine')
      },
      recover(context, failure) {
        context.state.combine_outputs = [...failure.result!.outputs]
        context.end(failure.result!.outputs.reduce<number>((sum, value) => sum + Number(value), 0))
      },
    },
  )
    .start({})
    .result()
}

async function invalidReturn(): Promise<RunResult<State>> {
  const invalid = (() => 42) as never
  return new Flow(node<State>(invalid)).start({}).result()
}

async function activationLimit(): Promise<RunResult<State>> {
  const looping = node<State>(() => {})
  looping.link(looping)
  return new Flow(looping, { maxActivations: 3 }).start({}).result()
}

async function localConcurrency(): Promise<RunResult<State>> {
  let active = 0
  let release!: () => void
  const gate = new Promise<void>((resolve) => (release = resolve))
  const source = node<State>((context) => {
    for (let value = 0; value < 4; value++) context.emit('work', value)
  })
  source.link(
    node<State, number>(async (context) => {
      active++
      context.state.peak = Math.max(Number(context.state.peak ?? 0), active)
      if (active === 2) release()
      await gate
      active--
    }),
    'work',
  )
  return new Flow(source, { concurrency: 2 }).start({}).result()
}

async function nestedEnd(): Promise<RunResult<State>> {
  const child = new Flow(node<State>((context) => context.end(7)))
  child.link(
    node<State>((context) => {
      context.state.ran = true
    }),
  )
  return new Flow(child).start({}).result()
}

async function nestedFailureTerminals(): Promise<RunResult<State>> {
  const source = node<State>((context) => {
    context.emit(undefined, 1)
    context.emit(undefined, 2)
  })
  source.link(
    node<State, number>((context) => {
      if (context.input === 1) context.end(context.input)
      else throw new Error('failed')
    }),
  )
  return new Flow(new Flow(source), {
    recover(context, failure) {
      context.state.settled = failure.terminals.map((terminal) => terminal.output)
    },
  })
    .start({})
    .result()
}

const cases: Record<string, () => Promise<RunResult<State>>> = {
  implicit_link: implicitLink,
  named_input: namedInput,
  unlabelled_input: unlabelledInput,
  fanout_ends: fanoutEnds,
  output_presence: outputPresence,
  combine_preserve: combinePreserve,
  nested_combine: nestedCombine,
  declared_exit: declaredExit,
  unknown_action: unknownAction,
  atomic_unknown: atomicUnknown,
  retry,
  node_recovery: nodeRecovery,
  flow_recovery: flowRecovery,
  combine_recovery: combineRecovery,
  invalid_return: invalidReturn,
  activation_limit: activationLimit,
  local_concurrency: localConcurrency,
  nested_end: nestedEnd,
  nested_failure_terminals: nestedFailureTerminals,
}

const document = JSON.parse(readFileSync(process.argv[2]!, 'utf8')) as { cases: { id: string }[] }
const ids = document.cases.map((item) => item.id)
if (ids.length !== Object.keys(cases).length || ids.some((id) => cases[id] === undefined)) {
  throw new Error('TypeScript adapter case ids do not match fixture ids')
}

const snapshots = []
for (const id of ids) snapshots.push({ id, snapshot: resultSnapshot(await cases[id]!()) })
const concurrent = snapshots.find((item) => item.id === 'local_concurrency')!.snapshot
const concurrentTerminals = concurrent.terminals as Record<string, unknown>[]
concurrentTerminals.sort((left, right) => Number(left.output) - Number(right.output))
for (const terminal of concurrentTerminals) delete terminal.sequence
process.stdout.write(JSON.stringify(snapshots))
