// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// Run accounting, event publication, and observable failure fences.

import { MAX_SAFE_INTEGER } from './contracts.js'
import { ProducedFailure } from './failures.js'
import { disposeNativePromise, RuntimeCancellation } from './timing.js'

import type { Failure, Observer, ObserverDiagnostic, Phase, RunEvent, RunStats, Terminal } from './contracts.js'

export type EventSpec = {
  readonly kind: RunEvent['kind']
  readonly payload: unknown
}

export class RunAccounting {
  nextActivationId = 2
  nextScopeId = 2
  nextTerminalSequence = 1
  activations = 1
  attempts = 0
  transitions = 0
  retries = 0
  reports = 0
  scopes = 0
  ready = 0
  peakReady = 0
  private terminalMs: number | undefined

  constructor(private readonly startedMs: number) {}

  allocateActivationId(): number {
    const value = this.nextActivationId
    this.nextActivationId += 1
    this.activations += 1
    return value
  }

  allocateTerminalSequence(): number {
    const value = this.nextTerminalSequence
    this.nextTerminalSequence += 1
    return value
  }

  stats(peakCallbacks: number): RunStats {
    this.terminalMs ??= performance.now()
    const durationMs = Math.min(MAX_SAFE_INTEGER, Math.max(0, Math.floor(this.terminalMs - this.startedMs)))
    return Object.freeze({
      activations: this.activations,
      attempts: this.attempts,
      transitions: this.transitions,
      retries: this.retries,
      reports: this.reports,
      scopes: this.scopes,
      peakReady: this.peakReady,
      peakCallbacks,
      durationMs,
    })
  }
}

export class EventPublisher {
  private sequence = 0
  private readonly observerDiagnostics: ObserverDiagnostic[] = []
  private disabled = false
  private publishing = false
  private runCancellationPublished = false
  private terminal = false
  private readonly pending: Array<readonly EventSpec[]> = []

  constructor(
    private readonly runId: string,
    private readonly observer: Observer | undefined,
  ) {}

  get diagnostics(): readonly ObserverDiagnostic[] {
    return Object.freeze(this.observerDiagnostics.slice())
  }

  get isPublishing(): boolean {
    return this.publishing
  }

  publish(kind: RunEvent['kind'], payload: unknown): void {
    this.publishBundle([{ kind, payload }])
  }

  publishBundle(specs: readonly EventSpec[]): void {
    if (specs.length === 0) return
    this.pending.push(specs.slice())
    if (this.publishing) return
    this.publishing = true
    try {
      while (this.pending.length > 0) {
        const bundle = this.pending.shift()!
        const events = bundle.map((spec): RunEvent => {
          this.sequence += 1
          return Object.freeze({ sequence: this.sequence, runId: this.runId, kind: spec.kind, payload: spec.payload }) as RunEvent
        })
        for (const event of events) this.invoke(event)
      }
    } finally {
      this.publishing = false
    }
  }

  rejectReentrantReport(): void {
    if (!this.publishing || this.disabled) return
    this.disable(this.sequence, 'Observer reentrancy disabled', null)
  }

  publishRunCancellation(reason: unknown, deadline: boolean): void {
    if (this.runCancellationPublished) return
    this.runCancellationPublished = true
    this.publish('cancellation_fenced', Object.freeze({ target: Object.freeze({ kind: 'run' }), reason, deadline }))
  }

  markRunCancellationPublished(): void {
    this.runCancellationPublished = true
  }

  get terminalCommitted(): boolean {
    return this.terminal
  }

  markTerminal(): void {
    this.terminal = true
  }

  private invoke(event: RunEvent): void {
    if (this.observer === undefined || this.disabled) return
    let result: unknown
    try {
      result = this.observer(event)
    } catch (cause) {
      this.disable(event.sequence, 'Observer raised', cause)
      return
    }
    if ((typeof result !== 'object' || result === null) && typeof result !== 'function') return
    let then: unknown
    try {
      then = Reflect.get(result, 'then')
    } catch (cause) {
      this.disable(event.sequence, 'Observer result inspection failed', cause)
      return
    }
    if (typeof then !== 'function') return
    disposeNativePromise(result)
    this.disable(event.sequence, 'Observer must return synchronously', null)
  }

