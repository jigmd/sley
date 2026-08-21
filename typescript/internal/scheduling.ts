// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// The sole orchestration owner for activations and structured scopes.

import { MAX_PORTABLE_COLLECTION_LENGTH, MAX_SAFE_INTEGER, OptionValidationError, RunError } from './contracts.js'
import { nodeHandlers, nodeRecoveries } from './definition.js'
import {
  FailureFactory,
  isFailureFence,
  isRecoverableFailure,
  ProducedFailure,
  RecoveryPolicy,
  replacePacket,
  RunAbandoned,
  RunCancelled,
  RunFailure,
  RuntimeScopeFailure,
  SemanticMisuse,
} from './failures.js'
import { EventPublisher, RunAccounting, RunObserver } from './observation.js'
import { resolveStateCarrier } from './state.js'
import {
  CallbackController,
  CallbackExecutor,
  disposeNativePromise,
  RunCancellation,
  RuntimeCancellation,
  RuntimeDeadline,
  waitRetryDelay,
  waitRuntimeDeadline,
} from './timing.js'

import type {
  AbandonedResult,
  Action,
  CancellationInfo,
  CancelledResult,
  CompletedResult,
  Context,
  EndTerminal,
  ExitTerminal,
  FailedResult,
  Failure,
  LimitName,
  NonEmptyTerminals,
  Observer,
  ObserverDiagnostic,
  Phase,
  RunHandle,
  RunResult,
  RunStats,
  ScopeFailure,
  ScopeResult,
  Terminal,
} from './contracts.js'
import type { CompiledNodePlacement, CompiledPlacement, CompiledScope, CompiledSnapshot } from './definition.js'
import type { FailurePacket } from './failures.js'
import type { EventSpec } from './observation.js'

type Intent = {
  readonly kind: 'emit' | 'end'
  readonly action: Action | null
  readonly value: unknown
  readonly present: boolean
}

type Activation = {
  readonly elementId: number
  readonly input: unknown
  readonly activationId: number
  readonly parentActivationId: number
}

type RuntimeScope = {
  readonly scopeId: number
  readonly definition: CompiledScope
  readonly ownerActivationId: number
  readonly ownerParentActivationId: number | null
  readonly incomingInput: unknown
  readonly parent: RuntimeScope | null
  readonly ownerPlacement: CompiledPlacement
  readonly entryActivationId: number
  readonly queue: Activation[]
  queueIndex: number
  terminals: Terminal[]
  readonly depth: number
  directActivations: number
  readonly cancellation: RuntimeCancellation
  combined: boolean
  finished: boolean
  finishedTerminalSequences?: readonly number[]
}

type SerialOutcome = {
  readonly terminals: readonly Terminal[]
  readonly stats: RunStats
  readonly failure: Failure | null
  readonly suppressed: readonly Failure[]
  readonly cancellation: CancellationInfo | null
  readonly abandonment: Failure | CancellationInfo | null
}

type NodeSettlement = {
  readonly intents: readonly Intent[]
  readonly attempt: number | null
  readonly previous: Failure | null
  readonly suppressed: readonly Failure[]
}

type ActivationCompletion = {
  readonly sequence: number
  readonly activation: Activation
  readonly failed: boolean
  readonly error: unknown
}

class RuntimeContext<State extends object> implements Context<State, unknown> {
  private readonly intents: Intent[] = []
  private live = true

  constructor(
    private readonly sharedState: State,
    private readonly branchInput: unknown,
    private readonly runtimeRunId: string,
    private readonly runtimeScopeId: number,
    private readonly runtimeActivationId: number,
    private readonly runtimeParentActivationId: number | null,
    private readonly runtimeAttempt: number | null,
    private readonly runtimePhase: Phase,
    private readonly runtimeCancellation: RuntimeCancellation,
    private readonly runtimeRemainingMs?: () => number | undefined,
    private readonly intentReserver?: (bufferedCount: number) => void,
    private readonly reporter?: (context: RuntimeContext<State>, name: unknown, data: unknown, hasData: boolean) => void,
  ) {}

  get state(): State {
    this.requireLive()
    return this.sharedState
  }

  get input(): unknown {
    this.requireLive()
    return this.branchInput
  }

  get runId(): string {
    this.requireLive()
    return this.runtimeRunId
  }

  get scopeId(): number {
    this.requireLive()
    return this.runtimeScopeId
  }

  get activationId(): number {
    this.requireLive()
    return this.runtimeActivationId
  }

  get parentActivationId(): number | null {
    this.requireLive()
    return this.runtimeParentActivationId
  }

  get attempt(): number | null {
    this.requireLive()
    return this.runtimeAttempt
  }

  get phase(): Phase {
    this.requireLive()
    return this.runtimePhase
  }

  get cancellation(): RuntimeCancellation {
    this.requireLive()
    return this.runtimeCancellation
  }

  remainingMs(): number | undefined {
    this.requireLive()
    return this.runtimeRemainingMs?.()
  }

  emit(): void
  emit(unlabelled: { readonly input: unknown }): void
  emit(action: Action): void
  emit(action: Action, input: unknown): void
  emit(...args: unknown[]): void {
    this.requireLive()
    if (args.length === 0) {
      this.appendIntent({ kind: 'emit', action: null, value: this.branchInput, present: true })
      return
    }
    if (args.length === 1) {
      const first = args[0]
      if (typeof first === 'string') {
        this.appendIntent({ kind: 'emit', action: requireRuntimeAction(first), value: this.branchInput, present: true })
        return
      }
      if ((typeof first !== 'object' && typeof first !== 'function') || first === null) {
        requireRuntimeAction(first)
      }
      this.appendIntent({ kind: 'emit', action: null, value: captureInputWrapper(first), present: true })
      return
    }
    if (args.length === 2) {
      this.appendIntent({ kind: 'emit', action: requireRuntimeAction(args[0]), value: args[1], present: true })
      return
    }
    throw new SemanticMisuse('invalid_control_arguments', 'emit() received invalid arguments')
  }

  end(): void
  end(output: unknown): void
  end(...args: unknown[]): void {
    this.requireLive()
    if (args.length > 1) throw new SemanticMisuse('invalid_control_arguments', 'end() received invalid arguments')
    this.appendIntent({ kind: 'end', action: null, value: args[0], present: args.length === 1 })
  }

  report(name: string): void
  report(name: string, data: unknown): void
  report(...args: unknown[]): void {
    this.requireLive()
    if (args.length !== 1 && args.length !== 2) {
      throw new SemanticMisuse('invalid_control_arguments', 'report() received invalid arguments')
    }
    if (this.reporter === undefined) throw new Error('Context report capability is unavailable')
    this.reporter(this, args[0], args[1], args.length === 2)
  }

  close(): readonly Intent[] {
    this.live = false
    return this.intents.slice()
  }

  abandon(): void {
    this.live = false
    this.intents.length = 0
  }

  private appendIntent(intent: Intent): void {
    this.intentReserver?.(this.intents.length + 1)
    this.intents.push(intent)
  }

  private requireLive(): void {
    if (!this.live) throw new SemanticMisuse('invalid_control_arguments', 'Context is closed')
  }
}

class RuntimeKernel<State extends object> {
  private readonly placements = new Map<number, CompiledPlacement>()
  private readonly scopes = new Map<number, CompiledScope>()
  private readonly failures = new FailureFactory()
  private readonly callbacks: CallbackController
  private readonly accounting: RunAccounting
  private readonly observer: RunObserver
  private readonly cancellationPolicy: RunCancellation
  private readonly recovery: RecoveryPolicy
  private readonly callbackExecutor: CallbackExecutor
  private readonly runtimeScopes = new Map<number, RuntimeScope>()

  constructor(
    private readonly snapshot: CompiledSnapshot,
    private readonly state: State,
    startedMs: number,
    private readonly cancellation: RuntimeCancellation,
    private readonly runId: string,
    private readonly options: ResolvedRunOptions,
    private readonly runDeadline: RuntimeDeadline | undefined,
    publisher: EventPublisher,
  ) {
    for (const placement of snapshot.placements) this.placements.set(placement.elementId, placement)
    for (const scope of snapshot.scopes) this.scopes.set(scope.scopeDefinitionId, scope)
    this.callbacks = new CallbackController(options.maxConcurrency ?? snapshot.autoMaxConcurrency, cancellation)
    this.accounting = new RunAccounting(startedMs)
    this.observer = new RunObserver(publisher, cancellation, this.runtimeScopes)
    this.cancellationPolicy = new RunCancellation(
      cancellation,
      runDeadline,
      () => this.observer.failureFence,
      () => this.observer.publishRunCancellationIfNeeded(),
    )
    this.recovery = new RecoveryPolicy(
      this.failures,
      cancellation,
      this.cancellationPolicy,
      (failure) => this.observer.publishFailureRecorded(failure),
      disposeNativePromise,
    )
    this.callbackExecutor = new CallbackExecutor(
      cancellation,
      runDeadline,
      options.cancelGraceMs,
      this.cancellationPolicy,
      () => this.observer.failureFence,
      (context, failure) => this.observer.publishAttemptTimeout(context, failure),
    )
  }

