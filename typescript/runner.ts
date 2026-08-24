// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2026, Victor Duarte

import { CallbackContext, InvalidOutcome } from './context.js'

import type { Intent } from './context.js'
import type {
  Action,
  Completed,
  EndTerminal,
  ExitTerminal,
  Failed,
  Failure,
  FailureKind,
  RunHandle,
  RunResult,
  ScopeFailure,
  ScopeResult,
  Terminal,
} from './contracts.js'
import type { CompiledPlacement, CompiledScope, CompiledSnapshot } from './graph.js'

const missing = Symbol('missing')

export function startRuntime<State extends object>(snapshot: CompiledSnapshot, state: State): RunHandle<State> {
  return new Handle(() => new Run(snapshot, state).execute())
}

class Run<State extends object> {
  readonly snapshot: CompiledSnapshot
  readonly state: State
  nextActivationId = 1
  nextFailureId = 0
  nextScopeId = 0
  nextTerminalSequence = 0

  constructor(snapshot: CompiledSnapshot, state: State) {
    this.snapshot = snapshot
    this.state = state
  }

  async execute(): Promise<RunResult<State>> {
    const outcome = await this.runScope(1, 1, undefined)
    if (outcome.failed) {
      return Object.freeze<Failed<State>>({
        status: 'failed',
        state: this.state,
        terminals: outcome.terminals,
        failure: outcome.failure,
      })
    }
    return Object.freeze<Completed<State>>({ status: 'completed', state: this.state, terminals: outcome.terminals })
  }

  private async runScope(compiledScopeId: number, ownerActivationId: number, input: unknown): Promise<ScopeSuccess | ScopeFailed> {
    const scope = this.scope(compiledScopeId)
    const runtimeScopeId = ++this.nextScopeId
    let queue = [this.activation(scope.entryElementId, input)]
    const terminals: Terminal[] = []
    let started = 0
    let failure: FailureSignal | undefined

    while (queue.length > 0 && failure === undefined) {
      if (scope.maxActivations !== undefined && started >= scope.maxActivations) {
        const blocked = queue[0]!
        failure = this.signal(
          this.failure(
            'activation_limit',
            `Flow ${JSON.stringify(scope.name)} exceeded maxActivations`,
            runtimeScopeId,
            blocked.activationId,
            blocked.elementId,
          ),
          blocked.activationId,
          blocked.input,
        )
        break
      }

      let width = Math.min(scope.concurrency, queue.length)
      if (scope.maxActivations !== undefined) width = Math.min(width, scope.maxActivations - started)
      const batch = queue.slice(0, width)
      queue = queue.slice(width)
      started += batch.length
      const outcomes = await Promise.all(batch.map((activation) => this.runActivation(scope, runtimeScopeId, activation)))

      for (const outcome of outcomes) {
        if (outcome.failed) {
          terminals.push(...outcome.terminals)
          failure ??= outcome
          continue
        }
        for (const item of outcome.items) {
          if (item.type === 'next') {
            if (failure === undefined) queue.push(this.activation(item.elementId, item.input))
          } else {
            terminals.push(item)
          }
        }
      }
    }

    const ordered = Object.freeze(terminals.slice().sort((left, right) => left.sequence - right.sequence))
    if (failure !== undefined) {
      return this.recoverScope(scope, runtimeScopeId, ownerActivationId, failure, ordered)
    }
    if (scope.combine === undefined) return { failed: false, terminals: ordered }

    const result = this.scopeResult(ordered)
    const callback = await this.callback(scope.combine, input, result)
    if (!callback.ok) {
      const signal = this.callbackFailure(
        callback.cause,
        'flow_combine',
        'Flow combine failed',
        runtimeScopeId,
        ownerActivationId,
        scope.ownerElementId,
        null,
        input,
        result,
      )
      return this.recoverScope(scope, runtimeScopeId, ownerActivationId, signal, ordered)
    }
    if (callback.intents.length === 0) return { failed: false, terminals: ordered }

    const transformed = this.boundaryTerminals(callback.intents, ownerActivationId)
    const invalid = this.invalidRootExit(scope, transformed, runtimeScopeId)
    if (invalid !== undefined) {
      return this.recoverScope(scope, runtimeScopeId, ownerActivationId, invalid, ordered)
    }
    return { failed: false, terminals: transformed }
  }

