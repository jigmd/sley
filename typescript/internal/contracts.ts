// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// Public runtime contracts shared by definition and execution modules.

export const MAX_SAFE_INTEGER = 9_007_199_254_740_991

export const MAX_PORTABLE_COLLECTION_LENGTH = 4_294_967_295

export const RUN_EVENT_SCHEMA_VERSION = 1

export const MAX_HOST_TIMER_DELAY_MS = 2_147_483_647

export class CaskadaError extends Error {
  constructor(message = '', options?: ErrorOptions) {
    super(message, options)
    this.name = new.target.name
  }
}

export class GraphDefinitionError extends CaskadaError {}

export class DuplicateLinkError extends GraphDefinitionError {}

export class OptionValidationError extends CaskadaError {}

export type Action = string

export type Phase = 'handle' | 'node_recover' | 'flow_combine' | 'flow_recover'

export const stateInvariant: unique symbol = Symbol('caskada.stateInvariant')

export const nodeConstructionToken: unique symbol = Symbol('caskada.nodeConstructionToken')

export const compiledFlowConstructionToken: unique symbol = Symbol('caskada.compiledFlowConstructionToken')

export const intrinsicPromiseThen = Promise.prototype.then

export interface Context<State extends object = Record<string, unknown>, Input = unknown> {
  readonly state: State
  readonly input: Input
  readonly runId: string
  readonly scopeId: number
  readonly activationId: number
  readonly parentActivationId: number | null
  readonly attempt: number | null
  readonly phase: Phase
  readonly cancellation: Cancellation
  remainingMs(): number | undefined
  emit(): void
  emit(unlabelled: { readonly input: unknown }): void
  emit(action: Action): void
  emit(action: Action, input: unknown): void
  end(): void
  end(output: unknown): void
  report(name: string): void
  report(name: string, data: unknown): void
}

export interface Cancellation {
  readonly cancelled: boolean
  readonly reason: unknown
  readonly signal: AbortSignal
  throwIfCancelled(): void
}

export interface EndTerminalBase {
  readonly type: 'end'
  readonly sequence: number
  readonly sourceActivationId: number
}

export type EndTerminal = EndTerminalBase &
  ({ readonly hasOutput: false; readonly output: undefined } | { readonly hasOutput: true; readonly output: unknown })

export interface ExitTerminal {
  readonly type: 'exit'
  readonly action: Action | null
  readonly hasOutput: true
  readonly output: unknown
  readonly sequence: number
  readonly sourceActivationId: number
}

export type Terminal = EndTerminal | ExitTerminal

export type NonEmptyTerminals = readonly [Terminal, ...Terminal[]]

export interface ScopeResult {
  readonly terminals: NonEmptyTerminals
  readonly outputs: readonly unknown[]
}

export interface ScopeFailure {
  readonly primary: Failure
  readonly suppressed: readonly Failure[]
  readonly settledBeforeFence: readonly Terminal[]
  readonly result: ScopeResult | null
  readonly failingActivationId: number | null
}

export type FailureKind =
  | 'handler'
  | 'handler_timeout'
  | 'retry_policy'
  | 'node_recovery'
  | 'flow_combine'
  | 'flow_recovery'
  | 'invalid_outcome'
  | 'invalid_combination'
  | 'unknown_action'
  | 'limit'
  | 'internal'

export type InvalidOutcomeReason =
  'wrong_return_type' | 'invalid_action' | 'invalid_control_arguments' | 'state_record_misuse' | 'report_name'

export type InvalidCombinationReason = InvalidOutcomeReason

export type LimitName =
  | 'max_activations'
  | 'scope_max_activations'
  | 'max_attempts'
  | 'max_transitions'
  | 'max_ready'
  | 'max_reports'
  | 'max_depth'
  | 'portable_collection'
  | 'safe_integer'

export type InternalReason = 'orphaned_live_token' | 'packet_registry' | 'counter_invariant' | 'scheduler_invariant'

export type FailureDetail =
  | { readonly type: 'invalid_outcome'; readonly reason: InvalidOutcomeReason }
  | { readonly type: 'invalid_combination'; readonly reason: InvalidCombinationReason }
  | { readonly type: 'unknown_action'; readonly action: Action }
  | { readonly type: 'limit'; readonly limit: LimitName }
  | { readonly type: 'internal'; readonly reason: InternalReason }

export interface Failure {
  readonly failureId: number
  readonly kind: FailureKind
  readonly message: string
  readonly cause: unknown | null
  readonly scopeId: number
  readonly activationId: number | null
  readonly elementId: number | null
  readonly attempt: number | null
  readonly detail: FailureDetail | null
  readonly previous: Failure | null
}

