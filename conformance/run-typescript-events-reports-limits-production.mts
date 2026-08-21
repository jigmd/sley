import { readFileSync } from 'node:fs'
import { Flow, node } from '../typescript/caskada.ts'

import type { Context, RunEvent, RunResult } from '../typescript/caskada.ts'

const FIXTURE_PATH = new URL('./fixtures/events-reports-limits.json', import.meta.url)
type State = Record<string, unknown>

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalize(item)]),
    )
  }
  return value
}

async function successfulTrace(): Promise<Record<string, unknown>> {
  const events: RunEvent[] = []
  const first = node<State>((context) => context.emit('next', 7), { name: 'first' })
  const second = node<State, number>((context) => context.end(context.input), { name: 'second' })
  first.link(second, 'next')
  const result = await new Flow(first).start(
    {},
    {
      observer(event) {
        events.push(event)
      },
      runId: 'fixture-events',
    },
  ).result
  const transitions = events.filter((event) => event.kind === 'transition_committed')
  const terminal = events.find((event) => event.kind === 'terminal_committed')
  const endDestination = transitions[1]?.payload.transition.destination
  if (transitions.length !== 2 || terminal?.kind !== 'terminal_committed' || endDestination?.type !== 'terminal') {
    throw new Error('trace fixture is incomplete')
  }
  return {
    status: result.status,
    run_ids: [...new Set(events.map((event) => event.runId))].sort(),
    sequences: events.map((event) => event.sequence),
    kinds: events.map((event) => event.kind),
    route_destination: transitions[0]!.payload.transition.destination.type,
    end_terminal_sequence: endDestination.sequence,
    committed_terminal_sequence: terminal.payload.terminalSequence,
  }
}

async function observerSkip(): Promise<Record<string, unknown>> {
  const events: RunEvent[] = []
  let calls = 0
  let handle: ReturnType<Flow<State>['start']>
  const handler = node<State>(
    () => {
      calls += 1
    },
    { name: 'work' },
  )
  handle = new Flow(handler).start(
    {},
    {
      observer(event) {
        events.push(event)
        if (event.kind === 'callback_started') handle.cancel('observer')
      },
    },
  )
  const result = await handle.result
  return {
    status: result.status,
    calls,
    kinds: events.map((event) => event.kind),
    attempts: result.stats.attempts,
  }
}

async function observerThrow(): Promise<Record<string, unknown>> {
  let calls = 0
  const result = await new Flow(node<State>(() => undefined, { name: 'work' })).start(
    {},
    {
      observer() {
        calls += 1
        throw new Error('observer')
      },
    },
  ).result
  const diagnostic = result.diagnostics[0]!
  return {
    status: result.status,
    calls,
    diagnostic_count: result.diagnostics.length,
    diagnostic: { event_sequence: diagnostic.eventSequence, message: diagnostic.message },
  }
}

async function reportPresence(): Promise<Record<string, unknown>> {
  const events: RunEvent[] = []
  const handler = node<State>(
    (context) => {
      context.report('started')
      context.report('value', null)
    },
    { name: 'work' },
  )
  const result = await new Flow(handler).start(
    {},
    {
      observer(event) {
        events.push(event)
      },
    },
  ).result
  const reports = events
    .filter((event) => event.kind === 'report')
    .map((event) =>
      event.payload.hasData
        ? { name: event.payload.name, has_data: true, data: event.payload.data }
        : { name: event.payload.name, has_data: false },
    )
  return { status: result.status, reports, report_count: result.stats.reports }
}

async function reportReentrant(): Promise<Record<string, unknown>> {
  const events: RunEvent[] = []
  let active: Context<State> | undefined
  const handler = node<State>(
    (context) => {
      active = context
      context.report('outer')
    },
    { name: 'work' },
  )
  const result = await new Flow(handler).start(
    {},
    {
      observer(event) {
        events.push(event)
        if (event.kind === 'report') active!.report('nested')
      },
    },
  ).result
  const diagnostic = result.diagnostics[0]!
  return {
    status: result.status,
    published_reports: events.filter((event) => event.kind === 'report').length,
    report_count: result.stats.reports,
    diagnostic: { event_sequence: diagnostic.eventSequence, message: diagnostic.message },
  }
}

async function reportOverflow(): Promise<Record<string, unknown>> {
  const events: RunEvent[] = []
  let caught = 0
  const handler = node<State>(
    (context) => {
      context.report('first')
      for (const name of ['overflow', 'already_fenced']) {
        try {
          context.report(name)
        } catch {
          caught += 1
        }
      }
    },
    { name: 'work' },
  )
  const result = await new Flow(handler).start(
    {},
    {
      maxReports: 1,
      observer(event) {
        events.push(event)
      },
    },
  ).result
  return normalizeLimit(result, {
    caught,
    published_reports: events.filter((event) => event.kind === 'report').length,
    failure_fences: events.filter((event) => event.kind === 'failure_fenced').length,
  })
}

