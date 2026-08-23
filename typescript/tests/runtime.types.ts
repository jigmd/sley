import { Flow, node } from '../sley'

import type { Context, Failure, RetryPolicy, RunResult, ScopeFailure, ScopeResult } from '../sley'

interface State {
  total?: number
}

const retry: RetryPolicy = {
  maxAttempts: 2,
  shouldRetry: (_failure: Failure) => true,
  delayMs: (_attempt, _failure) => 0,
}

const source = node<State>((context) => {
  context.emit('work', 1)
  context.emit(undefined, 2)
  context.end()
  context.end(undefined)
  // @ts-expect-error reports are not part of Context
  context.report('removed')
})

const worker = node<State, number>(
  async (context) => {
    context.input satisfies number
    context.end(context.input * 2)
  },
  { retry },
)

source.link(worker, 'work')

function combine(context: Context<State>, result: ScopeResult): void {
  context.state.total = result.outputs.reduce<number>((sum, value) => sum + Number(value), 0)
}

function recover(context: Context<State>, failure: ScopeFailure): void {
  failure.primary.message satisfies string
  context.end()
}

const flow = new Flow(source, { combine, recover })
const handle = flow.start({})
handle.done() satisfies boolean
handle.result() satisfies Promise<RunResult<State>>
flow.compile().describe().schema_version satisfies 1

// @ts-expect-error run-wide scheduler options were removed
flow.start({}, { maxConcurrency: 2 })
