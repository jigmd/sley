import { Flow, node } from '../caskada'

import type { Context, Failure, RetryOptions } from '../caskada'

type State = { value?: number }

const retry: RetryOptions = {
  maxAttempts: 3,
  shouldRetry(failure: Failure) {
    return failure.kind === 'handler'
  },
  delayMs(failedAttempt: number, failure: Failure) {
    return failure.attempt === null ? 0 : failedAttempt
  },
}

const worker = node<State, number>(
  (context: Context<State, number>) => {
    const attempt: number = context.attempt!
    context.end(context.input + attempt)
  },
  {
    retry,
    recover(context: Context<State, number>, failure: Failure) {
      const attempt: number | null = context.attempt
      context.end(failure.failureId + (attempt ?? 0))
    },
  },
)

const flow: Flow<State> = new Flow(worker)
void flow
