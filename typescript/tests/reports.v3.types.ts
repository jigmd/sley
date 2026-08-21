import type { Context, RunEvent } from '../caskada'

type State = { answer?: string }

function handler(context: Context<State>): void {
  const omitted: void = context.report('started')
  const explicit: void = context.report('value', undefined)
  void omitted
  void explicit
}

function observer(event: RunEvent): void {
  if (event.kind !== 'report') return
  const name: string = event.payload.name
  const present: boolean = event.payload.hasData
  const data: unknown = event.payload.data
  void name
  void present
  void data
}

void handler
void observer
