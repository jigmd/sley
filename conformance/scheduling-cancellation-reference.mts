type Program = {
  readonly scenario: string
  readonly width?: number
  readonly max_concurrency?: number
}

const CANCEL_REASON = 'fixture-cancel'

export function canonicalize(value: unknown): unknown {
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

export function evaluateSchedulingCancellation(program: Program): Record<string, unknown> {
  validateProgram(program)
  const scenario = program.scenario
  if (scenario === 'auto_width' || scenario === 'nested_auto_width' || scenario === 'global_ceiling') {
    const width = program.width!
    const nested = scenario === 'nested_auto_width'
    const peak = program.max_concurrency ?? width
    return snapshot({
      status: 'completed',
      outputs: Array.from({ length: width }, (_, index) => index),
      terminalCount: width,
      observations: { peak },
      activations: width + (nested ? 3 : 2),
      attempts: width + 1,
      transitions: nested ? 3 * width : 2 * width,
      scopes: nested ? 2 : 1,
      peakCallbacks: peak,
    })
  }
  if (scenario === 'retry_ready_priority') {
    return snapshot({
      status: 'completed',
      outputs: ['blocker', 'retry', 'new'],
      terminalCount: 3,
      observations: { order: ['retry:1', 'blocker:1', 'retry:2', 'new:1'] },
      activations: 5,
      attempts: 5,
      transitions: 6,
      retries: 1,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'fair_scope_rotation') {
    return snapshot({
      status: 'completed',
      outputs: [
        ['A', 0],
        ['A', 1],
        ['A', 2],
        ['B', 0],
        ['B', 1],
        ['B', 2],
      ],
      terminalCount: 6,
      observations: { b0_before_a2: true, work_count: 6 },
      activations: 12,
      attempts: 9,
      transitions: 20,
      scopes: 3,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'sibling_signal_before_recovery') {
    return snapshot({
      status: 'completed',
      state: { recovered: true },
      terminalCount: 1,
      observations: { scope_reason: 'scope_failed', sibling_signalled: true },
      activations: 4,
      attempts: 3,
      transitions: 3,
      scopes: 1,
      peakCallbacks: 2,
    })
  }
  if (scenario === 'parked_retry_packet') {
    return snapshot({
      status: 'failed',
      suppressed: [{ attempt: 1, kind: 'handler' }],
      observations: { primary_is_controller: true, suppressed_is_parked: true },
      activations: 4,
      attempts: 3,
      transitions: 2,
      retries: 1,
      scopes: 1,
      peakCallbacks: 2,
    })
  }
  if (scenario === 'attempt_limit_before_permit') {
    return snapshot({
      status: 'failed',
      observations: { calls: ['source', 'first'], limit: 'max_attempts' },
      activations: 4,
      attempts: 2,
      transitions: 2,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'zero_delay_retry_priority' || scenario === 'observer_retry_delay') {
    return snapshot({
      status: 'completed',
      outputs: ['retry', 'peer'],
      terminalCount: 2,
      observations: { order: ['retry:1', 'retry:2', 'peer:1'] },
      activations: 4,
      attempts: 4,
      transitions: 4,
      retries: 1,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'node_recovery_priority') {
    return snapshot({
      status: 'completed',
      outputs: ['recovered', 'peer'],
      terminalCount: 2,
      observations: { order: ['handle:bad', 'recover:bad', 'handle:peer'] },
      activations: 4,
      attempts: 3,
      transitions: 4,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'ready_waiter_capacity') {
    return snapshot({
      status: 'failed',
      observations: { calls: ['dispatch', 'active'], limit: 'max_ready' },
      activations: 4,
      attempts: 2,
      transitions: 2,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'cancel_before_admission') {
    return snapshot({
      status: 'cancelled',
      observations: { called: false },
      activations: 2,
      attempts: 0,
      transitions: 0,
      scopes: 1,
      peakCallbacks: 0,
    })
  }
  if (scenario === 'cancel_after_buffer') return cancelledActive()
  if (scenario === 'post_signal_suppression') return cancelledActive([{ attempt: 1, kind: 'handler' }])
  if (scenario === 'prior_terminal_ready_discard') {
    return snapshot({
      status: 'cancelled',
      outputs: [1],
      terminalCount: 1,
      observations: { late_present: false },
      activations: 5,
      attempts: 3,
      transitions: 4,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'cancel_retry_delay') return cancelledActive([{ attempt: 1, kind: 'handler' }], 1)
  if (scenario === 'cancel_node_recovery' || scenario === 'cancel_flow_recovery') {
    return cancelledActive([{ attempt: 1, kind: 'handler' }])
  }
  if (scenario === 'failure_grace_abandonment') {
    return snapshot({
      status: 'abandoned',
      cause: { attempt: 1, kind: 'handler', type: 'failure' },
      observations: {
        fences: [
          'failure_fenced:scope',
          'cancellation_fenced:scope',
          'failure_fenced:run',
          'cancellation_fenced:run',
          'run_finished:abandoned',
        ],
        recovery_called: false,
      },
      activations: 4,
      attempts: 3,
      transitions: 2,
      scopes: 1,
      peakCallbacks: 2,
    })
  }
  if (scenario === 'retry_suppression_unique') {
    return snapshot({
      status: 'failed',
      suppressed: [{ attempt: 1, kind: 'handler' }],
      observations: {
        primary_is_second_attempt: true,
        previous_is_timeout: true,
        suppression_is_unique: true,
      },
      activations: 2,
      attempts: 2,
      transitions: 0,
      retries: 1,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'concurrent_cancel_abandonment') {
    return snapshot({
      status: 'abandoned',
      cause: { deadline: false, reason: CANCEL_REASON, type: 'cancellation' },
      observations: { fences: ['cancellation_fenced:run', 'run_finished:abandoned'] },
      activations: 4,
      attempts: 3,
      transitions: 2,
      scopes: 1,
      peakCallbacks: 2,
    })
  }
  if (scenario === 'sync_retry_policy_grace') {
    return snapshot({
      status: 'abandoned',
      cause: { deadline: false, reason: CANCEL_REASON, type: 'cancellation' },
      suppressed: [{ attempt: 1, kind: 'handler' }],
      observations: { recorded_failure_kinds: ['handler'] },
      activations: 2,
      attempts: 1,
      transitions: 0,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'route_packet_cancellation') {
    return snapshot({
      status: 'cancelled',
      suppressed: [
        { attempt: 1, kind: 'handler_timeout' },
        { attempt: 1, kind: 'handler' },
      ],
      activations: 2,
      attempts: 2,
      transitions: 0,
      retries: 1,
      scopes: 1,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'nested_scope_failure_status') {
    return snapshot({
      status: 'completed',
      state: { recovered: true },
      terminalCount: 1,
      observations: { scope_finishes: ['2:failed', '1:completed'] },
      activations: 3,
      attempts: 1,
      transitions: 2,
      scopes: 2,
      peakCallbacks: 1,
    })
  }
  if (scenario === 'opening_observer_deadline') {
    return snapshot({
      status: 'cancelled',
      cancellation: { deadline: true, reason: 'deadline_exceeded' },
      observations: { called: false, done_on_return: true },
      activations: 2,
      attempts: 0,
      transitions: 0,
      scopes: 1,
      peakCallbacks: 0,
    })
  }
  throw new Error(`unknown scheduling/cancellation scenario ${scenario}`)
}

function cancelledActive(suppressed: unknown[] = [], retries = 0): Record<string, unknown> {
  return snapshot({
    status: 'cancelled',
    suppressed,
    activations: 2,
    attempts: 1,
    transitions: 0,
    retries,
    scopes: 1,
    peakCallbacks: 1,
  })
}

function snapshot(options: {
  readonly status: string
  readonly state?: Record<string, unknown>
  readonly outputs?: unknown[]
  readonly terminalCount?: number
  readonly suppressed?: unknown[]
  readonly cause?: Record<string, unknown>
  readonly cancellation?: Record<string, unknown>
  readonly observations?: Record<string, unknown>
  readonly activations: number
  readonly attempts: number
  readonly transitions: number
  readonly retries?: number
  readonly scopes: number
  readonly peakCallbacks: number
}): Record<string, unknown> {
  const result: Record<string, unknown> = {
    outputs: options.outputs ?? [],
    state: options.state ?? {},
    status: options.status,
    suppressed: options.suppressed ?? [],
    terminal_count: options.terminalCount ?? 0,
  }
  if (options.status === 'cancelled') {
    result.cancellation = options.cancellation ?? { deadline: false, reason: CANCEL_REASON }
  }
  if (options.status === 'abandoned') {
    if (options.cause === undefined) throw new Error('abandoned fixture requires a cause')
    result.cause = options.cause
  }
  return {
    observations: options.observations ?? {},
    result,
    stats: {
      activations: options.activations,
      attempts: options.attempts,
      peak_callbacks: options.peakCallbacks,
      retries: options.retries ?? 0,
      scopes: options.scopes,
      transitions: options.transitions,
    },
  }
}

function validateProgram(program: Program): void {
  const known = new Set([
    'auto_width',
    'nested_auto_width',
    'global_ceiling',
    'retry_ready_priority',
    'fair_scope_rotation',
    'sibling_signal_before_recovery',
    'parked_retry_packet',
    'attempt_limit_before_permit',
    'zero_delay_retry_priority',
    'observer_retry_delay',
    'node_recovery_priority',
    'ready_waiter_capacity',
    'cancel_before_admission',
    'cancel_after_buffer',
    'post_signal_suppression',
    'prior_terminal_ready_discard',
    'cancel_retry_delay',
    'cancel_node_recovery',
    'cancel_flow_recovery',
    'failure_grace_abandonment',
    'retry_suppression_unique',
    'concurrent_cancel_abandonment',
    'sync_retry_policy_grace',
    'route_packet_cancellation',
    'nested_scope_failure_status',
    'opening_observer_deadline',
  ])
  if (!known.has(program.scenario)) throw new Error('unknown scheduling/cancellation fixture scenario')
  if (program.scenario === 'auto_width' || program.scenario === 'nested_auto_width' || program.scenario === 'global_ceiling') {
    if (!Number.isSafeInteger(program.width) || program.width! < 1) throw new Error('width must be a positive integer')
  }
  if (program.max_concurrency !== undefined && (!Number.isSafeInteger(program.max_concurrency) || program.max_concurrency < 1)) {
    throw new Error('max_concurrency must be a positive integer')
  }
}
