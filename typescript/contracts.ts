// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2026, Victor Duarte

export type Action = string
export type MaybePromise<T> = T | PromiseLike<T>

export class CaskadaError extends Error {
  constructor(message = '', options?: ErrorOptions) {
    super(message, options)
    this.name = new.target.name
  }
}

export class GraphDefinitionError extends CaskadaError {}
export class DuplicateLinkError extends GraphDefinitionError {}

export interface Context<State extends object = Record<string, unknown>, Input = unknown> {
  readonly state: State
  readonly input: Input
  emit(): void
  emit(action: undefined, input: unknown): void
  emit(action: Action): void
  emit(action: Action, input: unknown): void
  end(): void
  end(output: unknown): void
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

export interface ScopeResult {
  readonly terminals: readonly Terminal[]
  readonly outputs: readonly unknown[]
}

export type FailureKind =
  | 'handler'
  | 'retry_policy'
  | 'node_recovery'
  | 'flow_combine'
  | 'flow_recovery'
  | 'invalid_outcome'
  | 'unknown_action'
  | 'activation_limit'
  | 'internal'

export interface Failure {
  readonly failureId: number
  readonly kind: FailureKind
  readonly message: string
  readonly cause: unknown | null
  readonly scopeId: number
  readonly activationId: number | null
  readonly elementId: number | null
  readonly attempt: number | null
  readonly previous: Failure | null
}

export interface ScopeFailure {
  readonly primary: Failure
  readonly terminals: readonly Terminal[]
  readonly result: ScopeResult | null
  readonly failingActivationId: number | null
}

export interface Completed<State extends object = Record<string, unknown>> {
  readonly status: 'completed'
  readonly state: State
  readonly terminals: readonly Terminal[]
}

export interface Failed<State extends object = Record<string, unknown>> {
  readonly status: 'failed'
  readonly state: State
  readonly terminals: readonly Terminal[]
  readonly failure: Failure
}

export type RunResult<State extends object = Record<string, unknown>> = Completed<State> | Failed<State>

export class RunError<State extends object = Record<string, unknown>> extends CaskadaError {
  readonly result: Failed<State>

  constructor(result: Failed<State>) {
    super(result.failure.message, result.failure.cause === null ? undefined : { cause: result.failure.cause })
    this.result = result
  }
}

export interface RunHandle<State extends object = Record<string, unknown>> {
  done(): boolean
  result(): Promise<RunResult<State>>
}

export type NodeHandler<State extends object = Record<string, unknown>, Input = unknown> = (
  context: Context<State, Input>,
) => MaybePromise<void>

export type NodeRecoveryHandler<State extends object = Record<string, unknown>, Input = unknown> = (
  context: Context<State, Input>,
  failure: Failure,
) => MaybePromise<void>

export type FlowCombineHandler<State extends object = Record<string, unknown>> = (
  context: Context<State>,
  result: ScopeResult,
) => MaybePromise<void>

export type FlowRecoveryHandler<State extends object = Record<string, unknown>> = (
  context: Context<State>,
  failure: ScopeFailure,
) => MaybePromise<void>

export interface RetryPolicy {
  readonly maxAttempts?: number
  readonly shouldRetry?: (failure: Failure) => boolean
  readonly delayMs?: number | ((attempt: number, failure: Failure) => number)
}

export interface NormalizedRetryPolicy {
  readonly maxAttempts: number
  readonly shouldRetry: (failure: Failure) => boolean
  readonly delayMs: number | ((attempt: number, failure: Failure) => number)
}