  private disable(eventSequence: number, message: string, cause: unknown | null): void {
    if (this.disabled) return
    this.disabled = true
    this.observerDiagnostics.push(Object.freeze({ eventSequence, message, cause }))
  }
}

type ObservedScope = {
  readonly scopeId: number
  readonly parent: { readonly scopeId: number } | null
  readonly ownerActivationId: number
  readonly entryActivationId: number
  readonly definition: { readonly entryElementId: number }
  readonly ownerPlacement: { readonly elementId: number }
  readonly depth: number
  readonly terminals: readonly Terminal[]
  finishedTerminalSequences?: readonly number[] | undefined
  finished: boolean
}

type ObservedAttempt = {
  readonly scopeId: number
  readonly activationId: number
  readonly attempt: number | null
}

export class RunObserver {
  failureFence: ProducedFailure | undefined
  private readonly recordedFailures = new Set<number>()
  private readonly scopeFencesPublished = new Set<number>()
  private readonly attemptFencesPublished = new Set<string>()
  private runFencePublished = false
  private cancellationFencePublished = false

  constructor(
    readonly publisher: EventPublisher,
    private readonly cancellation: RuntimeCancellation,
    private readonly runtimeScopes: ReadonlyMap<number, ObservedScope>,
  ) {}

  scopeStartedSpec(scope: ObservedScope): EventSpec {
    return {
      kind: 'scope_started',
      payload: Object.freeze({
        scopeId: scope.scopeId,
        parentScopeId: scope.parent?.scopeId ?? null,
        ownerActivationId: scope.ownerActivationId,
        entryActivationId: scope.entryActivationId,
        entryElementId: scope.definition.entryElementId,
        flowElementId: scope.ownerPlacement.elementId,
        depth: scope.depth,
      }),
    }
  }

  scopeFinishedSpec(scope: ObservedScope, status: 'completed' | 'failed' | 'cancelled' | 'abandoned'): EventSpec {
    return {
      kind: 'scope_finished',
      payload: Object.freeze({
        scopeId: scope.scopeId,
        status,
        terminalSequences: scope.finishedTerminalSequences ?? Object.freeze(scope.terminals.map((terminal) => terminal.sequence)),
      }),
    }
  }

  markScopeFinished(scope: ObservedScope, status: 'completed' | 'failed' | 'cancelled' | 'abandoned'): EventSpec | undefined {
    if (scope.finished) return undefined
    scope.finished = true
    return this.scopeFinishedSpec(scope, status)
  }

  captureScopeFinishTerminals(scope: ObservedScope): void {
    scope.finishedTerminalSequences ??= Object.freeze(scope.terminals.map((terminal) => terminal.sequence))
  }

  publishTerminal(status: 'completed' | 'failed' | 'cancelled' | 'abandoned'): void {
    this.publisher.markTerminal()
    const scopes = [...this.runtimeScopes.values()].sort((left, right) => right.depth - left.depth || left.scopeId - right.scopeId)
    const specs: EventSpec[] = []
    for (const scope of scopes) {
      const spec = this.markScopeFinished(scope, status)
      if (spec !== undefined) specs.push(spec)
    }
    specs.push({ kind: 'run_finished', payload: Object.freeze({ status }) })
    this.publisher.publishBundle(specs)
  }

  publishCallbackStarted(
    scope: ObservedScope,
    activationId: number,
    parentActivationId: number | null,
    elementId: number,
    phase: Phase,
    attempt: number | null,
  ): void {
    this.publisher.publish(
      'callback_started',
      Object.freeze({ scopeId: scope.scopeId, activationId, parentActivationId, elementId, phase, attempt }),
    )
  }