  async run(settle: (outcome: SerialOutcome) => void): Promise<void> {
    const rootDefinition = this.requireScope(1)
    const rootPlacement = this.requirePlacement(1)
    const root = this.newScope(rootDefinition, 1, null, undefined, null, rootPlacement)
    try {
      this.cancellationPolicy.check()
      let terminals: NonEmptyTerminals | undefined
      await this.runScopes(root, (completedTerminals) => {
        terminals = completedTerminals
      })
      this.cancellationPolicy.check()
      if (terminals === undefined) throw new Error('scheduler completed without root terminals')
      const stats = this.accounting.stats(this.callbacks.peak)
      this.observer.publishTerminal('completed')
      settle({
        terminals,
        stats,
        failure: null,
        suppressed: Object.freeze([]),
        cancellation: null,
        abandonment: null,
      })
    } catch (error) {
      if (error instanceof RunAbandoned) {
        const stats = this.accounting.stats(this.callbacks.peak)
        this.observer.publishTerminal('abandoned')
        settle({
          terminals: Object.freeze(root.terminals.slice()),
          stats,
          failure: null,
          suppressed: error.suppressed,
          cancellation: null,
          abandonment: error.cause,
        })
        return
      }
      if (error instanceof RunCancelled) {
        this.observer.publishRunCancellationIfNeeded()
        const stats = this.accounting.stats(this.callbacks.peak)
        this.observer.publishTerminal('cancelled')
        settle({
          terminals: Object.freeze(root.terminals.slice()),
          stats,
          failure: null,
          suppressed: error.suppressed,
          cancellation: Object.freeze({ reason: this.cancellation.reason, deadline: this.cancellation.deadline }),
          abandonment: null,
        })
        return
      }
      if (error instanceof RunFailure) {
        this.observer.publishRunFailureFence(error.packet.primary)
        const stats = this.accounting.stats(this.callbacks.peak)
        this.observer.publishTerminal('failed')
        settle({
          terminals: Object.freeze(root.terminals.slice()),
          stats,
          failure: error.packet.primary,
          suppressed: error.packet.suppressed,
          cancellation: null,
          abandonment: null,
        })
        return
      }
      const failure =
        error instanceof ProducedFailure
          ? error.failure
          : this.failures.create('internal', 1, null, null, null, null, {
              type: 'internal',
              reason: 'scheduler_invariant',
            })
      this.observer.publishRunFailureFence(failure)
      const stats = this.accounting.stats(this.callbacks.peak)
      this.observer.publishTerminal('failed')
      settle({
        terminals: Object.freeze(root.terminals.slice()),
        stats,
        failure,
        suppressed: error instanceof ProducedFailure ? error.suppressed : Object.freeze([]),
        cancellation: null,
        abandonment: null,
      })
    }
  }

  private async acquireCallback(scope: RuntimeScope, readyCallback: boolean): Promise<void> {
    this.cancellationPolicy.checkScope(scope.cancellation)
    try {
      await this.callbacks.acquire(readyCallback, scope.cancellation, scope.scopeId)
    } catch {
      this.cancellationPolicy.checkScope(scope.cancellation)
      throw new Error('callback permit acquisition lost its cancellation reason')
    }
  }

  private async acquireCallbackSource(cancellation: RuntimeCancellation, readyCallback: boolean): Promise<void> {
    this.cancellationPolicy.check()
    try {
      await this.callbacks.acquire(readyCallback, cancellation)
    } catch {
      this.cancellationPolicy.check()
      if (isFailureFence(cancellation.reason)) throw cancellation.reason.produced
      throw new RunCancelled()
    }
  }

  private releaseCallback(): void {
    this.callbacks.release()
  }

  private async runScopes(root: RuntimeScope, complete: (terminals: NonEmptyTerminals) => void): Promise<void> {
    if (this.snapshot.scopes.every((scope) => scope.concurrency === 1)) {
      await this.runScopesSerial(root, complete)
      return
    }
    await this.runScopeConcurrent(root)
    if (root.terminals.length === 0) throw new Error('a completed root Flow must have a terminal')
    complete(Object.freeze(root.terminals.slice()) as NonEmptyTerminals)
  }

  private async runScopeConcurrent(scope: RuntimeScope): Promise<void> {
    const active = new Map<number, Promise<ActivationCompletion>>()
    let taskSequence = 0
    let failure: { packet: FailurePacket; failingActivationId: number | null; recoverable: boolean } | undefined

    while (scope.queueIndex < scope.queue.length || active.size > 0) {
      this.cancellationPolicy.checkScope(scope.cancellation)
      while (scope.queueIndex < scope.queue.length && active.size < scope.definition.concurrency) {
        const activation = scope.queue[scope.queueIndex]!
        scope.queueIndex += 1
        this.accounting.ready -= 1
        const sequence = taskSequence
        taskSequence += 1
        const completion = this.runActivationConcurrent(scope, activation).then(
          (): ActivationCompletion => ({ sequence, activation, failed: false, error: undefined }),
          (error: unknown): ActivationCompletion => ({ sequence, activation, failed: true, error }),
        )
        active.set(sequence, completion)
        await Promise.resolve()
      }

      if (active.size === 0) break
      const completion = await Promise.race(active.values())
      active.delete(completion.sequence)
      if (!completion.failed) continue
      const error = completion.error
      if (error instanceof RuntimeScopeFailure) {
        failure = { packet: error.packet, failingActivationId: completion.activation.activationId, recoverable: true }
      } else if (error instanceof ProducedFailure) {
        failure = {
          packet: { primary: error.failure, suppressed: error.suppressed, input: completion.activation.input },
          failingActivationId: completion.activation.activationId,
          recoverable: isRecoverableFailure(error.failure),
        }
      } else {
        if (active.size > 0) await Promise.all(active.values())
        throw error
      }

      const fence = new ProducedFailure(failure.packet.primary, failure.packet.suppressed)
      scope.cancellation.cancel(Object.freeze({ type: 'failure_fence' as const, produced: fence }))
      this.observer.publishScopeFailureFence(scope, failure.packet.primary)
      this.discardScopeReady(scope)
      if (active.size > 0) {
        const drained = await Promise.all(active.values())
        failure = { ...failure, packet: this.mergeDrainedFailures(failure.packet, drained) }
        active.clear()
      }
      if (!failure.recoverable) throw new ProducedFailure(failure.packet.primary, failure.packet.suppressed)

      let recovered: readonly Terminal[] | null | undefined
      let packet = failure.packet
      await this.recoverScope(
        scope,
        packet,
        Object.freeze(scope.terminals.slice()),
        null,
        failure.failingActivationId,
        (terminals, nextPacket) => {
          recovered = terminals
          packet = nextPacket
        },
      )
      if (recovered === undefined) throw new Error('Flow recovery completed without settlement')
      if (recovered !== null) {
        this.observer.captureScopeFinishTerminals(scope)
        scope.terminals = recovered.slice()
        scope.cancellation.close()
        return
      }
      scope.cancellation.close()
      if (scope.parent === null) throw new RunFailure(packet)
      const finish = this.observer.markScopeFinished(scope, 'failed')
      if (finish !== undefined) this.observer.publisher.publishBundle([finish])
      throw new RuntimeScopeFailure(packet)
    }

    if (!scope.combined) {
      scope.combined = true
      if (scope.definition.combine !== undefined) {
        const resultView = this.scopeResult(scope)
        let intents: readonly Intent[] = []
        try {
          await this.invokeCombine(scope, resultView, (settled) => {
            intents = settled
          })
        } catch (error) {
          if (!(error instanceof ProducedFailure) || error.failure.kind !== 'flow_combine') throw error
          let recovered: readonly Terminal[] | null | undefined
          let packet: FailurePacket = { primary: error.failure, suppressed: error.suppressed, input: scope.incomingInput }
          await this.recoverScope(scope, packet, Object.freeze(scope.terminals.slice()), resultView, null, (terminals, nextPacket) => {
            recovered = terminals
            packet = nextPacket
          })
          if (recovered === undefined) throw new Error('Flow recovery completed without settlement')
          if (recovered === null) {
            scope.cancellation.close()
            if (scope.parent === null) throw new RunFailure(packet)
            throw new RuntimeScopeFailure(packet)
          }
          this.observer.captureScopeFinishTerminals(scope)
          scope.terminals = recovered.slice()
        }
        if (intents.length > 0) {
          this.observer.captureScopeFinishTerminals(scope)
          scope.terminals = this.boundaryTerminals(scope, intents)
        }
      }
    }
    scope.cancellation.close()
  }

  private async runActivationConcurrent(scope: RuntimeScope, activation: Activation): Promise<void> {
    const placement = this.requirePlacement(activation.elementId)
    if (placement.kind === 'node') {
      let settlement: NodeSettlement | undefined
      await this.runNode(scope, placement, activation, (settled) => {
        settlement = settled
      })
      if (settlement === undefined) throw new Error('Node completed without settlement')
      this.route(
        scope,
        placement,
        activation.activationId,
        settlement.intents,
        settlement.attempt,
        settlement.previous,
        settlement.suppressed,
        settlement.attempt === null ? 'node_recover' : 'handle',
      )
      return
    }
    const child = this.newScope(
      this.requireScope(placement.ownedScopeDefinitionId),
      activation.activationId,
      activation.parentActivationId,
      activation.input,
      scope,
      placement,
    )
    await this.runScopeConcurrent(child)
    this.forwardChild(child)
  }

  private mergeDrainedFailures(packet: FailurePacket, drained: readonly ActivationCompletion[]): FailurePacket {
    const suppressed = [...packet.suppressed]
    const seen = new Set<number>([packet.primary.failureId, ...suppressed.map((failure) => failure.failureId)])
    for (const completion of drained) {
      if (!completion.failed) continue
      let failures: readonly Failure[] = []
      if (completion.error instanceof ProducedFailure) {
        failures = [completion.error.failure, ...completion.error.suppressed]
      } else if (completion.error instanceof RuntimeScopeFailure) {
        failures = [completion.error.packet.primary, ...completion.error.packet.suppressed]
      }
      for (const candidate of failures) {
        if (seen.has(candidate.failureId)) continue
        seen.add(candidate.failureId)
        suppressed.push(candidate)
      }
    }
    return { primary: packet.primary, suppressed: Object.freeze(suppressed), input: packet.input }
  }

