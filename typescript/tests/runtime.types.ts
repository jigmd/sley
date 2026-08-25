import { Flow, node } from '../sley'

import type {
  CompiledDescription,
  Context,
  DescriptionElement,
  DescriptionFlow,
  DescriptionLink,
  DescriptionNode,
  DescriptionRoot,
  DescriptionScope,
  Failure,
  RetryPolicy,
  RunResult,
  ScopeFailure,
  ScopeResult,
} from '../sley'

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
const description = flow.compile().describe()
description satisfies CompiledDescription
description.schema_version satisfies 1
description.root satisfies DescriptionRoot
description.scopes[0]! satisfies DescriptionScope
const element = description.elements[0]!
element satisfies DescriptionElement
element.links[0]! satisfies DescriptionLink
if (element.kind === 'node') {
  element satisfies DescriptionNode
  element.max_attempts satisfies number
} else {
  element satisfies DescriptionFlow
  element.owned_scope_id satisfies number
}

// @ts-expect-error run-wide scheduler options were removed
flow.start({}, { maxConcurrency: 2 })