  failureRecordSpec(failure: Failure): EventSpec | undefined {
    if (this.recordedFailures.has(failure.failureId)) return undefined
    this.recordedFailures.add(failure.failureId)
    return { kind: 'failure_recorded', payload: Object.freeze({ failure }) }
  }

  publishCallbackFinished(
    scopeId: number,
    activationId: number,
    phase: Phase,
    attempt: number | null,
    disposition:
      | { readonly kind: 'outcome'; readonly outcome: 'route' | 'fanout' | 'end' | 'forward' | 'unhandled' }
      | { readonly kind: 'failure'; readonly failure: Failure }
      | { readonly kind: 'discarded' },
    failures: readonly Failure[] = [],
  ): void {
    const specs: EventSpec[] = []
    for (const failure of failures) {
      const spec = this.failureRecordSpec(failure)
      if (spec !== undefined) specs.push(spec)
    }
    specs.push({
      kind: 'callback_finished',
      payload: Object.freeze({ scopeId, activationId, phase, attempt, disposition: Object.freeze(disposition) }),
    })
    this.publisher.publishBundle(specs)
  }

  publishFailureRecorded(failure: Failure): void {
    const spec = this.failureRecordSpec(failure)
    if (spec !== undefined) this.publisher.publishBundle([spec])
  }

  publishScopeFailureFence(scope: ObservedScope, failure: Failure): void {
    if (this.scopeFencesPublished.has(scope.scopeId)) return
    this.scopeFencesPublished.add(scope.scopeId)
    const specs: EventSpec[] = []
    const record = this.failureRecordSpec(failure)
    if (record !== undefined) specs.push(record)
    specs.push(
      {
        kind: 'failure_fenced',
        payload: Object.freeze({ target: Object.freeze({ kind: 'scope', scopeId: scope.scopeId }), failure }),
      },
      {
        kind: 'cancellation_fenced',
        payload: Object.freeze({
          target: Object.freeze({ kind: 'scope', scopeId: scope.scopeId }),
          reason: 'scope_failed',
          deadline: false,
        }),
      },
    )
    this.publisher.publishBundle(specs)
  }

  publishRunFailureFence(failure: Failure): void {
    if (this.runFencePublished) return
    this.runFencePublished = true
    this.cancellationFencePublished = true
    this.failureFence ??= new ProducedFailure(failure)
    this.cancellation.cancel(Object.freeze({ type: 'failure_fence' as const, produced: this.failureFence }))
    this.publisher.markRunCancellationPublished()
    const specs: EventSpec[] = []
    const record = this.failureRecordSpec(failure)
    if (record !== undefined) specs.push(record)
    specs.push(
      { kind: 'failure_fenced', payload: Object.freeze({ target: Object.freeze({ kind: 'run' }), failure }) },
      {
        kind: 'cancellation_fenced',
        payload: Object.freeze({ target: Object.freeze({ kind: 'run' }), reason: 'run_failed', deadline: false }),
      },
    )
    this.publisher.publishBundle(specs)
  }

  publishRunCancellationIfNeeded(): void {
    if (!this.cancellation.cancelled || this.cancellationFencePublished) return
    this.cancellationFencePublished = true
    this.publisher.publishRunCancellation(this.cancellation.reason, this.cancellation.deadline)
  }

  publishAttemptTimeout(context: ObservedAttempt, failure: Failure): void {
    const targetKey = `${context.scopeId}:${context.activationId}:${context.attempt!}`
    if (this.attemptFencesPublished.has(targetKey)) return
    this.attemptFencesPublished.add(targetKey)
    const specs: EventSpec[] = []
    const record = this.failureRecordSpec(failure)
    if (record !== undefined) specs.push(record)
    specs.push({
      kind: 'cancellation_fenced',
      payload: Object.freeze({
        target: Object.freeze({
          kind: 'attempt',
          scopeId: context.scopeId,
          activationId: context.activationId,
          attempt: context.attempt!,
        }),
        reason: 'attempt_timeout',
        deadline: false,
      }),
    })
    this.publisher.publishBundle(specs)
  }
}