  private async runScopesSerial(root: RuntimeScope, complete: (terminals: NonEmptyTerminals) => void): Promise<void> {
    const stack: RuntimeScope[] = [root]

    while (stack.length > 0) {
      this.cancellationPolicy.check()
      const scope = stack[stack.length - 1]!
      if (scope.queueIndex < scope.queue.length) {
        const activation = scope.queue[scope.queueIndex]!
        scope.queueIndex += 1
        this.accounting.ready -= 1
        const placement = this.requirePlacement(activation.elementId)
        if (placement.kind === 'node') {
          try {
            let settlement: NodeSettlement | undefined
            await this.runNode(scope, placement, activation, (settled) => {
              settlement = settled
            })
            if (settlement === undefined) throw new Error('Node completed without settlement')
            this.route(
              scope,
              placement,
              activation.activationId,
              settlement.intents,
              settlement.attempt,
              settlement.previous,
              settlement.suppressed,
              settlement.attempt === null ? 'node_recover' : 'handle',
            )
          } catch (error) {
            if (!(error instanceof ProducedFailure) || !isRecoverableFailure(error.failure)) throw error
            let failureCompletion: NonEmptyTerminals | null | undefined
            await this.settleScopeFailure(
              stack,
              scope,
              { primary: error.failure, suppressed: error.suppressed, input: activation.input },
              activation.activationId,
              null,
              (terminals) => {
                failureCompletion = terminals
              },
            )
            if (failureCompletion === undefined) throw new Error('scope failure completed without settlement')
            if (failureCompletion !== null) {
              complete(failureCompletion)
              return
            }
          }
          continue
        }

        const child = this.newScope(
          this.requireScope(placement.ownedScopeDefinitionId),
          activation.activationId,
          activation.parentActivationId,
          activation.input,
          scope,
          placement,
        )
        stack.push(child)
        continue
      }

      if (!scope.combined) {
        scope.combined = true
        if (scope.definition.combine !== undefined) {
          const resultView = this.scopeResult(scope)
          let intents: readonly Intent[] = []
          try {
            await this.invokeCombine(scope, resultView, (settled) => {
              intents = settled
            })
          } catch (error) {
            if (!(error instanceof ProducedFailure) || error.failure.kind !== 'flow_combine') throw error
            let failureCompletion: NonEmptyTerminals | null | undefined
            await this.settleScopeFailure(
              stack,
              scope,
              { primary: error.failure, suppressed: error.suppressed, input: scope.incomingInput },
              null,
              resultView,
              (terminals) => {
                failureCompletion = terminals
              },
            )
            if (failureCompletion === undefined) throw new Error('scope failure completed without settlement')
            if (failureCompletion !== null) {
              complete(failureCompletion)
              return
            }
            continue
          }
          if (intents.length > 0) {
            this.observer.captureScopeFinishTerminals(scope)
            scope.terminals = this.boundaryTerminals(scope, intents)
          }
        }
      }

      const completed = stack.pop()!
      if (completed.parent === null) {
        if (completed.terminals.length === 0) throw new Error('a completed root Flow must have a terminal')
        const terminals = Object.freeze(completed.terminals.slice()) as NonEmptyTerminals
        complete(terminals)
        return
      }
      this.forwardChild(completed)
    }

    throw new Error('scheduler lost its root scope')
  }

  private async settleScopeFailure(
    stack: RuntimeScope[],
    scope: RuntimeScope,
    initialPacket: FailurePacket,
    failingActivationId: number | null,
    result: ScopeResult | null,
    settle: (terminals: NonEmptyTerminals | null) => void,
  ): Promise<void> {
    let currentScope = scope
    let currentPacket = initialPacket
    let currentFailingActivationId = failingActivationId
    let currentResult = result

    while (true) {
      this.cancellationPolicy.check([currentPacket.primary, ...currentPacket.suppressed])
      const settledBeforeFence = Object.freeze(currentScope.terminals.slice())
      currentScope.cancellation.cancel(
        Object.freeze({
          type: 'failure_fence' as const,
          produced: new ProducedFailure(currentPacket.primary, currentPacket.suppressed),
        }),
      )
      this.observer.publishScopeFailureFence(currentScope, currentPacket.primary)
      this.discardScopeReady(currentScope)
      let recovered: readonly Terminal[] | null | undefined
      let nextPacket = currentPacket
      await this.recoverScope(
        currentScope,
        currentPacket,
        settledBeforeFence,
        currentResult,
        currentFailingActivationId,
        (terminals, packet) => {
          recovered = terminals
          nextPacket = packet
        },
      )
      if (recovered === undefined) throw new Error('Flow recovery completed without settlement')
      currentPacket = nextPacket

      if (recovered !== null) {
        this.observer.captureScopeFinishTerminals(currentScope)
        currentScope.terminals = recovered.slice()
        const completed = stack.pop()
        if (completed !== currentScope) throw new Error('scope failure stack ownership changed')
        completed.cancellation.close()
        if (completed.parent === null) {
          if (completed.terminals.length === 0) throw new Error('a recovered root Flow must have a terminal')
          settle(Object.freeze(completed.terminals.slice()) as NonEmptyTerminals)
          return
        }
        this.forwardChild(completed)
        settle(null)
        return
      }

      const completed = stack.pop()
      if (completed !== currentScope) throw new Error('scope failure stack ownership changed')
      completed.cancellation.close()
      if (completed.parent === null) throw new RunFailure(currentPacket)
      const finish = this.observer.markScopeFinished(completed, 'failed')
      if (finish !== undefined) this.observer.publisher.publishBundle([finish])
      currentScope = completed.parent
      currentFailingActivationId = completed.ownerActivationId
      currentResult = null
    }
  }

  private async recoverScope(
    scope: RuntimeScope,
    packet: FailurePacket,
    settledBeforeFence: readonly Terminal[],
    result: ScopeResult | null,
    failingActivationId: number | null,
    settle: (terminals: readonly Terminal[] | null, packet: FailurePacket) => void,
  ): Promise<void> {
    if (scope.definition.recover === undefined) {
      this.cancellationPolicy.check([packet.primary, ...packet.suppressed])
      settle(null, packet)
      return
    }
    const recoverySource = scope.parent === null ? this.cancellation : scope.parent.cancellation
    await this.acquireCallbackSource(recoverySource, true)
    try {
      await this.recoverScopeAdmitted(scope, packet, settledBeforeFence, result, failingActivationId, settle)
    } finally {
      this.releaseCallback()
    }
  }

  private async recoverScopeAdmitted(
    scope: RuntimeScope,
    packet: FailurePacket,
    settledBeforeFence: readonly Terminal[],
    result: ScopeResult | null,
    failingActivationId: number | null,
    settle: (terminals: readonly Terminal[] | null, packet: FailurePacket) => void,
  ): Promise<void> {
    const callback = scope.definition.recover
    this.cancellationPolicy.check([packet.primary, ...packet.suppressed])
    if (callback === undefined) {
      throw new Error('admitted Flow recovery has no callback')
    }

    const callbackSource = new RuntimeCancellation(scope.parent === null ? this.cancellation : scope.parent.cancellation)
    const context = new RuntimeContext(
      this.state,
      packet.input,
      this.runId,
      scope.scopeId,
      scope.ownerActivationId,
      scope.ownerParentActivationId,
      null,
      'flow_recover',
      callbackSource,
      () => this.callbackExecutor.remainingMs(callbackSource, undefined),
      this.makeIntentReserver(
        scope.scopeId,
        scope.ownerActivationId,
        scope.ownerPlacement.elementId,
        null,
        packet.primary,
        packet.suppressed,
        callbackSource,
      ),
      this.makeReporter(
        scope.scopeId,
        scope.ownerActivationId,
        scope.ownerPlacement.elementId,
        null,
        packet.primary,
        packet.suppressed,
        callbackSource,
      ),
    )
    const failureView: ScopeFailure = Object.freeze({
      primary: packet.primary,
      suppressed: packet.suppressed,
      settledBeforeFence,
      result,
      failingActivationId,
    })
    const classify = (error: unknown, selected: Failure | null): Failure => {
      const causal = selected ?? packet.primary
      if (error instanceof SemanticMisuse) {
        return this.failures.create(
          'invalid_combination',
          scope.scopeId,
          scope.ownerActivationId,
          scope.ownerPlacement.elementId,
          null,
          null,
          { type: 'invalid_combination', reason: error.reason },
          causal,
        )
      }
      return this.failures.create(
        'flow_recovery',
        scope.scopeId,
        scope.ownerActivationId,
        scope.ownerPlacement.elementId,
        null,
        error,
        null,
        causal,
      )
    }
    let callbackResult: unknown
    let intents: readonly Intent[]
    this.observer.publishCallbackStarted(
      scope,
      scope.ownerActivationId,
      scope.ownerParentActivationId,
      scope.ownerPlacement.elementId,
      'flow_recover',
      null,
    )
    try {
      try {
        callbackResult = await this.callbackExecutor.awaitLifecycleCallback(
          context,
          callbackSource,
          () => callback(context, failureView),
          classify,
          {
            active: [packet.primary, ...packet.suppressed],
          },
        )
      } catch (error) {
        if (!(error instanceof ProducedFailure)) {
          if (error instanceof RunCancelled || error instanceof RunAbandoned) {
            this.observer.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_recover', null, {
              kind: 'discarded',
            })
          }
          throw error
        }
        this.observer.publishCallbackFinished(
          scope.scopeId,
          scope.ownerActivationId,
          'flow_recover',
          null,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
        const replaced: FailurePacket = {
          primary: error.failure,
          suppressed: error.suppressed,
          input: packet.input,
        }
        if (!isRecoverableFailure(error.failure)) throw new RunFailure(replaced)
        settle(null, replaced)
        return
      }
    } finally {
      intents = context.close()
    }

