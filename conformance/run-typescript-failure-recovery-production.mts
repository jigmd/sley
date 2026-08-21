import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Flow, node } from '../typescript/caskada.ts'

import type { Context, Failure, RunEvent, ScopeFailure, ScopeResult, Terminal } from '../typescript/caskada.ts'
import type { FailureRecoveryProgram } from './failure-recovery-reference.mts'

type State = Record<string, unknown>
type Fixture = { id: string; program: FailureRecoveryProgram }

class FixtureRuntime {
  readonly events: RunEvent[] = []

  constructor(private readonly program: FailureRecoveryProgram) {}

  build(): Flow<State> {
    const worker = node<State>(this.handle.bind(this), {
      name: 'worker',
      retry: { maxAttempts: this.program.retry_max_attempts },
      ...(this.program.node_recovery === 'none' ? {} : { recover: this.nodeRecover.bind(this) }),
    })
    if (this.program.topology === 'root_node') return new Flow(worker, { name: 'root' })
    if (this.program.topology === 'node_after_source') {
      const source = node<State>(this.source.bind(this), { name: 'source' })
      source.link(worker)
      return new Flow(source, { name: 'root' })
    }
    if (this.program.topology === 'nested_flow') {
      const child = new Flow(worker, { name: 'child', recover: this.flowRecover.bind(this) })
      const source = node<State>(this.source.bind(this), { name: 'source' })
      source.link(child)
      return new Flow(source, { name: 'root' })
    }
    if (this.program.topology === 'combine') {
      return new Flow(worker, { name: 'root', combine: this.combine.bind(this), recover: this.flowRecover.bind(this) })
    }
    throw new Error(`unknown topology ${String(this.program.topology)}`)
  }

  private source(context: Context<State>): void {
    context.emit({ input: this.program.input })
  }

  private handle(context: Context<State>): void {
    const attempts = Number(context.state.handler_attempts ?? 0) + 1
    context.state.handler_attempts = attempts
    if (this.program.handler === 'fail' || (this.program.handler === 'fail_once_then_end' && attempts === 1)) {
      throw new Error('handler')
    }
    if (this.program.handler === 'end') context.end(this.program.input)
    else context.end(this.program.output)
  }

  private nodeRecover(context: Context<State>, failure: Failure): void {
    const observation: Record<string, unknown> = { failure_id: failure.failureId, kind: failure.kind }
    if (this.program.topology === 'node_after_source') observation.input = context.input
    context.state.node_recovery = observation
    if (this.program.node_recovery === 'end') context.end(this.program.output)
    else if (this.program.node_recovery === 'throw') throw new Error('node_recovery')
  }

  private combine(_context: Context<State>, _result: ScopeResult): never {
    throw new Error('combine')
  }

  private flowRecover(context: Context<State>, failure: ScopeFailure): void {
    const observation: Record<string, unknown> = {
      failure_id: failure.primary.failureId,
      kind: failure.primary.kind,
      failing_activation_id: failure.failingActivationId,
      settled_outputs: failure.settledBeforeFence.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.output),
      result_outputs: failure.result === null ? null : Array.from(failure.result.outputs),
    }
    if (this.program.topology === 'nested_flow') observation.input = context.input
    context.state.flow_recovery = observation
    if (this.program.flow_recovery === 'end') context.end(this.program.output)
    else if (this.program.flow_recovery === 'throw') throw new Error('flow_recovery')
  }
}

const fixtureUrl = new URL('./fixtures/failure-recovery.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as { schema_version: number; fixtures: Fixture[] }
assert.equal(collection.schema_version, 1, 'unsupported failure fixture schema')

const fixtures = []
for (const fixture of collection.fixtures) fixtures.push(await runFixture(fixture))
console.log(JSON.stringify(canonicalize({ schema_version: 1, fixtures })))

async function runFixture(fixture: Fixture): Promise<Record<string, unknown>> {
  const runtime = new FixtureRuntime(fixture.program)
  const compiled = runtime.build().compile()
  const names = new Map(compiled.describe().elements.map((element) => [element.element_id, element.name]))
  const result = await compiled.start(
    {},
    {
      observer(event): undefined {
        runtime.events.push(event)
        return undefined
      },
    },
  ).result
  const normalizedResult: Record<string, unknown> = {
    status: result.status,
    state: Object.fromEntries(Object.entries(result.state)),
    terminals: result.terminals.map(normalizeTerminal),
  }
  if (result.status === 'failed') {
    normalizedResult.failure = normalizeFailure(result.failure, names)
    normalizedResult.suppressed = result.suppressed.map((failure) => normalizeFailure(failure, names))
  }
  const failures = runtime.events
    .filter((event) => event.kind === 'failure_recorded')
    .map((event) => normalizeFailure(event.payload.failure, names))
  const retries = runtime.events
    .filter((event) => event.kind === 'retry_scheduled')
    .map((event) => ({
      failure_id: event.payload.failureId,
      failed_attempt: event.payload.failedAttempt,
      next_attempt: event.payload.nextAttempt,
      delay_ms: event.payload.delayMs,
    }))
  return {
    id: fixture.id,
    snapshot: {
      result: normalizedResult,
      trace: { failures, retries },
      stats: {
        activations: result.stats.activations,
        attempts: result.stats.attempts,
        transitions: result.stats.transitions,
        retries: result.stats.retries,
        scopes: result.stats.scopes,
      },
    },
  }
}

function normalizeFailure(failure: Failure, names: ReadonlyMap<number, string>): Record<string, unknown> {
  assert(failure.elementId !== null, 'fixture Failure must have an element')
  const source = names.get(failure.elementId)
  assert(source !== undefined, 'fixture Failure source must be described')
  return {
    failure_id: failure.failureId,
    kind: failure.kind,
    message: failure.message,
    source,
    attempt: failure.attempt,
    previous_failure_id: failure.previous?.failureId ?? null,
  }
}

function normalizeTerminal(terminal: Terminal): Record<string, unknown> {
  const normalized: Record<string, unknown> = { type: terminal.type, has_output: terminal.hasOutput }
  if (terminal.type === 'exit') normalized.action = terminal.action
  if (terminal.hasOutput) normalized.output = terminal.output
  return normalized
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, canonicalize(entry)]),
    )
  }
  return value
}