  private async runActivation(scope: CompiledScope, runtimeScopeId: number, activation: Activation): Promise<Success | FailureSignal> {
    const placement = this.placement(activation.elementId)
    if (placement.kind === 'flow') {
      if (placement.ownedScopeId === undefined) throw new Error('compiled Flow has no owned scope')
      // ponytail: recurse by Flow depth; use an explicit stack only if real
      // workflows reach the JavaScript call-stack limit.
      const child = await this.runScope(placement.ownedScopeId, activation.activationId, activation.input)
      if (child.failed) return this.signal(child.failure, activation.activationId, activation.input, null, child.terminals)
      return this.routeChild(scope, runtimeScopeId, placement, activation, child.terminals)
    }

    const intents = await this.runNode(placement, runtimeScopeId, activation)
    if (intents.failed) return intents
    return this.routeIntents(scope, runtimeScopeId, placement, activation, intents.intents)
  }

  private async runNode(
    placement: CompiledPlacement,
    scopeId: number,
    activation: Activation,
  ): Promise<IntentSuccess | FailureSignal> {
    if (placement.handler === undefined || placement.retry === undefined) {
      throw new Error('compiled Node is incomplete')
    }
    let previous: Failure | null = null

    for (let attempt = 1; attempt <= placement.retry.maxAttempts; attempt++) {
      const callback = await this.callback(placement.handler, activation.input)
      if (callback.ok) {
        const intents =
          callback.intents.length === 0
            ? [{ kind: 'emit', action: null, value: activation.input, hasValue: true } satisfies Intent]
            : callback.intents
        return { failed: false, intents }
      }

      const kind: FailureKind = callback.cause instanceof InvalidOutcome ? 'invalid_outcome' : 'handler'
      const failure = this.failure(
        kind,
        message(callback.cause),
        scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        callback.cause,
        previous,
      )
      if (kind === 'handler' && attempt < placement.retry.maxAttempts) {
        const policy = this.retry(placement, attempt, failure)
        if (typeof policy !== 'number') {
          if (policy !== null) return this.signal(policy, activation.activationId, activation.input)
        } else {
          if (policy > 0) await new Promise((resolve) => setTimeout(resolve, policy))
          previous = failure
          continue
        }
      }
      return this.recoverNode(placement, scopeId, activation, failure)
    }
    throw new Error('retry loop did not return')
  }

  private retry(placement: CompiledPlacement, attempt: number, failure: Failure): number | null | Failure {
    if (placement.retry === undefined) throw new Error('compiled Node has no retry policy')
    try {
      const shouldRetry = placement.retry.shouldRetry(failure)
      if (typeof shouldRetry !== 'boolean') throw new TypeError('shouldRetry must return boolean')
      if (!shouldRetry) return null
      const configured = placement.retry.delayMs
      const delay = typeof configured === 'function' ? configured(attempt, failure) : configured
      if (!Number.isSafeInteger(delay) || delay < 0) throw new TypeError('delayMs must return a nonnegative safe integer')
      return delay
    } catch (cause) {
      return this.failure(
        'retry_policy',
        message(cause),
        failure.scopeId,
        failure.activationId,
        failure.elementId,
        failure.attempt,
        cause,
        failure,
      )
    }
  }

  private async recoverNode(
    placement: CompiledPlacement,
    scopeId: number,
    activation: Activation,
    failure: Failure,
  ): Promise<IntentSuccess | FailureSignal> {
    if (placement.recover === undefined) return this.signal(failure, activation.activationId, activation.input)
    const callback = await this.callback(placement.recover, activation.input, failure)
    if (!callback.ok) {
      const kind: FailureKind = callback.cause instanceof InvalidOutcome ? 'invalid_outcome' : 'node_recovery'
      return this.signal(
        this.failure(
          kind,
          message(callback.cause),
          scopeId,
          activation.activationId,
          placement.elementId,
          null,
          callback.cause,
          failure,
        ),
        activation.activationId,
        activation.input,
      )
    }
    if (callback.intents.length === 0) return this.signal(failure, activation.activationId, activation.input)
    return { failed: false, intents: callback.intents }
  }

