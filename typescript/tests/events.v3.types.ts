import { Flow, node } from '../caskada'

import type { Observer, RunEvent } from '../caskada'

type State = { answer?: string }

const observer: Observer = (event): undefined => {
  const sequence: number = event.sequence
  const runId: string = event.runId
  void sequence
  void runId
  if (event.kind === 'callback_finished') {
    const activationId: number = event.payload.activationId
    void activationId
  }
  return undefined
}

const flow = new Flow(node<State>(() => {}))
const handle = flow.start({}, { observer, runId: 'typed' })
const event = null as RunEvent | null
void handle
void event