    this.cancellationPolicy.check([packet.primary, ...packet.suppressed])
    if (callbackResult !== undefined) {
      const failure = this.failures.create(
        'invalid_combination',
        scope.scopeId,
        scope.ownerActivationId,
        scope.ownerPlacement.elementId,
        null,
        null,
        { type: 'invalid_combination', reason: 'wrong_return_type' },
        packet.primary,
      )
      this.observer.publishCallbackFinished(
        scope.scopeId,
        scope.ownerActivationId,
        'flow_recover',
        null,
        { kind: 'failure', failure },
        [failure],
      )
      throw new RunFailure(replacePacket(packet, failure))
    }
    if (intents.length === 0) {
      this.observer.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_recover', null, {
        kind: 'outcome',
        outcome: 'unhandled',
      })
      settle(null, packet)
      return
    }
    try {
      settle(this.boundaryTerminals(scope, intents, packet.primary, 'flow_recover'), packet)
    } catch (error) {
      if (!(error instanceof ProducedFailure)) throw error
      throw new RunFailure(replacePacket(packet, error.failure))
    }
  }

  private discardScopeReady(scope: RuntimeScope): void {
    const discarded = scope.queue.length - scope.queueIndex
    scope.queue.length = 0
    scope.queueIndex = 0
    this.accounting.ready -= discarded
  }

  private scopeResult(scope: RuntimeScope): ScopeResult {
    const terminals = Object.freeze(scope.terminals.slice()) as NonEmptyTerminals
    const outputs = Object.freeze(scope.terminals.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.output))
    return Object.freeze({ terminals, outputs })
  }

  private makeIntentReserver(
    scopeId: number,
    activationId: number,
    elementId: number,
    attempt: number | null,
    previous: Failure | null,
    suppressed: readonly Failure[],
    callbackSource: RuntimeCancellation,
  ): (bufferedCount: number) => void {
    return (bufferedCount): void => {
      if (callbackSource.cancelled) throw callbackSource.reason
      let limit: LimitName | null = null
      if (this.accounting.transitions + bufferedCount > this.options.maxTransitions) limit = 'max_transitions'
      else if (bufferedCount > MAX_PORTABLE_COLLECTION_LENGTH) limit = 'portable_collection'
      if (limit === null) return
      const produced = new ProducedFailure(
        this.failures.create('limit', scopeId, activationId, elementId, attempt, null, { type: 'limit', limit }, previous),
        suppressed,
      )
      this.observer.failureFence ??= produced
      const fence = Object.freeze({ type: 'failure_fence' as const, produced: this.observer.failureFence })
      callbackSource.cancel(fence)
      throw fence
    }
  }

  private makeReporter(
    scopeId: number,
    activationId: number,
    elementId: number,
    attempt: number | null,
    previous: Failure | null,
    suppressed: readonly Failure[],
    callbackSource: RuntimeCancellation,
    attemptDeadline?: RuntimeDeadline,
    timeoutFailure?: () => Failure,
  ): (context: RuntimeContext<State>, name: unknown, data: unknown, hasData: boolean) => void {
    return (context, name, data, hasData): void => {
      if (this.observer.publisher.isPublishing) {
        this.observer.publisher.rejectReentrantReport()
        return
      }
      this.cancellationPolicy.commitDeadlineIfDue()
      if (this.observer.failureFence !== undefined) {
        throw callbackSource.reason ?? this.cancellation.reason
      }
      if (this.cancellation.cancelled) {
        this.observer.publishRunCancellationIfNeeded()
        throw callbackSource.reason ?? this.cancellation.reason
      }
      if (callbackSource.cancelled) {
        throw callbackSource.reason ?? this.cancellation.reason
      }
      if (attemptDeadline?.due()) {
        if (timeoutFailure === undefined) throw new Error('attempt report checkpoint has no timeout')
        const failure = timeoutFailure()
        callbackSource.cancel('attempt_timeout')
        this.observer.publishAttemptTimeout(context, failure)
        throw callbackSource.reason
      }
      if (typeof name !== 'string' || name.length === 0) {
        throw new SemanticMisuse('report_name', 'report name must be a nonempty string')
      }
      if (this.accounting.reports >= this.options.maxReports) {
        const produced = new ProducedFailure(
          this.failures.create(
            'limit',
            scopeId,
            activationId,
            elementId,
            attempt,
            null,
            { type: 'limit', limit: 'max_reports' },
            previous,
          ),
          suppressed,
        )
        this.observer.failureFence ??= produced
        this.observer.publishRunFailureFence(this.observer.failureFence.failure)
        callbackSource.cancel(Object.freeze({ type: 'failure_fence' as const, produced: this.observer.failureFence }))
        throw callbackSource.reason
      }
      this.accounting.reports += 1
      this.observer.publisher.publish('report', Object.freeze({ scopeId, activationId, name, hasData, data }))
      this.cancellationPolicy.commitDeadlineIfDue()
      if (this.cancellation.cancelled) this.observer.publishRunCancellationIfNeeded()
      if (!callbackSource.cancelled && attemptDeadline?.due()) {
        if (timeoutFailure === undefined) throw new Error('attempt report checkpoint has no timeout')
        const failure = timeoutFailure()
        callbackSource.cancel('attempt_timeout')
        this.observer.publishAttemptTimeout(context, failure)
      }
      if (this.observer.failureFence !== undefined || this.cancellation.cancelled || callbackSource.cancelled) {
        throw callbackSource.reason ?? this.cancellation.reason
      }
    }
  }

  private newScope(
    definition: CompiledScope,
    ownerActivationId: number,
    ownerParentActivationId: number | null,
    incomingInput: unknown,
    parent: RuntimeScope | null,
    ownerPlacement: CompiledPlacement,
  ): RuntimeScope {
    let scopeId: number
    let depth: number
    if (parent === null) {
      scopeId = 1
      depth = 1
    } else {
      let limit: LimitName | null = null
      if (parent.depth + 1 > this.options.maxDepth) limit = 'max_depth'
      else if (this.accounting.activations + 1 > this.options.maxActivations) limit = 'max_activations'
      else if (this.accounting.ready + 1 > this.options.maxReady) limit = 'max_ready'
      else if (this.accounting.nextScopeId > MAX_SAFE_INTEGER || this.accounting.nextActivationId > MAX_SAFE_INTEGER)
        limit = 'safe_integer'
      if (limit !== null) {
        throw new ProducedFailure(
          this.failures.create('limit', parent.scopeId, ownerActivationId, ownerPlacement.elementId, null, null, {
            type: 'limit',
            limit,
          }),
        )
      }
      scopeId = this.accounting.nextScopeId
      this.accounting.nextScopeId += 1
      depth = parent.depth + 1
    }
    const entry: Activation = {
      elementId: definition.entryElementId,
      input: incomingInput,
      activationId: this.accounting.allocateActivationId(),
      parentActivationId: ownerActivationId,
    }
    this.accounting.scopes += 1
    this.accounting.ready += 1
    this.accounting.peakReady = Math.max(this.accounting.peakReady, this.accounting.ready)
    const runtimeScope: RuntimeScope = {
      scopeId,
      definition,
      ownerActivationId,
      ownerParentActivationId,
      incomingInput,
      parent,
      ownerPlacement,
      entryActivationId: entry.activationId,
      queue: [entry],
      queueIndex: 0,
      terminals: [],
      depth,
      directActivations: 1,
      cancellation: new RuntimeCancellation(parent === null ? this.cancellation : parent.cancellation),
      combined: false,
      finished: false,
    }
    this.runtimeScopes.set(scopeId, runtimeScope)
    if (parent !== null) {
      this.observer.publisher.publishBundle([this.observer.scopeStartedSpec(runtimeScope)])
      this.cancellationPolicy.checkScope(parent.cancellation)
    }
    return runtimeScope
  }

  private async runNode(
    scope: RuntimeScope,
    placement: CompiledNodePlacement,
    activation: Activation,
    settle: (settlement: NodeSettlement) => void,
  ): Promise<void> {
    let attempt = 1
    let previous: Failure | null = null
    let packetSuppressed: readonly Failure[] = Object.freeze([])
    while (true) {
      let activePacket: readonly Failure[] = previous === null ? packetSuppressed : [previous, ...packetSuppressed]
      this.cancellationPolicy.checkScope(scope.cancellation, activePacket)
      await this.acquireCallback(scope, attempt > 1)
      let permitHeld = true
      try {
        if (this.accounting.attempts >= this.options.maxAttempts) {
          throw new ProducedFailure(
            this.failures.create(
              'limit',
              scope.scopeId,
              activation.activationId,
              placement.elementId,
              null,
              null,
              { type: 'limit', limit: 'max_attempts' },
              previous,
            ),
            packetSuppressed,
          )
        }
        this.accounting.attempts += 1
        let intents: readonly Intent[] = []
        try {
          await this.invokeNode(scope, placement, activation, attempt, previous, packetSuppressed, (settled) => {
            intents = settled
          })
        } catch (error) {
          if (!(error instanceof ProducedFailure) || (error.failure.kind !== 'handler' && error.failure.kind !== 'handler_timeout'))
            throw error
          const failure = error.failure
          packetSuppressed = Object.freeze([...packetSuppressed, ...error.suppressed])
          previous = failure
          activePacket = [failure, ...packetSuppressed]
          this.cancellationPolicy.checkScope(scope.cancellation, activePacket)
          const shouldRetry =
            attempt < placement.retry.maxAttempts &&
            this.recovery.shouldRetry(scope, placement, activation, attempt, failure, packetSuppressed)
          if (shouldRetry) {
            if (this.accounting.attempts >= this.options.maxAttempts) {
              throw new ProducedFailure(
                this.failures.create(
                  'limit',
                  scope.scopeId,
                  activation.activationId,
                  placement.elementId,
                  null,
                  null,
                  { type: 'limit', limit: 'max_attempts' },
                  failure,
                ),
                packetSuppressed,
              )
            }
            const delayMs = this.recovery.retryDelay(scope, placement, activation, attempt, failure, packetSuppressed)
            this.accounting.retries += 1
            this.observer.publisher.publish(
              'retry_scheduled',
              Object.freeze({
                scopeId: scope.scopeId,
                activationId: activation.activationId,
                failureId: failure.failureId,
                failedAttempt: attempt,
                nextAttempt: attempt + 1,
                delayMs,
              }),
            )
            this.cancellationPolicy.checkScope(scope.cancellation, activePacket)
            this.releaseCallback()
            permitHeld = false
            if (!(await waitRetryDelay(delayMs, scope.cancellation)))
              this.cancellationPolicy.checkScope(scope.cancellation, activePacket)
            attempt += 1
            continue
          }
          this.releaseCallback()
          permitHeld = false
          this.cancellationPolicy.checkScope(scope.cancellation, activePacket)
          await this.invokeNodeRecovery(scope, placement, activation, failure, packetSuppressed, settle)
          return
        }

        if (intents.length === 0) intents = [{ kind: 'emit', action: null, value: activation.input, present: true }]
        settle({ intents, attempt, previous, suppressed: packetSuppressed })
        return
      } finally {
        if (permitHeld) this.releaseCallback()
      }
    }
  }

  private async invokeNode(
    scope: RuntimeScope,
    placement: CompiledNodePlacement,
    activation: Activation,
    attempt: number,
    previous: Failure | null,
    inheritedSuppressed: readonly Failure[],
    settle: (intents: readonly Intent[]) => void,
  ): Promise<void> {
    const handler = nodeHandlers.get(placement.definition)
    if (handler === undefined) throw new Error('compiled Node placement has no handler')
    const callbackSource = new RuntimeCancellation(scope.cancellation)
    const attemptDeadline = placement.timeoutMs === undefined ? undefined : new RuntimeDeadline(performance.now(), placement.timeoutMs)
    let timeoutFailureValue: Failure | undefined
    const timeoutFailure = (): Failure => {
      timeoutFailureValue ??= this.failures.create(
        'handler_timeout',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        null,
        null,
        previous,
      )
      return timeoutFailureValue
    }
    const context = new RuntimeContext(
      this.state,
      activation.input,
      this.runId,
      scope.scopeId,
      activation.activationId,
      activation.parentActivationId,
      attempt,
      'handle',
      callbackSource,
      () => this.callbackExecutor.remainingMs(callbackSource, attemptDeadline),
      this.makeIntentReserver(
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        previous,
        inheritedSuppressed,
        callbackSource,
      ),
      this.makeReporter(
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        previous,
        inheritedSuppressed,
        callbackSource,
        attemptDeadline,
        timeoutFailure,
      ),
    )
    const classify = (error: unknown, selected: Failure | null): Failure => {
      const causal = selected ?? previous
      if (error instanceof SemanticMisuse) {
        return this.failures.create(
          'invalid_outcome',
          scope.scopeId,
          activation.activationId,
          placement.elementId,
          attempt,
          null,
          { type: 'invalid_outcome', reason: error.reason },
          causal,
        )
      }
      return this.failures.create('handler', scope.scopeId, activation.activationId, placement.elementId, attempt, error, null, causal)
    }
    let result: unknown
    let intents: readonly Intent[]
    this.observer.publishCallbackStarted(
      scope,
      activation.activationId,
      activation.parentActivationId,
      placement.elementId,
      'handle',
      attempt,
    )
    try {
      try {
        result = await this.callbackExecutor.awaitLifecycleCallback(context, callbackSource, () => handler(context), classify, {
          active: previous === null ? inheritedSuppressed : [previous, ...inheritedSuppressed],
          ...(attemptDeadline === undefined ? {} : { attemptDeadline }),
          timeoutFailure,
        })
      } finally {
        intents = context.close()
      }
      this.cancellationPolicy.checkScope(
        scope.cancellation,
        previous === null ? inheritedSuppressed : [previous, ...inheritedSuppressed],
      )
      if (result !== undefined) {
        throw new ProducedFailure(
          this.failures.create(
            'invalid_outcome',
            scope.scopeId,
            activation.activationId,
            placement.elementId,
            attempt,
            null,
            { type: 'invalid_outcome', reason: 'wrong_return_type' },
            previous,
          ),
          inheritedSuppressed,
        )
      }
    } catch (error) {
      if (error instanceof ProducedFailure) {
        this.observer.publishCallbackFinished(
          scope.scopeId,
          activation.activationId,
          'handle',
          attempt,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
      } else if (error instanceof RunCancelled || error instanceof RunAbandoned) {
        this.observer.publishCallbackFinished(scope.scopeId, activation.activationId, 'handle', attempt, { kind: 'discarded' })
      }
      throw error
    }
    settle(intents)
  }

  private async invokeNodeRecovery(
    scope: RuntimeScope,
    placement: CompiledNodePlacement,
    activation: Activation,
    failure: Failure,
    inheritedSuppressed: readonly Failure[],
    settle: (settlement: NodeSettlement) => void,
  ): Promise<void> {
    await this.acquireCallback(scope, true)
    try {
      await this.invokeNodeRecoveryAdmitted(scope, placement, activation, failure, inheritedSuppressed, settle)
    } finally {
      this.releaseCallback()
    }
  }

  private async invokeNodeRecoveryAdmitted(
    scope: RuntimeScope,
    placement: CompiledNodePlacement,
    activation: Activation,
    failure: Failure,
    inheritedSuppressed: readonly Failure[],
    settle: (settlement: NodeSettlement) => void,
  ): Promise<void> {
    const callback = nodeRecoveries.get(placement.definition)
    if (callback === undefined) throw new ProducedFailure(failure, inheritedSuppressed)

    const callbackSource = new RuntimeCancellation(scope.cancellation)
    const context = new RuntimeContext(
      this.state,
      activation.input,
      this.runId,
      scope.scopeId,
      activation.activationId,
      activation.parentActivationId,
      null,
      'node_recover',
      callbackSource,
      () => this.callbackExecutor.remainingMs(callbackSource, undefined),
      this.makeIntentReserver(
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        null,
        failure,
        inheritedSuppressed,
        callbackSource,
      ),
      this.makeReporter(
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        null,
        failure,
        inheritedSuppressed,
        callbackSource,
      ),
    )
    const classify = (error: unknown, selected: Failure | null): Failure => {
      const causal = selected ?? failure
      if (error instanceof SemanticMisuse) {
        return this.failures.create(
          'invalid_outcome',
          scope.scopeId,
          activation.activationId,
          placement.elementId,
          null,
          null,
          { type: 'invalid_outcome', reason: error.reason },
          causal,
        )
      }
      return this.failures.create(
        'node_recovery',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        null,
        error,
        null,
        causal,
      )
    }
    let result: unknown
    let intents: readonly Intent[]
    this.observer.publishCallbackStarted(
      scope,
      activation.activationId,
      activation.parentActivationId,
      placement.elementId,
      'node_recover',
      null,
    )
    try {
      try {
        result = await this.callbackExecutor.awaitLifecycleCallback(
          context,
          callbackSource,
          () => callback(context, failure),
          classify,
          {
            active: [failure, ...inheritedSuppressed],
          },
        )
      } finally {
        intents = context.close()
      }
      this.cancellationPolicy.checkScope(scope.cancellation, [failure, ...inheritedSuppressed])
      if (result !== undefined) {
        throw new ProducedFailure(
          this.failures.create(
            'invalid_outcome',
            scope.scopeId,
            activation.activationId,
            placement.elementId,
            null,
            null,
            { type: 'invalid_outcome', reason: 'wrong_return_type' },
            failure,
          ),
          inheritedSuppressed,
        )
      }
    } catch (error) {
      if (error instanceof ProducedFailure) {
        this.observer.publishCallbackFinished(
          scope.scopeId,
          activation.activationId,
          'node_recover',
          null,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
      } else if (error instanceof RunCancelled || error instanceof RunAbandoned) {
        this.observer.publishCallbackFinished(scope.scopeId, activation.activationId, 'node_recover', null, { kind: 'discarded' })
      }
      throw error
    }
    if (intents.length === 0) {
      this.observer.publishCallbackFinished(scope.scopeId, activation.activationId, 'node_recover', null, {
        kind: 'outcome',
        outcome: 'unhandled',
      })
      throw new ProducedFailure(failure, inheritedSuppressed)
    }
    settle({ intents, attempt: null, previous: failure, suppressed: inheritedSuppressed })
  }

  private async invokeCombine(
    scope: RuntimeScope,
    resultView: ScopeResult,
    settle: (intents: readonly Intent[]) => void,
  ): Promise<void> {
    await this.acquireCallback(scope, true)
    try {
      await this.invokeCombineAdmitted(scope, resultView, settle)
    } finally {
      this.releaseCallback()
    }
  }

  private async invokeCombineAdmitted(
    scope: RuntimeScope,
    resultView: ScopeResult,
    settle: (intents: readonly Intent[]) => void,
  ): Promise<void> {
    const callback = scope.definition.combine
    if (callback === undefined) {
      settle([])
      return
    }
    const callbackSource = new RuntimeCancellation(scope.cancellation)
    const context = new RuntimeContext(
      this.state,
      scope.incomingInput,
      this.runId,
      scope.scopeId,
      scope.ownerActivationId,
      scope.ownerParentActivationId,
      null,
      'flow_combine',
      callbackSource,
      () => this.callbackExecutor.remainingMs(callbackSource, undefined),
      this.makeIntentReserver(scope.scopeId, scope.ownerActivationId, scope.ownerPlacement.elementId, null, null, [], callbackSource),
      this.makeReporter(scope.scopeId, scope.ownerActivationId, scope.ownerPlacement.elementId, null, null, [], callbackSource),
    )
    const classify = (error: unknown, selected: Failure | null): Failure => {
      if (error instanceof SemanticMisuse) {
        return this.failures.create(
          'invalid_combination',
          scope.scopeId,
          scope.ownerActivationId,
          scope.ownerPlacement.elementId,
          null,
          null,
          { type: 'invalid_combination', reason: error.reason },
          selected,
        )
      }
      return this.failures.create(
        'flow_combine',
        scope.scopeId,
        scope.ownerActivationId,
        scope.ownerPlacement.elementId,
        null,
        error,
        null,
        selected,
      )
    }
    let result: unknown
    let intents: readonly Intent[]
    this.observer.publishCallbackStarted(
      scope,
      scope.ownerActivationId,
      scope.ownerParentActivationId,
      scope.ownerPlacement.elementId,
      'flow_combine',
      null,
    )
    try {
      try {
        result = await this.callbackExecutor.awaitLifecycleCallback(
          context,
          callbackSource,
          () => callback(context, resultView),
          classify,
        )
      } finally {
        intents = context.close()
      }
      this.cancellationPolicy.checkScope(scope.cancellation)
      if (result !== undefined) {
        throw new ProducedFailure(
          this.failures.create(
            'invalid_combination',
            scope.scopeId,
            scope.ownerActivationId,
            scope.ownerPlacement.elementId,
            null,
            null,
            {
              type: 'invalid_combination',
              reason: 'wrong_return_type',
            },
          ),
        )
      }
    } catch (error) {
      if (error instanceof ProducedFailure) {
        this.observer.publishCallbackFinished(
          scope.scopeId,
          scope.ownerActivationId,
          'flow_combine',
          null,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
      } else if (error instanceof RunCancelled || error instanceof RunAbandoned) {
        this.observer.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_combine', null, { kind: 'discarded' })
      }
      throw error
    }
    if (intents.length === 0) {
      this.observer.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_combine', null, {
        kind: 'outcome',
        outcome: 'forward',
      })
    }
    settle(intents)
  }

  private route(
    scope: RuntimeScope,
    source: CompiledPlacement,
    sourceActivationId: number,
    intents: readonly Intent[],
    attempt: number | null = null,
    previous: Failure | null = null,
    suppressed: readonly Failure[] = [],
    callbackPhase?: Phase,
    forwarded = false,
    suffix: readonly EventSpec[] = [],
  ): void {
    let resolutions: Array<{ readonly kind: 'target' | 'exit' | 'end'; readonly target?: number }>
    let targetCount: number
    try {
      this.cancellationPolicy.checkScope(scope.cancellation, previous === null ? [] : [previous])
      resolutions = []
      for (const intent of intents) {
        if (intent.kind === 'end') {
          resolutions.push({ kind: 'end' })
          continue
        }
        const link = source.links.find((candidate) => candidate.action === intent.action)
        if (link !== undefined) resolutions.push({ kind: 'target', target: link.targetElementId })
        else if (intent.action === null || scope.definition.exits.includes(intent.action)) resolutions.push({ kind: 'exit' })
        else {
          throw new ProducedFailure(
            this.failures.create(
              'unknown_action',
              scope.scopeId,
              sourceActivationId,
              source.elementId,
              attempt,
              null,
              { type: 'unknown_action', action: intent.action },
              previous,
            ),
            suppressed,
          )
        }
      }

      targetCount = resolutions.filter((resolution) => resolution.kind === 'target').length
      const terminalCount = intents.length - targetCount
      this.preflightBatchCapacity(
        scope,
        source,
        sourceActivationId,
        attempt,
        previous,
        intents.length,
        targetCount,
        terminalCount,
        suppressed,
      )
    } catch (error) {
      if (error instanceof ProducedFailure) {
        if (callbackPhase !== undefined) {
          this.observer.publishCallbackFinished(
            scope.scopeId,
            sourceActivationId,
            callbackPhase,
            attempt,
            { kind: 'failure', failure: error.failure },
            [error.failure, ...error.suppressed],
          )
        } else this.observer.publishFailureRecorded(error.failure)
      }
      throw error
    }

    if (callbackPhase !== undefined) {
      this.observer.publishCallbackFinished(scope.scopeId, sourceActivationId, callbackPhase, attempt, {
        kind: 'outcome',
        outcome: this.intentOutcome(intents),
      })
      this.cancellationPolicy.checkScope(scope.cancellation, previous === null ? [] : [previous])
    }
    this.accounting.transitions += intents.length
    scope.directActivations += targetCount
    const specs: EventSpec[] = []
    for (let index = 0; index < intents.length; index += 1) {
      const intent = intents[index]!
      const resolution = resolutions[index]!
      if (resolution.kind === 'target') {
        if (resolution.target === undefined) throw new Error('target resolution has no element')
        const activationId = this.accounting.allocateActivationId()
        scope.queue.push({
          elementId: resolution.target,
          input: intent.value,
          activationId,
          parentActivationId: sourceActivationId,
        })
        this.accounting.ready += 1
        this.accounting.peakReady = Math.max(this.accounting.peakReady, this.accounting.ready)
        specs.push({
          kind: 'transition_committed',
          payload: Object.freeze({
            scopeId: scope.scopeId,
            sourceActivationId,
            branchIndex: index,
            transition: Object.freeze({
              kind: forwarded ? 'forward_exit' : 'route',
              action: intent.action,
              destination: Object.freeze({ type: 'activation', activationId, elementId: resolution.target }),
            }),
          }),
        })
      } else if (resolution.kind === 'end') {
        const terminal = this.endTerminal(intent, sourceActivationId)
        scope.terminals.push(terminal)
        specs.push(
          ...this.terminalEventSpecs(
            scope.scopeId,
            sourceActivationId,
            index,
            {
              kind: forwarded ? 'forward_end' : 'end',
              destination: Object.freeze({ type: 'terminal', sequence: terminal.sequence }),
            },
            terminal,
          ),
        )
      } else {
        const terminal: ExitTerminal = Object.freeze({
          type: 'exit',
          action: intent.action,
          hasOutput: true,
          output: intent.value,
          sequence: this.accounting.allocateTerminalSequence(),
          sourceActivationId,
        })
        scope.terminals.push(terminal)
        specs.push(
          ...this.terminalEventSpecs(
            scope.scopeId,
            sourceActivationId,
            index,
            {
              kind: forwarded ? 'forward_exit' : 'route',
              action: intent.action,
              destination: Object.freeze({ type: 'terminal', sequence: terminal.sequence }),
            },
            terminal,
          ),
        )
      }
    }
    specs.push(...suffix)
    this.observer.publisher.publishBundle(specs)
  }

  private intentOutcome(intents: readonly Intent[]): 'route' | 'fanout' | 'end' | 'forward' | 'unhandled' {
    if (intents.length > 1) return 'fanout'
    return intents[0]!.kind === 'end' ? 'end' : 'route'
  }

  private terminalEventSpecs(
    scopeId: number,
    sourceActivationId: number,
    branchIndex: number,
    transition: unknown,
    terminal: Terminal,
  ): readonly EventSpec[] {
    const metadata =
      terminal.type === 'end'
        ? Object.freeze({ kind: 'end' as const, hasOutput: terminal.hasOutput })
        : Object.freeze({ kind: 'exit' as const, action: terminal.action, hasOutput: true as const })
    return [
      {
        kind: 'transition_committed',
        payload: Object.freeze({ scopeId, sourceActivationId, branchIndex, transition }),
      },
      {
        kind: 'terminal_committed',
        payload: Object.freeze({
          scopeId,
          terminalSequence: terminal.sequence,
          sourceActivationId,
          terminal: metadata,
        }),
      },
    ]
  }

  private boundaryTerminals(
    scope: RuntimeScope,
    intents: readonly Intent[],
    previous: Failure | null = null,
    callbackPhase: Phase = 'flow_combine',
  ): Terminal[] {
    try {
      this.cancellationPolicy.check(previous === null ? [] : [previous])
      for (const intent of intents) {
        if (intent.kind === 'end') continue
        const resolved =
          scope.parent === null
            ? intent.action === null || scope.definition.exits.includes(intent.action)
            : scope.ownerPlacement.links.some((link) => link.action === intent.action) ||
              intent.action === null ||
              scope.parent.definition.exits.includes(intent.action)
        if (!resolved) {
          throw new ProducedFailure(
            this.failures.create(
              'unknown_action',
              scope.scopeId,
              scope.ownerActivationId,
              scope.ownerPlacement.elementId,
              null,
              null,
              {
                type: 'unknown_action',
                action: intent.action!,
              },
              previous,
            ),
          )
        }
      }

      this.preflightBatchCapacity(
        scope,
        scope.ownerPlacement,
        scope.ownerActivationId,
        null,
        previous,
        intents.length,
        0,
        intents.length,
      )
    } catch (error) {
      if (error instanceof ProducedFailure) {
        this.observer.publishCallbackFinished(
          scope.scopeId,
          scope.ownerActivationId,
          callbackPhase,
          null,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
      }
      throw error
    }
    this.observer.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, callbackPhase, null, {
      kind: 'outcome',
      outcome: this.intentOutcome(intents),
    })
    this.cancellationPolicy.check(previous === null ? [] : [previous])
    const terminals: Terminal[] = []
    const specs: EventSpec[] = []
    for (let branchIndex = 0; branchIndex < intents.length; branchIndex += 1) {
      const intent = intents[branchIndex]!
      let terminal: Terminal
      let transition: unknown
      if (intent.kind === 'end') {
        terminal = this.endTerminal(intent, scope.ownerActivationId)
        transition = Object.freeze({ kind: 'end', destination: Object.freeze({ type: 'terminal', sequence: terminal.sequence }) })
      } else {
        terminal = Object.freeze({
          type: 'exit',
          action: intent.action,
          hasOutput: true,
          output: intent.value,
          sequence: this.accounting.allocateTerminalSequence(),
          sourceActivationId: scope.ownerActivationId,
        })
        transition = Object.freeze({
          kind: 'route',
          action: intent.action,
          destination: Object.freeze({ type: 'terminal', sequence: terminal.sequence }),
        })
      }
      terminals.push(terminal)
      if (scope.parent === null) {
        specs.push(...this.terminalEventSpecs(scope.scopeId, scope.ownerActivationId, branchIndex, transition, terminal))
      }
    }
    this.accounting.transitions += intents.length
    this.observer.publisher.publishBundle(specs)
    return terminals
  }

  private preflightBatchCapacity(
    scope: RuntimeScope,
    source: CompiledPlacement,
    sourceActivationId: number,
    attempt: number | null,
    previous: Failure | null,
    transitionCount: number,
    targetCount: number,
    terminalCount: number,
    suppressed: readonly Failure[] = [],
  ): void {
    const queued = scope.queue.length - scope.queueIndex
    let limit: LimitName | null = null
    if (this.accounting.transitions + transitionCount > this.options.maxTransitions) limit = 'max_transitions'
    else if (
      transitionCount > MAX_PORTABLE_COLLECTION_LENGTH ||
      queued + targetCount > MAX_PORTABLE_COLLECTION_LENGTH ||
      scope.terminals.length + terminalCount > MAX_PORTABLE_COLLECTION_LENGTH
    )
      limit = 'portable_collection'
    else if (this.accounting.activations + targetCount > this.options.maxActivations) limit = 'max_activations'
    else if (scope.definition.maxActivations !== undefined && scope.directActivations + targetCount > scope.definition.maxActivations)
      limit = 'scope_max_activations'
    else if (this.accounting.ready + targetCount > this.options.maxReady) limit = 'max_ready'
    else if (
      (targetCount > 0 && this.accounting.nextActivationId + targetCount - 1 > MAX_SAFE_INTEGER) ||
      (terminalCount > 0 && this.accounting.nextTerminalSequence + terminalCount - 1 > MAX_SAFE_INTEGER)
    )
      limit = 'safe_integer'
    if (limit === null) return
    throw new ProducedFailure(
      this.failures.create(
        'limit',
        scope.scopeId,
        sourceActivationId,
        source.elementId,
        attempt,
        null,
        { type: 'limit', limit },
        previous,
      ),
      suppressed,
    )
  }

  private forwardChild(child: RuntimeScope): void {
    if (child.parent === null) throw new Error('root scope cannot be forwarded')
    const intents = child.terminals.map((terminal): Intent =>
      terminal.type === 'end'
        ? { kind: 'end', action: null, value: terminal.output, present: terminal.hasOutput }
        : { kind: 'emit', action: terminal.action, value: terminal.output, present: true },
    )
    const finish = this.observer.scopeFinishedSpec(child, 'completed')
    this.route(child.parent, child.ownerPlacement, child.ownerActivationId, intents, null, null, [], undefined, true, [finish])
    child.finished = true
  }

  private endTerminal(intent: Intent, sourceActivationId: number): EndTerminal {
    const common = {
      type: 'end' as const,
      sequence: this.accounting.allocateTerminalSequence(),
      sourceActivationId,
    }
    return intent.present
      ? Object.freeze({ ...common, hasOutput: true as const, output: intent.value })
      : Object.freeze({ ...common, hasOutput: false as const, output: undefined })
  }

  private requirePlacement(elementId: number): CompiledPlacement {
    const placement = this.placements.get(elementId)
    if (placement === undefined) throw new Error(`unknown compiled element ${elementId}`)
    return placement
  }

  private requireScope(scopeDefinitionId: number): CompiledScope {
    const scope = this.scopes.get(scopeDefinitionId)
    if (scope === undefined) throw new Error(`unknown compiled scope ${scopeDefinitionId}`)
    return scope
  }
}

