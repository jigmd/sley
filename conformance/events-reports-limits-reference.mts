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

export function evaluateEventsReportsLimits(scenario: string): Record<string, unknown> {
  if (scenario === 'successful_trace') {
    return {
      committed_terminal_sequence: 1,
      end_terminal_sequence: 1,
      kinds: [
        'run_started',
        'scope_started',
        'callback_started',
        'callback_finished',
        'transition_committed',
        'callback_started',
        'callback_finished',
        'transition_committed',
        'terminal_committed',
        'scope_finished',
        'run_finished',
      ],
      route_destination: 'activation',
      run_ids: ['fixture-events'],
      sequences: Array.from({ length: 11 }, (_, index) => index + 1),
      status: 'completed',
    }
  }
  if (scenario === 'observer_skip') {
    return {
      attempts: 1,
      calls: 0,
      kinds: [
        'run_started',
        'scope_started',
        'callback_started',
        'cancellation_fenced',
        'callback_finished',
        'scope_finished',
        'run_finished',
      ],
      status: 'cancelled',
    }
  }
  if (scenario === 'observer_throw') {
    return {
      calls: 1,
      diagnostic: { event_sequence: 1, message: 'Observer raised' },
      diagnostic_count: 1,
      status: 'completed',
    }
  }
  if (scenario === 'report_presence') {
    return {
      report_count: 2,
      reports: [
        { has_data: false, name: 'started' },
        { data: null, has_data: true, name: 'value' },
      ],
      status: 'completed',
    }
  }
  if (scenario === 'report_reentrant') {
    return {
      diagnostic: { event_sequence: 4, message: 'Observer reentrancy disabled' },
      published_reports: 1,
      report_count: 1,
      status: 'completed',
    }
  }
  if (scenario === 'report_overflow') {
    return limit({
      limitName: 'max_reports',
      activationId: 2,
      attempt: 1,
      activations: 2,
      attempts: 1,
      transitions: 0,
      reports: 1,
      scopes: 1,
      observations: { caught: 2, failure_fences: 1, published_reports: 1 },
    })
  }
  if (scenario === 'transition_overflow') {
    return limit({
      limitName: 'max_transitions',
      activationId: 2,
      attempt: 1,
      activations: 2,
      attempts: 1,
      transitions: 0,
      reports: 0,
      scopes: 1,
      observations: { caught: true },
    })
  }
  if (scenario === 'capacity_priority') {
    return limit({
      limitName: 'max_activations',
      activationId: 2,
      attempt: 1,
      activations: 2,
      attempts: 1,
      transitions: 0,
      reports: 0,
      scopes: 1,
    })
  }
  if (scenario === 'depth_limit') {
    return limit({
      limitName: 'max_depth',
      activationId: 3,
      attempt: null,
      activations: 3,
      attempts: 1,
      transitions: 1,
      reports: 0,
      scopes: 1,
    })
  }
  if (scenario === 'attempt_limit') {
    return limit({
      limitName: 'max_attempts',
      activationId: 3,
      attempt: null,
      activations: 3,
      attempts: 1,
      transitions: 1,
      reports: 0,
      scopes: 1,
      observations: { calls: ['source'] },
    })
  }
  throw new Error(`unknown events/reports/limits scenario ${scenario}`)
}

function limit(options: {
  readonly limitName: string
  readonly activationId: number
  readonly attempt: number | null
  readonly activations: number
  readonly attempts: number
  readonly transitions: number
  readonly reports: number
  readonly scopes: number
  readonly observations?: Record<string, unknown>
}): Record<string, unknown> {
  return {
    failure: {
      activation_id: options.activationId,
      attempt: options.attempt,
      kind: 'limit',
      limit: options.limitName,
      scope_id: 1,
    },
    observations: options.observations ?? {},
    stats: {
      activations: options.activations,
      attempts: options.attempts,
      peak_ready: 1,
      reports: options.reports,
      scopes: options.scopes,
      transitions: options.transitions,
    },
    status: 'failed',
    terminal_count: 0,
  }
}
