import { Flow, node } from '../caskada'

import type { Context, ScopeFailure, ScopeResult } from '../caskada'

type State = { count?: number }

const worker = node<State, number>((context) => context.end(context.input))

function combine(context: Context<State>, result: ScopeResult): void {
  context.state.count = result.outputs.length
}

function recover(context: Context<State>, failure: ScopeFailure): void {
  if (failure.result !== null) context.end(failure.result.outputs.length)
  else if (failure.failingActivationId !== null) context.end(failure.primary.failureId)
}

const flow: Flow<State> = new Flow(worker, { combine, recover })
void flow
