// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// Failure construction, packets, and retry-policy evaluation.

import { failureMessages } from './contracts.js'

import type { CancellationInfo, Failure, FailureDetail, FailureKind, InvalidOutcomeReason, RetryPolicy } from './contracts.js'

export type FailurePacket = {
  readonly primary: Failure
  readonly suppressed: readonly Failure[]
  readonly input: unknown
}

export class FailureFactory {
  private nextId = 1

  create(
    kind: FailureKind,
    scopeId: number,
    activationId: number | null,
    elementId: number | null,
    attempt: number | null,
    cause: unknown | null,
    detail: FailureDetail | null,
    previous: Failure | null = null,
  ): Failure {
    const failure = Object.create(null) as {
      failureId: number
      kind: FailureKind
      message: string
      cause: unknown | null
      scopeId: number
      activationId: number | null
      elementId: number | null
      attempt: number | null
      detail: FailureDetail | null
      previous: Failure | null
    }
    failure.failureId = this.nextId
    failure.kind = kind
    failure.message = failureMessages[kind]
    failure.cause = cause
    failure.scopeId = scopeId
    failure.activationId = activationId
    failure.elementId = elementId
    failure.attempt = attempt
    failure.detail = detail === null ? null : Object.freeze(detail)
    failure.previous = previous
    this.nextId += 1
    return Object.freeze(failure)
  }
}

export function isRecoverableFailure(failure: Failure): boolean {
  return (
    failure.kind === 'handler' ||
    failure.kind === 'handler_timeout' ||
    failure.kind === 'node_recovery' ||
    failure.kind === 'flow_combine' ||
    failure.kind === 'flow_recovery'
  )
}

export function replacePacket(packet: FailurePacket, failure: Failure): FailurePacket {
  return { primary: failure, suppressed: packet.suppressed, input: packet.input }
}

export class SemanticMisuse extends TypeError {
  constructor(
    readonly reason: InvalidOutcomeReason,
    message: string,
  ) {
    super(message)
  }
}

export class ProducedFailure extends Error {
  readonly suppressed: readonly Failure[]

  constructor(
    readonly failure: Failure,
    suppressed: readonly Failure[] = [],
  ) {
    super(failure.message)
    this.suppressed = Object.freeze(suppressed.slice())
  }
}

type FailureFence = {
  readonly type: 'failure_fence'
  readonly produced: ProducedFailure
}

export function isFailureFence(value: unknown): value is FailureFence {
  return typeof value === 'object' && value !== null && (value as { readonly type?: unknown }).type === 'failure_fence'
}

export class RunFailure extends Error {
  constructor(readonly packet: FailurePacket) {
    super(packet.primary.message)
  }
}

export class RuntimeScopeFailure extends Error {
  constructor(readonly packet: FailurePacket) {
    super(packet.primary.message)
  }
}

export class RunCancelled extends Error {
  readonly suppressed: readonly Failure[]

  constructor(suppressed: readonly Failure[] = []) {
    super('Caskada run cancelled')
    this.suppressed = Object.freeze(suppressed.slice())
  }
}

export class RunAbandoned extends Error {
  readonly suppressed: readonly Failure[]

  constructor(
    readonly cause: Failure | CancellationInfo,
    suppressed: readonly Failure[] = [],
  ) {
    super('Caskada run abandoned')
    this.suppressed = Object.freeze(suppressed.slice())
  }
}

type RetryScope = { readonly scopeId: number }
type RetryPlacement = { readonly elementId: number; readonly retry: RetryPolicy }
type RetryActivation = { readonly activationId: number }

export class RecoveryPolicy {
  constructor(
    private readonly failures: FailureFactory,
    private readonly cancellation: { readonly cancelled: boolean },
    private readonly cancellationPolicy: {
      commitDeadlineIfDue(): void
      check(suppressed?: readonly Failure[]): void
    },
    private readonly publishFailure: (failure: Failure) => void,
    private readonly disposePromise: (value: object) => void,
  ) {}

  shouldRetry(
    scope: RetryScope,
    placement: RetryPlacement,
    activation: RetryActivation,
    attempt: number,
    failure: Failure,
    inheritedSuppressed: readonly Failure[],
  ): boolean {
    let result: unknown
    try {
      result = placement.retry.shouldRetry(failure)
    } catch (cause) {
      const replacement = this.failures.create(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        cause,
        null,
        failure,
      )
      this.cancellationPolicy.commitDeadlineIfDue()
      if (this.cancellation.cancelled) throw new RunCancelled([failure, ...inheritedSuppressed, replacement])
      this.publishFailure(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    this.cancellationPolicy.check([failure, ...inheritedSuppressed])
    this.rejectAsynchronousPolicyResult(scope, placement, activation, attempt, failure, inheritedSuppressed, result)
    if (typeof result !== 'boolean') {
      const replacement = this.failures.create(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        null,
        null,
        failure,
      )
      this.publishFailure(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    return result
  }

  retryDelay(
    scope: RetryScope,
    placement: RetryPlacement,
    activation: RetryActivation,
    attempt: number,
    failure: Failure,
    inheritedSuppressed: readonly Failure[],
  ): number {
    if (typeof placement.retry.delayMs === 'number') return placement.retry.delayMs
    let result: unknown
    try {
      result = placement.retry.delayMs(attempt, failure)
    } catch (cause) {
      const replacement = this.failures.create(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        cause,
        null,
        failure,
      )
      this.cancellationPolicy.commitDeadlineIfDue()
      if (this.cancellation.cancelled) throw new RunCancelled([failure, ...inheritedSuppressed, replacement])
      this.publishFailure(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    this.cancellationPolicy.check([failure, ...inheritedSuppressed])
    this.rejectAsynchronousPolicyResult(scope, placement, activation, attempt, failure, inheritedSuppressed, result)
    if (typeof result !== 'number' || !Number.isSafeInteger(result) || result < 0) {
      const replacement = this.failures.create(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        null,
        null,
        failure,
      )
      this.publishFailure(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    return Object.is(result, -0) ? 0 : result
  }

  rejectAsynchronousPolicyResult(
    scope: RetryScope,
    placement: RetryPlacement,
    activation: RetryActivation,
    attempt: number,
    failure: Failure,
    inheritedSuppressed: readonly Failure[],
    result: unknown,
  ): void {
    if ((typeof result !== 'object' || result === null) && typeof result !== 'function') return
    let then: unknown
    try {
      then = Reflect.get(result, 'then')
    } catch (cause) {
      const replacement = this.failures.create(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        cause,
        null,
        failure,
      )
      this.cancellationPolicy.commitDeadlineIfDue()
      if (this.cancellation.cancelled) throw new RunCancelled([failure, ...inheritedSuppressed, replacement])
      this.publishFailure(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    this.cancellationPolicy.check([failure, ...inheritedSuppressed])
    if (typeof then !== 'function') return
    this.disposePromise(result)
    const replacement = this.failures.create(
      'retry_policy',
      scope.scopeId,
      activation.activationId,
      placement.elementId,
      attempt,
      null,
      null,
      failure,
    )
    this.publishFailure(replacement)
    throw new ProducedFailure(replacement, inheritedSuppressed)
  }
}
