import { Flow, node } from '../caskada'

import type { AbandonedResult, Context, RunOptions, RunResult } from '../caskada'

type State = { value?: number }

async function handler(context: Context<State>): Promise<void> {
  const remaining: number | undefined = context.remainingMs()
  if (remaining === 0) context.cancellation.throwIfCancelled()
}

const flow = new Flow(node(handler, { timeoutMs: 10 }))
const options: RunOptions = { deadlineMs: 20, cancelGraceMs: 5, runId: 'typed-run' }
const handle = flow.start({}, options)

async function inspectResult(): Promise<void> {
  const result: RunResult<State> = await handle.result
  if (result.status === 'abandoned') {
    const abandoned: AbandonedResult<State> = result
    void abandoned.cause
  }
}

void inspectResult
