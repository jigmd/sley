import { Flow, node } from '../caskada'

import type { Context, RunOptions } from '../caskada'

type State = { visits?: number }

const handler = node<State>((context: Context<State>) => {
  context.state.visits = (context.state.visits ?? 0) + 1
})

const flow = new Flow(handler, { maxActivations: 3 })
const options = {
  maxConcurrency: 2,
  maxActivations: 3,
  maxAttempts: 2,
  maxTransitions: 2,
  maxReady: 2,
  maxReports: 2,
  maxDepth: 2,
} satisfies RunOptions

const projected: Promise<State> = flow.run({}, options)
void projected