class RuntimeRunHandle<State extends object> implements RunHandle<State> {
  readonly result: Promise<RunResult<State>>
  private resolveResult!: (result: RunResult<State>) => void
  private rejectResult!: (error: unknown) => void
  private settled = false

  constructor(
    private readonly cancellation: RuntimeCancellation,
    private readonly publisher: EventPublisher,
  ) {
    this.result = new Promise<RunResult<State>>((resolve, reject) => {
      this.resolveResult = resolve
      this.rejectResult = reject
    })
  }

  get done(): boolean {
    return this.settled
  }

  cancel(reason: unknown = 'cancelled'): void {
    if (this.settled || this.publisher.terminalCommitted) return
    if (this.cancellation.cancel(reason)) this.publisher.publishRunCancellation(reason, false)
  }

  complete(result: RunResult<State>): void {
    if (this.settled) throw new Error('RunHandle settled more than once')
    this.settled = true
    this.resolveResult(result)
  }

  fail(error: unknown): void {
    if (this.settled) return
    this.settled = true
    this.rejectResult(error)
  }
}

let nextRunNumber = 1

export function startRuntime<State extends object>(
  snapshot: CompiledSnapshot,
  state: State,
  options: ResolvedRunOptions,
): RunHandle<State> {
  const cancellation = new RuntimeCancellation()
  const runId = options.runId ?? `run-${nextRunNumber}`
  if (options.runId === undefined) nextRunNumber += 1
  const publisher = new EventPublisher(runId, options.observer)
  const rootScope = snapshot.scopes.find((scope) => scope.scopeDefinitionId === 1)
  if (rootScope === undefined) throw new Error('compiled runtime has no root scope')
  publisher.publishBundle([
    { kind: 'run_started', payload: Object.freeze({ rootElementId: 1, rootActivationId: 1 }) },
    {
      kind: 'scope_started',
      payload: Object.freeze({
        scopeId: 1,
        parentScopeId: null,
        ownerActivationId: 1,
        entryActivationId: 2,
        entryElementId: rootScope.entryElementId,
        flowElementId: 1,
        depth: 1,
      }),
    },
  ])
  const handle = new RuntimeRunHandle<State>(cancellation, publisher)
  const startedMs = performance.now()
  const deadline = options.deadlineMs === undefined ? undefined : new RuntimeDeadline(startedMs, options.deadlineMs)
  const deadlineStop = new AbortController()
  if (deadline !== undefined) void watchRunDeadline(cancellation, deadline, deadlineStop.signal, publisher)
  queueMicrotask(() => {
    let outcome: SerialOutcome | undefined
    void new RuntimeKernel(snapshot, state, startedMs, cancellation, runId, options, deadline, publisher)
      .run((settledOutcome) => {
        outcome = settledOutcome
      })
      .then(
        () => {
          deadlineStop.abort()
          if (outcome === undefined) {
            handle.fail(new Error('scheduler completed without a result'))
            return
          }
          if (outcome.abandonment !== null) {
            handle.complete(
              createAbandonedResult(
                state,
                outcome.terminals,
                outcome.abandonment,
                outcome.suppressed,
                outcome.stats,
                publisher.diagnostics,
              ),
            )
          } else if (outcome.cancellation !== null) {
            handle.complete(
              createCancelledResult(
                state,
                outcome.terminals,
                outcome.cancellation,
                outcome.suppressed,
                outcome.stats,
                publisher.diagnostics,
              ),
            )
          } else if (outcome.failure !== null) {
            handle.complete(
              createFailedResult(state, outcome.terminals, outcome.failure, outcome.suppressed, outcome.stats, publisher.diagnostics),
            )
          } else {
            handle.complete(createCompletedResult(state, outcome.terminals as NonEmptyTerminals, outcome.stats, publisher.diagnostics))
          }
        },
        (error: unknown) => {
          deadlineStop.abort()
          handle.fail(error)
        },
      )
  })
  return handle
}

