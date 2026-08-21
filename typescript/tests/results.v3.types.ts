import { Flow, node } from '../caskada'

import type { CompletedResult, Context, RunHandle, RunResult } from '../caskada'

interface State {
  answer: string
}

function answer(context: Context<State>): void {
  context.state.answer = 'done'
}

const flow = new Flow(node(answer))
const handle: RunHandle<State> = flow.start({ answer: 'pending' })
const result: Promise<RunResult<State>> = handle.result
const state: Promise<State> = flow.run({ answer: 'pending' })

async function inspectResult(): Promise<void> {
  const settled = await result
  if (settled.status === 'completed') {
    const completed: CompletedResult<State> = settled
    void completed
  }
}

void inspectResult
void state
