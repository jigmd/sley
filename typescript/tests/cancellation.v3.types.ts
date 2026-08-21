import { Flow, node } from '../caskada'

import type { Cancellation, CancelledResult, Context, RunResult } from '../caskada'

type State = { value?: number }

async function handler(context: Context<State>): Promise<void> {
  const token: Cancellation = context.cancellation
  if (!token.cancelled) {
    await new Promise<void>((resolve) => token.signal.addEventListener('abort', () => resolve(), { once: true }))
  }
  token.throwIfCancelled()
}

const flow = new Flow(node(handler))
const handle = flow.start({})
handle.cancel('stop')

async function inspectResult(): Promise<void> {
  const result: RunResult<State> = await handle.result
  if (result.status === 'cancelled') {
    const cancelled: CancelledResult<State> = result
    const deadline: boolean = cancelled.cancellation.deadline
    void deadline
  }
}

void inspectResult