function createAbandonedResult<State extends object>(
  state: State,
  terminals: readonly Terminal[],
  cause: Failure | CancellationInfo,
  suppressed: readonly Failure[],
  stats: RunStats,
  diagnostics: readonly ObserverDiagnostic[],
): AbandonedResult<State> {
  const result = Object.create(null) as {
    status: 'abandoned'
    state: State
    terminals: readonly Terminal[]
    cause: Failure | CancellationInfo
    suppressed: readonly Failure[]
    stats: RunStats
    diagnostics: readonly ObserverDiagnostic[]
  }
  result.status = 'abandoned'
  result.state = state
  result.terminals = terminals
  result.cause = cause
  result.suppressed = suppressed
  result.stats = stats
  result.diagnostics = diagnostics
  return Object.freeze(result)
}

function createCancelledResult<State extends object>(
  state: State,
  terminals: readonly Terminal[],
  cancellation: CancellationInfo,
  suppressed: readonly Failure[],
  stats: RunStats,
  diagnostics: readonly ObserverDiagnostic[],
): CancelledResult<State> {
  const result = Object.create(null) as {
    status: 'cancelled'
    state: State
    terminals: readonly Terminal[]
    cancellation: CancellationInfo
    suppressed: readonly Failure[]
    stats: RunStats
    diagnostics: readonly ObserverDiagnostic[]
  }
  result.status = 'cancelled'
  result.state = state
  result.terminals = terminals
  result.cancellation = cancellation
  result.suppressed = suppressed
  result.stats = stats
  result.diagnostics = diagnostics
  return Object.freeze(result)
}