  private async recoverScope(
    scope: CompiledScope,
    runtimeScopeId: number,
    ownerActivationId: number,
    signal: FailureSignal,
    terminals: readonly Terminal[],
  ): Promise<ScopeSuccess | ScopeFailed> {
    if (scope.recover === undefined) return { failed: true, terminals, failure: signal.failure }
    const scopeFailure = Object.freeze<ScopeFailure>({
      primary: signal.failure,
      terminals,
      result: signal.result,
      failingActivationId: signal.activationId,
    })
    const callback = await this.callback(scope.recover, signal.input, scopeFailure)
    if (!callback.ok) {
      const kind: FailureKind = callback.cause instanceof InvalidOutcome ? 'invalid_outcome' : 'flow_recovery'
      return {
        failed: true,
        terminals,
        failure: this.failure(
          kind,
          message(callback.cause),
          runtimeScopeId,
          ownerActivationId,
          scope.ownerElementId,
          null,
          callback.cause,
          signal.failure,
        ),
      }
    }
    if (callback.intents.length === 0) return { failed: true, terminals, failure: signal.failure }

    const transformed = this.boundaryTerminals(callback.intents, ownerActivationId)
    const invalid = this.invalidRootExit(scope, transformed, runtimeScopeId)
    if (invalid !== undefined) return { failed: true, terminals, failure: invalid.failure }
    return { failed: false, terminals: transformed }
  }

  private async callback(callback: Function, input: unknown, extra: unknown | typeof missing = missing): Promise<CallbackResult> {
    const context = new CallbackContext(this.state, input)
    try {
      const value = await (extra === missing ? callback(context) : callback(context, extra))
      if (value !== undefined) throw new InvalidOutcome('callbacks must return undefined')
      return { ok: true, intents: context.close() }
    } catch (cause) {
      context.close()
      return { ok: false, cause }
    }
  }

  private routeIntents(
    scope: CompiledScope,
    scopeId: number,
    placement: CompiledPlacement,
    activation: Activation,
    intents: readonly Intent[],
  ): Success | FailureSignal {
    const destinations: { readonly intent: Intent; readonly target: number | undefined }[] = []
    for (const intent of intents) {
      if (intent.kind === 'end') {
        destinations.push({ intent, target: undefined })
        continue
      }
      const target = placement.links.find((link) => link.action === intent.action)?.targetElementId
      if (target === undefined && intent.action !== null && !scope.exits.includes(intent.action)) {
        return this.signal(
          this.failure(
            'unknown_action',
            `unknown action ${JSON.stringify(intent.action)} from ${JSON.stringify(placement.name)}`,
            scopeId,
            activation.activationId,
            placement.elementId,
          ),
          activation.activationId,
          activation.input,
        )
      }
      destinations.push({ intent, target })
    }

    const items: (Terminal | Next)[] = []
    for (const { intent, target } of destinations) {
      if (intent.kind === 'end') {
        items.push(this.endTerminal(intent.hasValue, intent.value, activation.activationId))
      } else if (target !== undefined) {
        items.push({ type: 'next', elementId: target, input: intent.value })
      } else {
        items.push(this.exitTerminal(intent.action, intent.value, activation.activationId))
      }
    }
    return { failed: false, items }
  }

  private routeChild(
    scope: CompiledScope,
    scopeId: number,
    placement: CompiledPlacement,
    activation: Activation,
    terminals: readonly Terminal[],
  ): Success | FailureSignal {
    const items: (Terminal | Next)[] = []
    for (const terminal of terminals) {
      if (terminal.type === 'end') {
        items.push(terminal)
        continue
      }
      const routed = this.routeIntents(scope, scopeId, placement, activation, [
        { kind: 'emit', action: terminal.action, value: terminal.output, hasValue: true },
      ])
      if (routed.failed) return routed
      items.push(...routed.items)
    }
    return { failed: false, items }
  }

  private boundaryTerminals(intents: readonly Intent[], sourceActivationId: number): readonly Terminal[] {
    return Object.freeze(
      intents.map((intent) =>
        intent.kind === 'end'
          ? this.endTerminal(intent.hasValue, intent.value, sourceActivationId)
          : this.exitTerminal(intent.action, intent.value, sourceActivationId),
      ),
    )
  }

  private invalidRootExit(scope: CompiledScope, terminals: readonly Terminal[], runtimeScopeId: number): FailureSignal | undefined {
    if (scope.parentScopeId !== null) return undefined
    for (const terminal of terminals) {
      if (terminal.type === 'exit' && terminal.action !== null && !scope.exits.includes(terminal.action)) {
        return this.signal(
          this.failure(
            'unknown_action',
            `unknown root exit ${JSON.stringify(terminal.action)}`,
            runtimeScopeId,
            terminal.sourceActivationId,
            scope.ownerElementId,
          ),
          terminal.sourceActivationId,
          terminal.output,
        )
      }
    }
    return undefined
  }

