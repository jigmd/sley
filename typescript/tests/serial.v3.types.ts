import { Flow, node } from '../caskada'

import type { Context, ScopeResult } from '../caskada'

interface State {
  count: number
  outputs?: unknown[]
}

interface Job {
  value: number
}

function handler(context: Context<State, Job>): void {
  context.state.count += context.input.value
  context.emit()
  context.emit({ input: { value: 1 } })
  context.emit('next')
  context.emit('next', { value: 2 })
  context.end()
  context.end(undefined)
  // @ts-expect-error undefined is not an unlabelled-input wrapper.
  context.emit(undefined)
}

function combine(context: Context<State>, result: ScopeResult): void {
  context.state.outputs = result.outputs.slice()
}

const flow: Flow<State> = new Flow(node(handler), { combine })
const state: Promise<State> = flow.compile().run({ count: 0 })
void state