function createFailedResult<State extends object>(
  state: State,
  terminals: readonly Terminal[],
  failure: Failure,
  suppressed: readonly Failure[],
  stats: RunStats,
  diagnostics: readonly ObserverDiagnostic[],
): FailedResult<State> {
  const result = Object.create(null) as {
    status: 'failed'
    state: State
    terminals: readonly Terminal[]
    failure: Failure
    suppressed: readonly Failure[]
    stats: RunStats
    diagnostics: readonly ObserverDiagnostic[]
  }
  result.status = 'failed'
  result.state = state
  result.terminals = terminals
  result.failure = failure
  result.suppressed = suppressed
  result.stats = stats
  result.diagnostics = diagnostics
  return Object.freeze(result)
}

function createCompletedResult<State extends object>(
  state: State,
  terminals: NonEmptyTerminals,
  stats: RunStats,
  diagnostics: readonly ObserverDiagnostic[],
): CompletedResult<State> {
  const result = Object.create(null) as {
    status: 'completed'
    state: State
    terminals: NonEmptyTerminals
    stats: RunStats
    diagnostics: readonly ObserverDiagnostic[]
  }
  result.status = 'completed'
  result.state = state
  result.terminals = terminals
  result.stats = stats
  result.diagnostics = diagnostics
  return Object.freeze(result)
}