  private callbackFailure(
    cause: unknown,
    ordinaryKind: FailureKind,
    failureMessage: string,
    scopeId: number,
    activationId: number,
    elementId: number,
    attempt: number | null,
    input: unknown,
    result: ScopeResult | null,
  ): FailureSignal {
    const kind = cause instanceof InvalidOutcome ? 'invalid_outcome' : ordinaryKind
    return this.signal(
      this.failure(
        kind,
        cause instanceof InvalidOutcome ? message(cause) : failureMessage,
        scopeId,
        activationId,
        elementId,
        attempt,
        cause,
      ),
      activationId,
      input,
      result,
    )
  }

  private scopeResult(terminals: readonly Terminal[]): ScopeResult {
    return Object.freeze({
      terminals,
      outputs: Object.freeze(terminals.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.output)),
    })
  }

  private failure(
    kind: FailureKind,
    failureMessage: string,
    scopeId: number,
    activationId: number | null,
    elementId: number | null,
    attempt: number | null = null,
    cause: unknown = null,
    previous: Failure | null = null,
  ): Failure {
    return Object.freeze({
      failureId: ++this.nextFailureId,
      kind,
      message: failureMessage,
      cause,
      scopeId,
      activationId,
      elementId,
      attempt,
      previous,
    })
  }

  private signal(
    failure: Failure,
    activationId: number | null,
    input: unknown,
    result: ScopeResult | null = null,
    terminals: readonly Terminal[] = [],
  ): FailureSignal {
    return { failed: true, failure, activationId, input, result, terminals }
  }

  private activation(elementId: number, input: unknown): Activation {
    return { activationId: ++this.nextActivationId, elementId, input }
  }

  private endTerminal(hasOutput: boolean, output: unknown, sourceActivationId: number): EndTerminal {
    const shared = { type: 'end' as const, sequence: ++this.nextTerminalSequence, sourceActivationId }
    return hasOutput
      ? Object.freeze({ ...shared, hasOutput: true as const, output })
      : Object.freeze({ ...shared, hasOutput: false as const, output: undefined })
  }

  private exitTerminal(action: Action | null, output: unknown, sourceActivationId: number): ExitTerminal {
    return Object.freeze({
      type: 'exit',
      action,
      hasOutput: true,
      output,
      sequence: ++this.nextTerminalSequence,
      sourceActivationId,
    })
  }

  private scope(scopeId: number): CompiledScope {
    const scope = this.snapshot.scopes[scopeId - 1]
    if (scope === undefined) throw new Error('compiled scope is missing')
    return scope
  }

  private placement(elementId: number): CompiledPlacement {
    const placement = this.snapshot.placements[elementId - 1]
    if (placement === undefined) throw new Error('compiled placement is missing')
    return placement
  }
}

interface Activation {
  readonly activationId: number
  readonly elementId: number
  readonly input: unknown
}

interface Next {
  readonly type: 'next'
  readonly elementId: number
  readonly input: unknown
}

interface Success {
  readonly failed: false
  readonly items: readonly (Terminal | Next)[]
}

interface IntentSuccess {
  readonly failed: false
  readonly intents: readonly Intent[]
}

interface FailureSignal {
  readonly failed: true
  readonly failure: Failure
  readonly activationId: number | null
  readonly input: unknown
  readonly result: ScopeResult | null
  readonly terminals: readonly Terminal[]
}

interface ScopeSuccess {
  readonly failed: false
  readonly terminals: readonly Terminal[]
}

interface ScopeFailed {
  readonly failed: true
  readonly terminals: readonly Terminal[]
  readonly failure: Failure
}

type CallbackResult = { readonly ok: true; readonly intents: readonly Intent[] } | { readonly ok: false; readonly cause: unknown }

class Handle<State extends object> implements RunHandle<State> {
  readonly #promise: Promise<RunResult<State>>
  #done = false

  constructor(run: () => Promise<RunResult<State>>) {
    this.#promise = Promise.resolve()
      .then(run)
      .finally(() => {
        this.#done = true
      })
  }

  done(): boolean {
    return this.#done
  }

  result(): Promise<RunResult<State>> {
    return this.#promise
  }
}

function message(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause)
}
