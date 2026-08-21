import { Flow, node } from '../caskada'

import type { Context, RunEvent, ScopeResult } from '../caskada'

type State = { total?: number; value?: number }

type BrowserGlobals = typeof globalThis & {
  __caskadaV3BrowserResult?: Record<string, unknown>
  __caskadaV3BrowserError?: string
}

void (async () => {
  const reportNames: string[] = []
  const dispatch = node<State>((context) => {
    context.emit('work', 1)
    context.emit('work', 2)
  })
  const worker = node<State, number>(async (context) => {
    await Promise.resolve()
    context.end(context.input * 2)
  })
  dispatch.link(worker, 'work')

  function combine(context: Context<State>, result: ScopeResult): void {
    context.state.total = result.outputs.reduce<number>((sum, output) => sum + Number(output), 0)
    context.report('combined')
  }

  const events: RunEvent[] = []
  const result = await new Flow(dispatch, { combine, concurrency: 2 }).start(
    {},
    {
      observer(event) {
        events.push(event)
        if (event.kind === 'report') reportNames.push(event.payload.name)
      },
    },
  ).result

  const projected = await new Flow(
    node<State>((context) => {
      context.state.value = 7
    }),
  ).run({})

  ;(globalThis as BrowserGlobals).__caskadaV3BrowserResult = {
    status: result.status,
    total: result.state.total,
    outputs: result.terminals.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.output),
    terminalCount: result.terminals.length,
    reportNames,
    projectedValue: projected.value,
    processType: typeof (globalThis as { process?: unknown }).process,
  }
})().catch((error: unknown) => {
  ;(globalThis as BrowserGlobals).__caskadaV3BrowserError = error instanceof Error ? (error.stack ?? error.message) : String(error)
})