export function projectState<State extends object>(handle: RunHandle<State>): Promise<State> {
  return new Promise<State>((resolve, reject) => {
    void handle.result.then(
      (result) => {
        if (result.status !== 'completed') {
          reject(new RunError(result))
          return
        }
        try {
          resolveStateCarrier(resolve, result.state)
        } catch (error) {
          reject(error)
        }
      },
      (error: unknown) => {
        reject(error)
      },
    )
  })
}

type ResolvedRunOptions = {
  readonly maxConcurrency: number | undefined
  readonly maxActivations: number
  readonly maxAttempts: number
  readonly maxTransitions: number
  readonly maxReady: number
  readonly maxReports: number
  readonly maxDepth: number
  readonly deadlineMs: number | undefined
  readonly cancelGraceMs: number
  readonly observer: Observer | undefined
  readonly runId: string | undefined
}

export function captureRunOptions(value: unknown): ResolvedRunOptions {
  const declaredKeys = [
    'maxConcurrency',
    'maxActivations',
    'maxAttempts',
    'maxTransitions',
    'maxReady',
    'maxReports',
    'maxDepth',
    'deadlineMs',
    'cancelGraceMs',
    'observer',
    'runId',
  ] as const
  const captured = Object.create(null) as Record<string, unknown>
  if (value !== undefined) {
    if (value === null || typeof value !== 'object') {
      throw new OptionValidationError('RunOptions must be a plain record')
    }
    const prototype = captureRunOptionValue(() => Reflect.getPrototypeOf(value), 'RunOptions could not be captured')
    if (prototype !== Object.prototype && prototype !== null) {
      throw new OptionValidationError('RunOptions must be a plain record')
    }
    const ownKeys = captureRunOptionValue(() => Reflect.ownKeys(value), 'RunOptions could not be captured')
    if (ownKeys.length > MAX_PORTABLE_COLLECTION_LENGTH) {
      throw new OptionValidationError('RunOptions exceed the portable limit')
    }
    const allowed = new Set<string>(declaredKeys)
    const present = new Set<string>()
    for (const key of ownKeys) {
      if (typeof key !== 'string') throw new OptionValidationError('RunOptions cannot contain symbol keys')
      if (!allowed.has(key)) {
        throw new OptionValidationError(`RunOptions contain unknown field ${JSON.stringify(key)}`)
      }
      const descriptor = captureRunOptionValue(() => Reflect.getOwnPropertyDescriptor(value, key), 'RunOptions could not be captured')
      if (descriptor === undefined || !descriptor.enumerable) {
        throw new OptionValidationError(`RunOptions field ${JSON.stringify(key)} must be enumerable`)
      }
      present.add(key)
    }
    for (const key of declaredKeys) {
      if (!present.has(key)) continue
      const field = captureRunOptionValue(() => Reflect.get(value, key), 'RunOptions could not be captured')
      if (field !== undefined) captured[key] = field
    }
  }

  const maxConcurrency =
    captured.maxConcurrency === undefined ? undefined : requireRunPositiveInteger(captured.maxConcurrency, 'RunOptions.maxConcurrency')
  const maxActivations =
    captured.maxActivations === undefined ? 100_000 : requireRunPositiveInteger(captured.maxActivations, 'RunOptions.maxActivations')
  if (maxActivations < 2) throw new OptionValidationError('RunOptions.maxActivations must be at least 2')
  const maxAttempts =
    captured.maxAttempts === undefined ? 200_000 : requireRunPositiveInteger(captured.maxAttempts, 'RunOptions.maxAttempts')
  const maxTransitions =
    captured.maxTransitions === undefined ? 200_000 : requireRunPositiveInteger(captured.maxTransitions, 'RunOptions.maxTransitions')
  const maxReady = captured.maxReady === undefined ? 100_000 : requireRunPositiveInteger(captured.maxReady, 'RunOptions.maxReady')
  const maxReports =
    captured.maxReports === undefined ? 100_000 : requireRunPositiveInteger(captured.maxReports, 'RunOptions.maxReports')
  const maxDepth = captured.maxDepth === undefined ? 32 : requireRunPositiveInteger(captured.maxDepth, 'RunOptions.maxDepth')
  const deadlineMs =
    captured.deadlineMs === undefined ? undefined : requireRunNonnegativeInteger(captured.deadlineMs, 'RunOptions.deadlineMs')
  const cancelGraceMs =
    captured.cancelGraceMs === undefined ? 1_000 : requireRunNonnegativeInteger(captured.cancelGraceMs, 'RunOptions.cancelGraceMs')
  const observer = captured.observer === undefined ? undefined : requireRunCallback<Observer>(captured.observer, 'RunOptions.observer')
  const runId = captured.runId === undefined ? undefined : requireRunControlString(captured.runId, 'RunOptions.runId')
  const eventCapacity =
    16n + 16n * BigInt(maxActivations) + 8n * BigInt(maxAttempts) + 4n * BigInt(maxTransitions) + BigInt(maxReports)
  if (eventCapacity > BigInt(MAX_PORTABLE_COLLECTION_LENGTH)) {
    throw new OptionValidationError('RunOptions event capacity exceeds the portable collection limit')
  }
  return Object.freeze({
    maxConcurrency,
    maxActivations,
    maxAttempts,
    maxTransitions,
    maxReady,
    maxReports,
    maxDepth,
    deadlineMs,
    cancelGraceMs,
    observer,
    runId,
  })
}

function captureRunOptionValue<Value>(operation: () => Value, message: string): Value {
  try {
    return operation()
  } catch (cause) {
    throw new OptionValidationError(message, { cause })
  }
}

function requireRunPositiveInteger(value: unknown, field: string): number {
  const result = requireRunSafeInteger(value, field)
  if (result <= 0) throw new OptionValidationError(`${field} must be positive`)
  return result
}

function requireRunNonnegativeInteger(value: unknown, field: string): number {
  const result = requireRunSafeInteger(value, field)
  if (result < 0) throw new OptionValidationError(`${field} must be nonnegative`)
  return result
}

function requireRunSafeInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) {
    throw new OptionValidationError(`${field} must be a safe integer`)
  }
  return Object.is(value, -0) ? 0 : value
}

function requireRunCallback<Callback extends Function>(value: unknown, field: string): Callback {
  if (typeof value !== 'function') throw new OptionValidationError(`${field} must be callable`)
  return value as Callback
}

function requireRunControlString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new OptionValidationError(`${field} must be a nonempty string`)
  }
  return value
}

async function watchRunDeadline(
  cancellation: RuntimeCancellation,
  deadline: RuntimeDeadline,
  stopSignal: AbortSignal,
  publisher: EventPublisher,
): Promise<void> {
  const stop = new AbortController()
  const abort = (): void => stop.abort()
  cancellation.signal.addEventListener('abort', abort, { once: true })
  stopSignal.addEventListener('abort', abort, { once: true })
  try {
    if (await waitRuntimeDeadline(deadline, stop.signal)) {
      if (cancellation.cancel('deadline_exceeded', true)) publisher.publishRunCancellation('deadline_exceeded', true)
    }
  } finally {
    cancellation.signal.removeEventListener('abort', abort)
    stopSignal.removeEventListener('abort', abort)
  }
}

function captureInputWrapper(value: unknown): unknown {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new SemanticMisuse('invalid_control_arguments', 'unlabelled emit input must use { input: value }')
  }
  let prototype: object | null
  let keys: readonly PropertyKey[]
  let descriptor: PropertyDescriptor | undefined
  try {
    prototype = Object.getPrototypeOf(value)
    if (prototype !== Object.prototype && prototype !== null) {
      throw new SemanticMisuse('invalid_control_arguments', 'invalid unlabelled emit input')
    }
    keys = Reflect.ownKeys(value)
    if (keys.length !== 1 || keys[0] !== 'input') {
      throw new SemanticMisuse('invalid_control_arguments', 'invalid unlabelled emit input')
    }
    descriptor = Reflect.getOwnPropertyDescriptor(value, 'input')
  } catch (error) {
    if (error instanceof SemanticMisuse) throw error
    throw error
  }
  if (descriptor === undefined || !descriptor.enumerable || !('value' in descriptor)) {
    throw new SemanticMisuse('invalid_control_arguments', 'invalid unlabelled emit input')
  }
  return descriptor.value
}

function requireRuntimeAction(value: unknown): Action {
  if (typeof value !== 'string' || value.length === 0) {
    throw new SemanticMisuse('invalid_action', 'action must be a nonempty string')
  }
  return value
}