async function transitionOverflow(): Promise<Record<string, unknown>> {
  const events: RunEvent[] = []
  let caught = false
  let caughtKinds: string[] = []
  const controlKinds = (): string[] => {
    const selected = new Set(['callback_finished', 'cancellation_fenced', 'failure_fenced', 'failure_recorded', 'run_finished'])
    return events
      .filter((event) => selected.has(event.kind))
      .map((event) =>
        event.kind === 'failure_fenced' || event.kind === 'cancellation_fenced'
          ? `${event.kind}:${event.payload.target.kind}`
          : event.kind,
      )
  }
  const source = node<State>(
    (context) => {
      context.emit('next', 1)
      try {
        context.emit('next', 2)
      } catch {
        caught = true
        caughtKinds = controlKinds()
      }
    },
    { name: 'source' },
  )
  source.link(
    node<State>(() => undefined, { name: 'target' }),
    'next',
  )
  const result = await new Flow(source).start(
    {},
    {
      maxTransitions: 1,
      observer(event) {
        events.push(event)
      },
    },
  ).result
  return normalizeLimit(result, { caught, caught_kinds: caughtKinds, control_order: controlKinds() })
}

async function capacityPriority(): Promise<Record<string, unknown>> {
  const source = node<State>((context) => context.emit('next'), { name: 'source' })
  source.link(
    node<State>(() => undefined, { name: 'target' }),
    'next',
  )
  return normalizeLimit(await new Flow(source, { maxActivations: 1 }).start({}, { maxActivations: 2, maxReady: 1 }).result)
}

async function depthLimit(): Promise<Record<string, unknown>> {
  const source = node<State>((context) => context.emit('child'), { name: 'source' })
  source.link(
    new Flow(
      node<State>(() => undefined, { name: 'entry' }),
      { name: 'child' },
    ),
    'child',
  )
  return normalizeLimit(await new Flow(source).start({}, { maxDepth: 1 }).result)
}

async function attemptLimit(): Promise<Record<string, unknown>> {
  const calls: string[] = []
  const source = node<State>(
    (context) => {
      calls.push('source')
      context.emit('next')
    },
    { name: 'source' },
  )
  source.link(
    node<State>(
      () => {
        calls.push('target')
      },
      { name: 'target' },
    ),
    'next',
  )
  return normalizeLimit(await new Flow(source).start({}, { maxAttempts: 1 }).result, { calls })
}

function normalizeLimit(result: RunResult<State>, observations: Record<string, unknown> = {}): Record<string, unknown> {
  if (result.status !== 'failed') throw new Error('limit fixture must fail')
  const detail = result.failure.detail
  if (detail?.type !== 'limit') throw new Error('limit fixture requires LimitDetail')
  return {
    status: result.status,
    failure: {
      kind: result.failure.kind,
      limit: detail.limit,
      attempt: result.failure.attempt,
      scope_id: result.failure.scopeId,
      activation_id: result.failure.activationId,
    },
    terminal_count: result.terminals.length,
    observations,
    stats: {
      activations: result.stats.activations,
      attempts: result.stats.attempts,
      transitions: result.stats.transitions,
      reports: result.stats.reports,
      peak_ready: result.stats.peakReady,
      scopes: result.stats.scopes,
    },
  }
}

async function runProgram(scenario: string): Promise<Record<string, unknown>> {
  const runners: Record<string, () => Promise<Record<string, unknown>>> = {
    successful_trace: successfulTrace,
    observer_skip: observerSkip,
    observer_throw: observerThrow,
    report_presence: reportPresence,
    report_reentrant: reportReentrant,
    report_overflow: reportOverflow,
    transition_overflow: transitionOverflow,
    capacity_priority: capacityPriority,
    depth_limit: depthLimit,
    attempt_limit: attemptLimit,
  }
  const runner = runners[scenario]
  if (runner === undefined) throw new Error(`unknown events/reports/limits scenario ${scenario}`)
  return runner()
}

const collection = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8')) as {
  readonly fixtures: ReadonlyArray<{ readonly id: string; readonly program: { readonly scenario: string } }>
}
const fixtures = []
for (const fixture of collection.fixtures) {
  fixtures.push({ id: fixture.id, snapshot: await runProgram(fixture.program.scenario) })
}
process.stdout.write(JSON.stringify(canonicalize({ schema_version: 1, fixtures })) + '\n')
