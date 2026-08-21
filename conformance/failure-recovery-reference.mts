import assert from 'node:assert/strict'

type FailureKind = 'handler' | 'node_recovery' | 'flow_combine' | 'flow_recovery'
type Topology = 'root_node' | 'node_after_source' | 'nested_flow' | 'combine'
type HandlerMode = 'fail' | 'fail_once_then_end' | 'end'
type RecoveryMode = 'none' | 'pass' | 'end' | 'throw'

export type FailureRecoveryProgram = {
  topology: Topology
  handler: HandlerMode
  retry_max_attempts: number
  node_recovery: RecoveryMode
  flow_recovery: RecoveryMode
  input?: unknown
  output?: unknown
}

type FailureRecord = {
  failure_id: number
  kind: FailureKind
  message: string
  source: string
  attempt: number | null
  previous_failure_id: number | null
}

const FAILURE_MESSAGES: Readonly<Record<FailureKind, string>> = Object.freeze({
  handler: 'Node handler raised',
  node_recovery: 'Node recovery raised',
  flow_combine: 'Flow combine raised',
  flow_recovery: 'Flow recovery raised',
})

export function evaluateFailureRecovery(program: FailureRecoveryProgram): Record<string, unknown> {
  validateProgram(program)
  const state: Record<string, unknown> = {}
  const failures: FailureRecord[] = []
  const retries: Array<Record<string, unknown>> = []
  let terminals: Array<Record<string, unknown>> = []
  let transitions = ['node_after_source', 'nested_flow', 'combine'].includes(program.topology) ? 1 : 0
  const scopes = program.topology === 'nested_flow' ? 2 : 1
  const activations = { root_node: 2, node_after_source: 3, nested_flow: 4, combine: 2 }[program.topology]
  let handlerAttempts = 1
  let previous: FailureRecord | null

  const newFailure = (
    kind: FailureKind,
    source: string,
    attempt: number | null,
    prior: FailureRecord | null = null,
  ): FailureRecord => {
    const failure: FailureRecord = {
      failure_id: failures.length + 1,
      kind,
      message: FAILURE_MESSAGES[kind],
      source,
      attempt,
      previous_failure_id: prior?.failure_id ?? null,
    }
    failures.push(failure)
    return failure
  }

  if (program.topology === 'combine') {
    state.handler_attempts = 1
    terminals.push(end(program.input))
    previous = newFailure('flow_combine', 'root', null)
  } else {
    state.handler_attempts = 1
    previous = newFailure('handler', 'worker', 1)
    if (program.handler === 'fail_once_then_end' && program.retry_max_attempts > 1) {
      retries.push({ failure_id: previous.failure_id, failed_attempt: 1, next_attempt: 2, delay_ms: 0 })
      handlerAttempts = 2
      state.handler_attempts = 2
      terminals.push(end(program.output))
      transitions += 1
      previous = null
    }
  }

  if (previous !== null && program.topology !== 'combine' && program.node_recovery !== 'none') {
    const observation: Record<string, unknown> = { failure_id: previous.failure_id, kind: previous.kind }
    if (program.topology === 'node_after_source') observation.input = structuredClone(program.input)
    state.node_recovery = observation
    if (program.node_recovery === 'end') {
      terminals.push(end(program.output))
      transitions += 1
      previous = null
    } else if (program.node_recovery === 'throw') previous = newFailure('node_recovery', 'worker', null, previous)
  }

  if (previous !== null && program.flow_recovery !== 'none') {
    const combineFailure = program.topology === 'combine'
    const observation: Record<string, unknown> = {
      failure_id: previous.failure_id,
      kind: previous.kind,
      failing_activation_id: combineFailure ? null : 4,
      settled_outputs: combineFailure ? [program.input] : [],
      result_outputs: combineFailure ? [program.input] : null,
    }
    if (program.topology === 'nested_flow') observation.input = structuredClone(program.input)
    state.flow_recovery = observation
    if (program.flow_recovery === 'end') {
      terminals = [end(program.output)]
      transitions += combineFailure ? 1 : 2
      previous = null
    } else if (program.flow_recovery === 'throw') {
      previous = newFailure('flow_recovery', combineFailure ? 'root' : 'child', null, previous)
    }
  }

  const attempts = handlerAttempts + (['node_after_source', 'nested_flow'].includes(program.topology) ? 1 : 0)
  const result: Record<string, unknown> =
    previous === null
      ? { status: 'completed', state, terminals }
      : { status: 'failed', state, terminals, failure: previous, suppressed: [] }
  const snapshot: Record<string, unknown> = {
    result,
    trace: { failures, retries },
    stats: { activations, attempts, transitions, retries: retries.length, scopes },
  }
  if (previous !== null) snapshot.run_projection = runProjection()
  return snapshot
}

function end(output: unknown): Record<string, unknown> {
  return { type: 'end', has_output: true, output: structuredClone(output) }
}

function runProjection(): Record<string, unknown> {
  return {
    type: 'throw',
    error: {
      name: 'RunError',
      message: 'Caskada run failed',
      result_status: 'failed',
      cause_is_result_failure_cause: true,
    },
  }
}

function validateProgram(program: FailureRecoveryProgram): void {
  assert(['root_node', 'node_after_source', 'nested_flow', 'combine'].includes(program.topology), 'unknown fixture topology')
  assert(['fail', 'fail_once_then_end', 'end'].includes(program.handler), 'unknown fixture handler')
  assert(Number.isSafeInteger(program.retry_max_attempts) && program.retry_max_attempts >= 1, 'retry count must be positive')
  assert(['none', 'pass', 'end', 'throw'].includes(program.node_recovery), 'unknown Node recovery mode')
  assert(['none', 'pass', 'end', 'throw'].includes(program.flow_recovery), 'unknown Flow recovery mode')
  assert(program.topology === 'combine' ? program.handler === 'end' : program.handler !== 'end', 'handler does not match topology')
}

export function canonicalize(value: unknown): unknown {
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