export interface EventBase {
  readonly sequence: number
  readonly runId: string
}

export type ReportPayload = {
  readonly scopeId: number
  readonly activationId: number
  readonly name: string
} & ({ readonly hasData: false; readonly data: undefined } | { readonly hasData: true; readonly data: unknown })

export type RunEvent =
  | (EventBase & {
      readonly kind: 'run_started'
      readonly payload: { readonly rootElementId: number; readonly rootActivationId: number }
    })
  | (EventBase & {
      readonly kind: 'run_finished'
      readonly payload: { readonly status: 'completed' | 'failed' | 'cancelled' | 'abandoned' }
    })
  | (EventBase & {
      readonly kind: 'scope_started'
      readonly payload: {
        readonly scopeId: number
        readonly parentScopeId: number | null
        readonly ownerActivationId: number
        readonly entryActivationId: number
        readonly entryElementId: number
        readonly flowElementId: number
        readonly depth: number
      }
    })
  | (EventBase & {
      readonly kind: 'scope_finished'
      readonly payload: {
        readonly scopeId: number
        readonly status: 'completed' | 'failed' | 'cancelled' | 'abandoned'
        readonly terminalSequences: readonly number[]
      }
    })
  | (EventBase & {
      readonly kind: 'callback_started'
      readonly payload: {
        readonly scopeId: number
        readonly activationId: number
        readonly parentActivationId: number | null
        readonly elementId: number
        readonly phase: Phase
        readonly attempt: number | null
      }
    })
  | (EventBase & {
      readonly kind: 'callback_finished'
      readonly payload: {
        readonly scopeId: number
        readonly activationId: number
        readonly phase: Phase
        readonly attempt: number | null
        readonly disposition:
          | { readonly kind: 'outcome'; readonly outcome: 'route' | 'fanout' | 'end' | 'forward' | 'unhandled' }
          | { readonly kind: 'failure'; readonly failure: Failure }
          | { readonly kind: 'discarded' }
      }
    })
  | (EventBase & {
      readonly kind: 'retry_scheduled'
      readonly payload: {
        readonly scopeId: number
        readonly activationId: number
        readonly failureId: number
        readonly failedAttempt: number
        readonly nextAttempt: number
        readonly delayMs: number
      }
    })
  | (EventBase & {
      readonly kind: 'transition_committed'
      readonly payload: {
        readonly scopeId: number
        readonly sourceActivationId: number
        readonly branchIndex: number
        readonly transition:
          | {
              readonly kind: 'route' | 'forward_exit'
              readonly action: Action | null
              readonly destination:
                | { readonly type: 'activation'; readonly activationId: number; readonly elementId: number }
                | { readonly type: 'terminal'; readonly sequence: number }
            }
          | {
              readonly kind: 'end' | 'forward_end'
              readonly destination: { readonly type: 'terminal'; readonly sequence: number }
            }
      }
    })
  | (EventBase & {
      readonly kind: 'terminal_committed'
      readonly payload: {
        readonly scopeId: number
        readonly terminalSequence: number
        readonly sourceActivationId: number
        readonly terminal:
          | { readonly kind: 'end'; readonly hasOutput: boolean }
          | { readonly kind: 'exit'; readonly action: Action | null; readonly hasOutput: true }
      }
    })
  | (EventBase & { readonly kind: 'failure_recorded'; readonly payload: { readonly failure: Failure } })
  | (EventBase & {
      readonly kind: 'failure_fenced'
      readonly payload: {
        readonly target: { readonly kind: 'run' } | { readonly kind: 'scope'; readonly scopeId: number }
        readonly failure: Failure
      }
    })
  | (EventBase & {
      readonly kind: 'cancellation_fenced'
      readonly payload: {
        readonly target:
          | { readonly kind: 'run' }
          | { readonly kind: 'scope'; readonly scopeId: number }
          | { readonly kind: 'attempt'; readonly scopeId: number; readonly activationId: number; readonly attempt: number }
        readonly reason: unknown
        readonly deadline: boolean
      }
    })
  | (EventBase & { readonly kind: 'report'; readonly payload: ReportPayload })

export type Observer = (event: RunEvent) => undefined

export const failureMessages: Readonly<Record<FailureKind, string>> = Object.freeze({
  handler: 'Node handler raised',
  handler_timeout: 'Node handler timed out',
  retry_policy: 'Retry policy failed',
  node_recovery: 'Node recovery raised',
  flow_combine: 'Flow combine raised',
  flow_recovery: 'Flow recovery raised',
  invalid_outcome: 'Invalid callback outcome',
  invalid_combination: 'Invalid Flow callback outcome',
  unknown_action: 'Unknown action',
  limit: 'Run limit exceeded',
  internal: 'Caskada runtime invariant failed',
})

export interface RunStats {
  readonly activations: number
  readonly attempts: number
  readonly transitions: number
  readonly retries: number
  readonly reports: number
  readonly scopes: number
  readonly peakReady: number
  readonly peakCallbacks: number
  readonly durationMs: number
}

export interface ObserverDiagnostic {
  readonly eventSequence: number
  readonly message: string
  readonly cause: unknown | null
}

export interface CancellationInfo {
  readonly reason: unknown
  readonly deadline: boolean
}

export interface RunOptions {
  readonly maxConcurrency?: number | undefined
  readonly maxActivations?: number | undefined
  readonly maxAttempts?: number | undefined
  readonly maxTransitions?: number | undefined
  readonly maxReady?: number | undefined
  readonly maxReports?: number | undefined
  readonly maxDepth?: number | undefined
  readonly deadlineMs?: number | undefined
  readonly cancelGraceMs?: number | undefined
  readonly observer?: Observer | undefined
  readonly runId?: string | undefined
}

export interface CompletedResult<State extends object = Record<string, unknown>> {
  readonly status: 'completed'
  readonly state: State
  readonly terminals: NonEmptyTerminals
  readonly stats: RunStats
  readonly diagnostics: readonly ObserverDiagnostic[]
}

export interface FailedResult<State extends object = Record<string, unknown>> {
  readonly status: 'failed'
  readonly state: State
  readonly terminals: readonly Terminal[]
  readonly failure: Failure
  readonly suppressed: readonly Failure[]
  readonly stats: RunStats
  readonly diagnostics: readonly ObserverDiagnostic[]
}

export interface CancelledResult<State extends object = Record<string, unknown>> {
  readonly status: 'cancelled'
  readonly state: State
  readonly terminals: readonly Terminal[]
  readonly cancellation: CancellationInfo
  readonly suppressed: readonly Failure[]
  readonly stats: RunStats
  readonly diagnostics: readonly ObserverDiagnostic[]
}

export interface AbandonedResult<State extends object = Record<string, unknown>> {
  readonly status: 'abandoned'
  readonly state: State
  readonly terminals: readonly Terminal[]
  readonly cause: Failure | CancellationInfo
  readonly suppressed: readonly Failure[]
  readonly stats: RunStats
  readonly diagnostics: readonly ObserverDiagnostic[]
}

export type RunResult<State extends object = Record<string, unknown>> =
  CompletedResult<State> | FailedResult<State> | CancelledResult<State> | AbandonedResult<State>

export class RunError<State extends object = Record<string, unknown>> extends CaskadaError {
  readonly result: FailedResult<State> | CancelledResult<State> | AbandonedResult<State>

  constructor(result: FailedResult<State> | CancelledResult<State> | AbandonedResult<State>) {
    const message =
      result.status === 'failed'
        ? 'Caskada run failed'
        : result.status === 'cancelled'
          ? 'Caskada run cancelled'
          : 'Caskada run abandoned'
    const cause =
      result.status === 'failed'
        ? result.failure.cause
        : result.status === 'abandoned' && 'kind' in result.cause
          ? result.cause.cause
          : null
    super(message, cause === null ? undefined : { cause })
    this.result = result
  }
}

export interface RunHandle<State extends object = Record<string, unknown>> {
  readonly done: boolean
  readonly result: Promise<RunResult<State>>
  cancel(reason?: unknown): void
}

export type NodeHandler<State extends object = Record<string, unknown>, Input = unknown> = (
  context: Context<State, Input>,
) => void | Promise<void>

export type NodeRecoveryHandler<State extends object = Record<string, unknown>, Input = unknown> = (
  context: Context<State, Input>,
  failure: Failure,
) => void | Promise<void>

export type FlowCombineHandler<State extends object = Record<string, unknown>> = (
  context: Context<State>,
  result: ScopeResult,
) => void | Promise<void>

export type FlowRecoveryHandler<State extends object = Record<string, unknown>> = (
  context: Context<State>,
  failure: ScopeFailure,
) => void | Promise<void>

export interface RetryOptions {
  readonly maxAttempts?: number | undefined
  readonly shouldRetry?: ((failure: Failure) => boolean) | undefined
  readonly delayMs?: number | ((failedAttempt: number, failure: Failure) => number) | undefined
}

export interface RetryPolicy {
  readonly maxAttempts: number
  readonly shouldRetry: (failure: Failure) => boolean
  readonly delayMs: number | ((failedAttempt: number, failure: Failure) => number)
}
