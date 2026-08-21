// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

export const MAX_SAFE_INTEGER = 9_007_199_254_740_991
export const MAX_PORTABLE_COLLECTION_LENGTH = 4_294_967_295
export const RUN_EVENT_SCHEMA_VERSION = 1
const MAX_HOST_TIMER_DELAY_MS = 2_147_483_647

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

const stateInvariant: unique symbol = Symbol('caskada.stateInvariant')
const nodeConstructionToken: unique symbol = Symbol('caskada.nodeConstructionToken')
const compiledFlowConstructionToken: unique symbol = Symbol('caskada.compiledFlowConstructionToken')
const intrinsicPromiseThen = Promise.prototype.then

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

interface EndTerminalBase {
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

const failureMessages: Readonly<Record<FailureKind, string>> = Object.freeze({
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
    super(
      result.status === 'failed'
        ? 'Caskada run failed'
        : result.status === 'cancelled'
          ? 'Caskada run cancelled'
          : 'Caskada run abandoned',
    )
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

export interface Link<State extends object = Record<string, unknown>> {
  readonly action: Action | null
  readonly target: GraphElement<State>
}

const graphNames = new WeakMap<object, string>()
const graphLinks = new WeakMap<object, Link<any>[]>()
const graphLinkActions = new WeakMap<object, Set<string | symbol>>()
const unlabelled = Symbol('caskada.unlabelled')

export abstract class GraphElement<State extends object = Record<string, unknown>> {
  declare private readonly [stateInvariant]: (state: State) => State
  protected abstract readonly _caskadaKind: 'node' | 'flow'

  protected constructor(name: string) {
    if (new.target === GraphElement) throw new TypeError('GraphElement is abstract')
    graphNames.set(this, requireControlString(name, 'element name'))
    graphLinks.set(this, [])
    graphLinkActions.set(this, new Set())
  }

  get name(): string {
    return requireGraphValue(graphNames, this, 'GraphElement name')
  }

  link(target: GraphElement<State>): void
  link(target: GraphElement<State>, action: Action): void
  link(target: GraphElement<State>, action?: Action): void {
    if (arguments.length !== 1 && arguments.length !== 2) {
      throw new GraphDefinitionError('link() accepts a target and an optional action')
    }
    if (!(target instanceof GraphElement)) {
      throw new GraphDefinitionError('link target must be a GraphElement')
    }

    const hasAction = arguments.length === 2
    let publicAction: string | null
    let key: string | symbol
    if (hasAction) {
      publicAction = requireControlString(action, 'link action')
      key = publicAction
    } else {
      publicAction = null
      key = unlabelled
    }
    const actions = requireGraphValue(graphLinkActions, this, 'GraphElement action map')
    if (actions.has(key)) {
      const description = key === unlabelled ? 'unlabelled' : JSON.stringify(publicAction)
      throw new DuplicateLinkError(`duplicate link action: ${description}`)
    }

    const records = requireGraphValue(graphLinks, this, 'GraphElement links')
    if (records.length >= MAX_PORTABLE_COLLECTION_LENGTH) {
      throw new GraphDefinitionError('link collection exceeds the portable limit')
    }
    const record = Object.freeze({ action: publicAction, target })
    actions.add(key)
    records.push(record)
  }

  links(): readonly Link<State>[] {
    const records = requireGraphValue(graphLinks, this, 'GraphElement links')
    return Object.freeze(records.slice()) as readonly Link<State>[]
  }
}

const nodeHandlers = new WeakMap<object, NodeHandler<object, unknown>>()
const nodeRecoveries = new WeakMap<object, NodeRecoveryHandler<object, unknown> | undefined>()
const nodeRetries = new WeakMap<object, RetryPolicy>()
const nodeTimeouts = new WeakMap<object, number | undefined>()

export class Node<State extends object = Record<string, unknown>> extends GraphElement<State> {
  protected readonly _caskadaKind = 'node' as const

  constructor(token: typeof nodeConstructionToken) {
    if (new.target !== Node || token !== nodeConstructionToken) {
      throw new TypeError('Use node(handler) to create a Node')
    }
    super('anonymous')
  }

  get retry(): RetryPolicy {
    return requireGraphValue(nodeRetries, this, 'Node retry policy')
  }

  get timeoutMs(): number | undefined {
    return nodeTimeouts.get(this)
  }
}

export interface NodeOptions<State extends object = Record<string, unknown>, Input = unknown> {
  readonly name?: string | undefined
  readonly retry?: RetryOptions | undefined
  readonly timeoutMs?: number | undefined
  readonly recover?: NodeRecoveryHandler<State, Input> | undefined
}

export interface FlowOptions<State extends object = Record<string, unknown>> {
  readonly name?: string | undefined
  readonly exits?: readonly Action[] | undefined
  readonly concurrency?: number | undefined
  readonly maxActivations?: number | undefined
  readonly combine?: FlowCombineHandler<State> | undefined
  readonly recover?: FlowRecoveryHandler<State> | undefined
}

const flowEntries = new WeakMap<object, GraphElement<any>>()
const flowExits = new WeakMap<object, readonly string[]>()
const flowConcurrencies = new WeakMap<object, number>()
const flowMaxActivations = new WeakMap<object, number | undefined>()
const flowCombiners = new WeakMap<object, FlowCombineHandler<object> | undefined>()
const flowRecoveries = new WeakMap<object, FlowRecoveryHandler<object> | undefined>()

export class Flow<State extends object = Record<string, unknown>> extends GraphElement<State> {
  protected readonly _caskadaKind = 'flow' as const

  constructor(entry: GraphElement<State>, options?: FlowOptions<State>) {
    if (new.target !== Flow) throw new TypeError('Flow subclasses are not supported')
    if (!(entry instanceof GraphElement)) {
      throw new GraphDefinitionError('Flow.entry must be a GraphElement')
    }

    const captured = captureOptions(options, ['name', 'exits', 'concurrency', 'maxActivations', 'combine', 'recover'], 'Flow')
    const name = captured.name === undefined ? 'Flow' : requireControlString(captured.name, 'Flow.name')
    const exits = captured.exits === undefined ? Object.freeze([]) : captureExits(captured.exits)
    const concurrency = captured.concurrency === undefined ? 1 : requirePositiveInteger(captured.concurrency, 'Flow.concurrency')
    const maxActivations =
      captured.maxActivations === undefined ? undefined : requirePositiveInteger(captured.maxActivations, 'Flow.maxActivations')
    const combine = requireOptionalCallback<FlowCombineHandler<State>>(captured.combine, 'Flow.combine')
    const recover = requireOptionalCallback<FlowRecoveryHandler<State>>(captured.recover, 'Flow.recover')

    super(name)
    flowEntries.set(this, entry)
    flowExits.set(this, exits)
    flowConcurrencies.set(this, concurrency)
    flowMaxActivations.set(this, maxActivations)
    flowCombiners.set(this, combine as FlowCombineHandler<object> | undefined)
    flowRecoveries.set(this, recover as FlowRecoveryHandler<object> | undefined)
  }

  get entry(): GraphElement<State> {
    return requireGraphValue(flowEntries, this, 'Flow entry') as GraphElement<State>
  }

  get exits(): readonly Action[] {
    return requireGraphValue(flowExits, this, 'Flow exits')
  }

  get concurrency(): number {
    return requireGraphValue(flowConcurrencies, this, 'Flow concurrency')
  }

  get maxActivations(): number | undefined {
    return flowMaxActivations.get(this)
  }

  compile(): CompiledFlow<State> {
    return compileFlow(this)
  }

  start(initialState: Readonly<State>, options?: RunOptions): RunHandle<State> {
    const capturedOptions = captureRunOptions(options)
    const compiled = this.compile()
    const snapshot = requireGraphValue(compiledSnapshots, compiled, 'CompiledFlow snapshot')
    const state = captureInitialState(initialState)
    return startRuntime(snapshot, state, capturedOptions)
  }

  run(initialState: Readonly<State>, options?: RunOptions): Promise<State> {
    return projectState(this.start(initialState, options))
  }
}

export interface CompiledLinkDescription {
  readonly action: Action | null
  readonly target_element_id: number
}

export interface CompiledNodeDescription {
  readonly element_id: number
  readonly kind: 'node'
  readonly name: string
  readonly parent_scope_definition_id: number
  readonly links: readonly CompiledLinkDescription[]
  readonly retry: { readonly max_attempts: number }
  readonly timeout_ms: number | null
}

export interface CompiledFlowElementDescription {
  readonly element_id: number
  readonly kind: 'flow'
  readonly name: string
  readonly parent_scope_definition_id: number | null
  readonly owned_scope_definition_id: number
  readonly links: readonly CompiledLinkDescription[]
}

export type CompiledElementDescription = CompiledNodeDescription | CompiledFlowElementDescription

export interface CompiledScopeDescription {
  readonly scope_definition_id: number
  readonly owner_element_id: number
  readonly parent_scope_definition_id: number | null
  readonly entry_element_id: number
  readonly exits: readonly Action[]
  readonly concurrency: number
  readonly max_activations: number | null
}

export interface CompiledDescription {
  readonly schema_version: 1
  readonly auto_max_concurrency: number
  readonly root: {
    readonly element_id: number
    readonly scope_definition_id: number
  }
  readonly scope_definitions: readonly CompiledScopeDescription[]
  readonly elements: readonly CompiledElementDescription[]
}

type CompiledLink = {
  readonly action: Action | null
  readonly targetElementId: number
}

type CompiledPlacementBase = {
  readonly elementId: number
  readonly name: string
  readonly parentScopeDefinitionId: number | null
  readonly definition: GraphElement<any>
  readonly links: readonly CompiledLink[]
}

type CompiledNodePlacement = CompiledPlacementBase & {
  readonly kind: 'node'
  readonly definition: Node<any>
  readonly retry: RetryPolicy
  readonly timeoutMs: number | undefined
}

type CompiledFlowPlacement = CompiledPlacementBase & {
  readonly kind: 'flow'
  readonly definition: Flow<any>
  readonly ownedScopeDefinitionId: number
}

type CompiledPlacement = CompiledNodePlacement | CompiledFlowPlacement

type CompiledScope = {
  readonly scopeDefinitionId: number
  readonly ownerElementId: number
  readonly parentScopeDefinitionId: number | null
  readonly entryElementId: number
  readonly exits: readonly Action[]
  readonly concurrency: number
  readonly maxActivations: number | undefined
  readonly flow: Flow<any>
  readonly combine: FlowCombineHandler<any> | undefined
  readonly recover: FlowRecoveryHandler<any> | undefined
}

type CompiledSnapshot = {
  readonly root: Flow<any>
  readonly autoMaxConcurrency: number
  readonly scopes: readonly CompiledScope[]
  readonly placements: readonly CompiledPlacement[]
}

type ScopeWork = {
  readonly scopeDefinitionId: number
  readonly ownerElementId: number
  readonly parentScopeDefinitionId: number | null
  readonly flow: Flow<any>
}

const compiledSnapshots = new WeakMap<object, CompiledSnapshot>()
const stateTargets = new WeakMap<object, Record<string, unknown>>()

export class CompiledFlow<State extends object = Record<string, unknown>> {
  constructor(token: typeof compiledFlowConstructionToken) {
    if (new.target !== CompiledFlow || token !== compiledFlowConstructionToken) {
      throw new TypeError('Use Flow.compile() to create a CompiledFlow')
    }
  }

  start(initialState: Readonly<State>, options?: RunOptions): RunHandle<State> {
    const capturedOptions = captureRunOptions(options)
    const snapshot = requireGraphValue(compiledSnapshots, this, 'CompiledFlow snapshot')
    const state = captureInitialState(initialState)
    return startRuntime(snapshot, state, capturedOptions)
  }

  run(initialState: Readonly<State>, options?: RunOptions): Promise<State> {
    return projectState(this.start(initialState, options))
  }

  describe(): CompiledDescription {
    const snapshot = requireGraphValue(compiledSnapshots, this, 'CompiledFlow snapshot')
    return describeCompiled(snapshot)
  }
}

class DefinitionCompiler {
  private nextElementId = 2
  private nextScopeDefinitionId = 2
  private compiledConnectionCount = 0
  private compiledExitCount = 0
  private readonly placementsById = new Map<number, CompiledPlacement>()
  private readonly ownedScopeByElement = new Map<number, number>([[1, 1]])
  private readonly scopeQueue: ScopeWork[]
  private readonly compiledScopes: CompiledScope[] = []

  constructor(private readonly root: Flow<any>) {
    this.placementsById.set(1, {
      elementId: 1,
      kind: 'flow',
      name: root.name,
      parentScopeDefinitionId: null,
      definition: root,
      links: [],
      ownedScopeDefinitionId: 1,
    })
    this.scopeQueue = [
      {
        scopeDefinitionId: 1,
        ownerElementId: 1,
        parentScopeDefinitionId: null,
        flow: root,
      },
    ]
  }

  compile(): CompiledSnapshot {
    for (let scopeIndex = 0; scopeIndex < this.scopeQueue.length; scopeIndex += 1) {
      this.compileScope(this.scopeQueue[scopeIndex]!)
    }
    const placements: CompiledPlacement[] = []
    for (let elementId = 1; elementId < this.nextElementId; elementId += 1) {
      const placement = this.placementsById.get(elementId)
      if (placement === undefined) throw new Error('compiled element ID gap')
      placements.push(placement)
    }
    let autoMaxConcurrency = 1
    for (const scope of this.compiledScopes) {
      if (scope.concurrency > autoMaxConcurrency) autoMaxConcurrency = scope.concurrency
    }
    return {
      root: this.root,
      autoMaxConcurrency,
      scopes: this.compiledScopes.slice(),
      placements,
    }
  }

  private compileScope(scope: ScopeWork): void {
    this.compiledExitCount = reservePortableTotal(this.compiledExitCount, scope.flow.exits.length, 'exit')
    const placements = new Map<GraphElement<any>, number>()
    const placementQueue: GraphElement<any>[] = []
    const entryElementId = this.enqueue(scope, scope.flow.entry, placements, placementQueue)

    for (let placementIndex = 0; placementIndex < placementQueue.length; placementIndex += 1) {
      const element = placementQueue[placementIndex]!
      const elementId = placements.get(element)!
      const definitionLinks = element.links()
      this.compiledConnectionCount = reservePortableTotal(this.compiledConnectionCount, definitionLinks.length, 'connection')
      const links = definitionLinks.map((link) => ({
        action: link.action,
        targetElementId: this.enqueue(scope, link.target, placements, placementQueue),
      }))
      this.capturePlacement(scope, element, elementId, links)
    }

    this.compiledScopes.push({
      scopeDefinitionId: scope.scopeDefinitionId,
      ownerElementId: scope.ownerElementId,
      parentScopeDefinitionId: scope.parentScopeDefinitionId,
      entryElementId,
      exits: scope.flow.exits.slice(),
      concurrency: scope.flow.concurrency,
      maxActivations: scope.flow.maxActivations,
      flow: scope.flow,
      combine: flowCombiners.get(scope.flow),
      recover: flowRecoveries.get(scope.flow),
    })
  }

  private enqueue(
    scope: ScopeWork,
    element: GraphElement<any>,
    placements: Map<GraphElement<any>, number>,
    placementQueue: GraphElement<any>[],
  ): number {
    const kind = graphDefinitionKind(element)
    if (kind === null) throw new GraphDefinitionError('unsupported GraphElement definition')
    const existing = placements.get(element)
    if (existing !== undefined) return existing
    requireCompiledCapacity(this.nextElementId, 'element')
    const elementId = this.nextElementId
    this.nextElementId += 1
    placements.set(element, elementId)
    placementQueue.push(element)

    if (kind === 'flow') {
      const nested = element as Flow<any>
      requireCompiledCapacity(this.nextScopeDefinitionId, 'scope')
      const ownedScopeId = this.nextScopeDefinitionId
      this.nextScopeDefinitionId += 1
      this.ownedScopeByElement.set(elementId, ownedScopeId)
      this.scopeQueue.push({
        scopeDefinitionId: ownedScopeId,
        ownerElementId: elementId,
        parentScopeDefinitionId: scope.scopeDefinitionId,
        flow: nested,
      })
    }
    return elementId
  }

  private capturePlacement(scope: ScopeWork, element: GraphElement<any>, elementId: number, links: readonly CompiledLink[]): void {
    if (graphDefinitionKind(element) === 'node') {
      const occurrence = element as Node<any>
      this.placementsById.set(elementId, {
        elementId,
        kind: 'node',
        name: occurrence.name,
        parentScopeDefinitionId: scope.scopeDefinitionId,
        definition: occurrence,
        links: links.slice(),
        retry: occurrence.retry,
        timeoutMs: occurrence.timeoutMs,
      })
      return
    }
    const occurrence = element as Flow<any>
    const ownedScopeDefinitionId = this.ownedScopeByElement.get(elementId)
    if (ownedScopeDefinitionId === undefined) {
      throw new Error('compiled Flow placement has no owned scope')
    }
    this.placementsById.set(elementId, {
      elementId,
      kind: 'flow',
      name: occurrence.name,
      parentScopeDefinitionId: scope.scopeDefinitionId,
      definition: occurrence,
      links: links.slice(),
      ownedScopeDefinitionId,
    })
  }
}

function compileFlow<State extends object>(root: Flow<State>): CompiledFlow<State> {
  if (!flowEntries.has(root)) {
    throw new GraphDefinitionError('only runtime-created Flow definitions can compile')
  }
  validateContainment(root)
  const snapshot = new DefinitionCompiler(root).compile()
  const compiled = new CompiledFlow<State>(compiledFlowConstructionToken)
  compiledSnapshots.set(compiled, snapshot)
  return compiled
}

function validateContainment(root: Flow<any>): void {
  const adjacency = new Map<Flow<any>, readonly Flow<any>[]>()
  const colors = new Map<Flow<any>, 'active' | 'complete'>([[root, 'active']])
  const stack: Array<{ flow: Flow<any>; childIndex: number }> = [{ flow: root, childIndex: 0 }]

  while (stack.length > 0) {
    const frame = stack[stack.length - 1]!
    let children = adjacency.get(frame.flow)
    if (children === undefined) {
      children = nestedFlowDefinitions(frame.flow)
      adjacency.set(frame.flow, children)
    }
    if (frame.childIndex >= children.length) {
      colors.set(frame.flow, 'complete')
      stack.pop()
      continue
    }

    const child = children[frame.childIndex]!
    frame.childIndex += 1
    const color = colors.get(child)
    if (color === 'active') throw new GraphDefinitionError('recursive Flow containment is not allowed')
    if (color === 'complete') continue
    colors.set(child, 'active')
    stack.push({ flow: child, childIndex: 0 })
  }
}

function nestedFlowDefinitions(flow: Flow<any>): readonly Flow<any>[] {
  const seen = new Set<GraphElement<any>>()
  const worklist: GraphElement<any>[] = [flow.entry]
  const nested: Flow<any>[] = []
  for (let workIndex = 0; workIndex < worklist.length; workIndex += 1) {
    const element = worklist[workIndex]!
    if (seen.has(element)) continue
    seen.add(element)
    const kind = graphDefinitionKind(element)
    if (kind === null) throw new GraphDefinitionError('unsupported GraphElement definition')
    if (kind === 'flow') nested.push(element as Flow<any>)
    for (const link of element.links()) worklist.push(link.target)
  }
  return nested
}

function graphDefinitionKind(element: GraphElement<any>): 'node' | 'flow' | null {
  if (nodeHandlers.has(element)) return 'node'
  if (flowEntries.has(element)) return 'flow'
  return null
}

function requireCompiledCapacity(nextId: number, kind: string): void {
  if (nextId > MAX_SAFE_INTEGER || nextId > MAX_PORTABLE_COLLECTION_LENGTH) {
    throw new GraphDefinitionError(`compiled ${kind} collection exceeds the portable limit`)
  }
}

function reservePortableTotal(current: number, addition: number, kind: string): number {
  if (addition > MAX_PORTABLE_COLLECTION_LENGTH - current) {
    throw new GraphDefinitionError(`compiled ${kind} collection exceeds the portable limit`)
  }
  return current + addition
}

function describeCompiled(snapshot: CompiledSnapshot): CompiledDescription {
  const elements = snapshot.placements.map((placement): CompiledElementDescription => {
    const links = Object.freeze(
      placement.links.map((link) => Object.freeze({ action: link.action, target_element_id: link.targetElementId })),
    )
    if (placement.kind === 'node') {
      if (placement.parentScopeDefinitionId === null || placement.retry === undefined) {
        throw new Error('invalid compiled Node placement')
      }
      return Object.freeze({
        element_id: placement.elementId,
        kind: 'node',
        name: placement.name,
        parent_scope_definition_id: placement.parentScopeDefinitionId,
        links,
        retry: Object.freeze({ max_attempts: placement.retry.maxAttempts }),
        timeout_ms: placement.timeoutMs ?? null,
      })
    }
    if (placement.ownedScopeDefinitionId === undefined) {
      throw new Error('invalid compiled Flow placement')
    }
    return Object.freeze({
      element_id: placement.elementId,
      kind: 'flow',
      name: placement.name,
      parent_scope_definition_id: placement.parentScopeDefinitionId,
      owned_scope_definition_id: placement.ownedScopeDefinitionId,
      links,
    })
  })

  const scopeDefinitions = snapshot.scopes.map((scope) =>
    Object.freeze({
      scope_definition_id: scope.scopeDefinitionId,
      owner_element_id: scope.ownerElementId,
      parent_scope_definition_id: scope.parentScopeDefinitionId,
      entry_element_id: scope.entryElementId,
      exits: Object.freeze(scope.exits.slice()),
      concurrency: scope.concurrency,
      max_activations: scope.maxActivations ?? null,
    }),
  )
  return Object.freeze({
    schema_version: 1,
    auto_max_concurrency: snapshot.autoMaxConcurrency,
    root: Object.freeze({ element_id: 1, scope_definition_id: 1 }),
    scope_definitions: Object.freeze(scopeDefinitions),
    elements: Object.freeze(elements),
  })
}

export function node<State extends object = Record<string, unknown>, Input = unknown>(
  handler: NodeHandler<State, Input>,
  options?: NodeOptions<State, Input>,
): Node<State> {
  if (typeof handler !== 'function') throw new GraphDefinitionError('node handler must be callable')

  const captured = captureOptions(options, ['name', 'retry', 'timeoutMs', 'recover'], 'Node')
  const name = captured.name === undefined ? inferHandlerName(handler) : requireControlString(captured.name, 'Node.name')
  const retry = captureRetry(captured.retry)
  const timeoutMs = captured.timeoutMs === undefined ? undefined : requirePositiveInteger(captured.timeoutMs, 'Node.timeoutMs')
  const recover = requireOptionalCallback<NodeRecoveryHandler<State, Input>>(captured.recover, 'Node.recover')

  const occurrence = new Node<State>(nodeConstructionToken)
  graphNames.set(occurrence, name)
  nodeHandlers.set(occurrence, handler as NodeHandler<object, unknown>)
  nodeRecoveries.set(occurrence, recover as NodeRecoveryHandler<object, unknown> | undefined)
  nodeRetries.set(occurrence, retry)
  nodeTimeouts.set(occurrence, timeoutMs)
  return occurrence
}

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

type CallbackCompletion = {
  readonly result: unknown
  readonly error: unknown
  readonly failed: boolean
  readonly settledMs: number
}

type EventSpec = {
  readonly kind: RunEvent['kind']
  readonly payload: unknown
}

class EventPublisher {
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

type ActivationCompletion = {
  readonly sequence: number
  readonly activation: Activation
  readonly failed: boolean
  readonly error: unknown
}

type FailurePacket = {
  readonly primary: Failure
  readonly suppressed: readonly Failure[]
  readonly input: unknown
}

function isRecoverableFailure(failure: Failure): boolean {
  return (
    failure.kind === 'handler' ||
    failure.kind === 'handler_timeout' ||
    failure.kind === 'node_recovery' ||
    failure.kind === 'flow_combine' ||
    failure.kind === 'flow_recovery'
  )
}

function replacePacket(packet: FailurePacket, failure: Failure): FailurePacket {
  return { primary: failure, suppressed: packet.suppressed, input: packet.input }
}

class SemanticMisuse extends TypeError {
  constructor(
    readonly reason: InvalidOutcomeReason,
    message: string,
  ) {
    super(message)
  }
}

class ProducedFailure extends Error {
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

function isFailureFence(value: unknown): value is FailureFence {
  return typeof value === 'object' && value !== null && (value as { readonly type?: unknown }).type === 'failure_fence'
}

class RunFailure extends Error {
  constructor(readonly packet: FailurePacket) {
    super(packet.primary.message)
  }
}

class RuntimeScopeFailure extends Error {
  constructor(readonly packet: FailurePacket) {
    super(packet.primary.message)
  }
}

class RunCancelled extends Error {
  readonly suppressed: readonly Failure[]

  constructor(suppressed: readonly Failure[] = []) {
    super('Caskada run cancelled')
    this.suppressed = Object.freeze(suppressed.slice())
  }
}

class RunAbandoned extends Error {
  readonly suppressed: readonly Failure[]

  constructor(
    readonly cause: Failure | CancellationInfo,
    suppressed: readonly Failure[] = [],
  ) {
    super('Caskada run abandoned')
    this.suppressed = Object.freeze(suppressed.slice())
  }
}

class RuntimeDeadline {
  constructor(
    readonly originMs: number,
    readonly durationMs: number,
  ) {}

  due(nowMs = performance.now()): boolean {
    return nowMs - this.originMs >= this.durationMs
  }

  remainingMs(nowMs = performance.now()): number {
    return Math.max(0, Math.ceil(this.durationMs - (nowMs - this.originMs)))
  }
}

class RuntimeCancellation implements Cancellation {
  private readonly controller = new AbortController()
  private readonly parent: RuntimeCancellation | undefined
  private readonly parentListener: (() => void) | undefined
  private runtimeDeadline = false
  private runtimeFencedAtMs: number | undefined

  constructor(parent?: RuntimeCancellation) {
    this.parent = parent
    if (parent === undefined) return
    const propagate = (): void => {
      this.cancel(parent.reason, parent.deadline, parent.fencedAtMs)
    }
    this.parentListener = propagate
    if (parent.cancelled) propagate()
    else parent.signal.addEventListener('abort', propagate, { once: true })
  }

  get cancelled(): boolean {
    return this.controller.signal.aborted
  }

  get reason(): unknown {
    return this.controller.signal.reason
  }

  get signal(): AbortSignal {
    return this.controller.signal
  }

  get deadline(): boolean {
    return this.runtimeDeadline
  }

  get fencedAtMs(): number | undefined {
    return this.runtimeFencedAtMs
  }

  throwIfCancelled(): void {
    if (this.cancelled) throw this.reason
  }

  cancel(reason: unknown, deadline = false, fencedAtMs = performance.now()): boolean {
    if (this.cancelled) return false
    this.runtimeDeadline = deadline
    this.runtimeFencedAtMs = fencedAtMs
    this.controller.abort(reason)
    return true
  }

  close(): void {
    if (this.parent !== undefined && this.parentListener !== undefined) {
      this.parent.signal.removeEventListener('abort', this.parentListener)
    }
  }
}

type CallbackGateWaiter = {
  readonly cancellation: RuntimeCancellation
  readonly resolve: () => void
  readonly reject: (reason: unknown) => void
  readonly abort: () => void
  readonly scopeId: number | undefined
  settled: boolean
}

class CallbackGate {
  private active = 0
  private readonly high: CallbackGateWaiter[] = []
  private readonly lowByScope = new Map<number, CallbackGateWaiter[]>()
  private readonly lowScopes: number[] = []
  private readonly lowMembers = new Set<number>()

  constructor(
    private readonly limit: number,
    private readonly runCancellation: RuntimeCancellation,
  ) {}

  acquire(readyCallback: boolean, cancellation: RuntimeCancellation, scopeId?: number): Promise<void> {
    this.discardSettled()
    if (!readyCallback && scopeId === undefined) throw new Error('new callback waiter has no scope')
    if (this.active < this.limit && this.high.length === 0 && (readyCallback || this.lowScopes.length === 0)) {
      this.active += 1
      return Promise.resolve()
    }
    return new Promise<void>((resolve, reject) => {
      let waiter!: CallbackGateWaiter
      const abort = (): void => {
        if (waiter.settled) return
        waiter.settled = true
        reject(cancellation.reason)
      }
      waiter = { cancellation, resolve, reject, abort, scopeId, settled: false }
      if (readyCallback) this.high.push(waiter)
      else {
        const resolvedScopeId = scopeId!
        const queue = this.lowByScope.get(resolvedScopeId) ?? []
        queue.push(waiter)
        this.lowByScope.set(resolvedScopeId, queue)
        if (!this.lowMembers.has(resolvedScopeId)) {
          this.lowMembers.add(resolvedScopeId)
          this.lowScopes.push(resolvedScopeId)
        }
      }
      cancellation.signal.addEventListener('abort', abort, { once: true })
      if (this.runCancellation !== cancellation) {
        this.runCancellation.signal.addEventListener('abort', abort, { once: true })
      }
      if (cancellation.cancelled || this.runCancellation.cancelled) abort()
    })
  }

  release(): void {
    if (this.active <= 0) throw new Error('callback permit released without ownership')
    this.active -= 1
    this.admitWaiters()
  }

  private admitWaiters(): void {
    this.discardSettled()
    while (this.active < this.limit) {
      let waiter: CallbackGateWaiter | undefined
      if (this.high.length > 0) waiter = this.high.shift()
      else {
        const scopeId = this.lowScopes.shift()
        if (scopeId !== undefined) {
          this.lowMembers.delete(scopeId)
          const queue = this.lowByScope.get(scopeId)!
          waiter = queue.shift()
          if (queue.length > 0) {
            this.lowMembers.add(scopeId)
            this.lowScopes.push(scopeId)
          } else this.lowByScope.delete(scopeId)
        }
      }
      if (waiter === undefined) return
      if (waiter.settled) continue
      waiter.settled = true
      waiter.cancellation.signal.removeEventListener('abort', waiter.abort)
      this.runCancellation.signal.removeEventListener('abort', waiter.abort)
      this.active += 1
      waiter.resolve()
    }
  }

  private discardSettled(): void {
    while (this.high[0]?.settled) this.high.shift()
    for (const scopeId of [...this.lowScopes]) {
      const queue = this.lowByScope.get(scopeId)!
      while (queue[0]?.settled) queue.shift()
      if (queue.length > 0) continue
      this.lowByScope.delete(scopeId)
      this.lowMembers.delete(scopeId)
    }
    if (this.lowMembers.size !== this.lowScopes.length) {
      const live = this.lowScopes.filter((scopeId) => this.lowMembers.has(scopeId))
      this.lowScopes.length = 0
      this.lowScopes.push(...live)
    }
  }
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
  private nextActivationId = 2
  private nextScopeId = 2
  private nextTerminalSequence = 1
  private nextFailureId = 1
  private activations = 1
  private attempts = 0
  private transitions = 0
  private retries = 0
  private reports = 0
  private scopesCreated = 0
  private readyCount = 0
  private peakReady = 0
  private peakCallbacks = 0
  private activeCallbacks = 0
  private readonly effectiveMaxConcurrency: number
  private readonly callbackGate: CallbackGate
  private terminalMs: number | undefined
  private failureFence: ProducedFailure | undefined
  private readonly recordedFailures = new Set<number>()
  private readonly scopeFencesPublished = new Set<number>()
  private readonly attemptFencesPublished = new Set<string>()
  private runFencePublished = false
  private cancellationFencePublished = false
  private readonly runtimeScopes = new Map<number, RuntimeScope>()

  constructor(
    private readonly snapshot: CompiledSnapshot,
    private readonly state: State,
    private readonly startedMs: number,
    private readonly cancellation: RuntimeCancellation,
    private readonly runId: string,
    private readonly options: ResolvedRunOptions,
    private readonly runDeadline: RuntimeDeadline | undefined,
    private readonly publisher: EventPublisher,
  ) {
    for (const placement of snapshot.placements) this.placements.set(placement.elementId, placement)
    for (const scope of snapshot.scopes) this.scopes.set(scope.scopeDefinitionId, scope)
    this.effectiveMaxConcurrency = options.maxConcurrency ?? snapshot.autoMaxConcurrency
    this.callbackGate = new CallbackGate(this.effectiveMaxConcurrency, cancellation)
  }

  private scopeStartedSpec(scope: RuntimeScope): EventSpec {
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

  private scopeFinishedSpec(scope: RuntimeScope, status: 'completed' | 'failed' | 'cancelled' | 'abandoned'): EventSpec {
    return {
      kind: 'scope_finished',
      payload: Object.freeze({
        scopeId: scope.scopeId,
        status,
        terminalSequences: scope.finishedTerminalSequences ?? Object.freeze(scope.terminals.map((terminal) => terminal.sequence)),
      }),
    }
  }

  private markScopeFinished(scope: RuntimeScope, status: 'completed' | 'failed' | 'cancelled' | 'abandoned'): EventSpec | undefined {
    if (scope.finished) return undefined
    scope.finished = true
    return this.scopeFinishedSpec(scope, status)
  }

  private captureScopeFinishTerminals(scope: RuntimeScope): void {
    scope.finishedTerminalSequences ??= Object.freeze(scope.terminals.map((terminal) => terminal.sequence))
  }

  private publishTerminal(status: 'completed' | 'failed' | 'cancelled' | 'abandoned'): void {
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

  private publishCallbackStarted(
    scope: RuntimeScope,
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

  private failureRecordSpec(failure: Failure): EventSpec | undefined {
    if (this.recordedFailures.has(failure.failureId)) return undefined
    this.recordedFailures.add(failure.failureId)
    return { kind: 'failure_recorded', payload: Object.freeze({ failure }) }
  }

  private publishCallbackFinished(
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

  private publishFailureRecorded(failure: Failure): void {
    const spec = this.failureRecordSpec(failure)
    if (spec !== undefined) this.publisher.publishBundle([spec])
  }

  private publishScopeFailureFence(scope: RuntimeScope, failure: Failure): void {
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

  private publishRunFailureFence(failure: Failure): void {
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

  private publishRunCancellationIfNeeded(): void {
    if (!this.cancellation.cancelled || this.cancellationFencePublished) return
    this.cancellationFencePublished = true
    this.publisher.publishRunCancellation(this.cancellation.reason, this.cancellation.deadline)
  }

  private publishAttemptTimeout(context: RuntimeContext<State>, failure: Failure): void {
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

  async run(settle: (outcome: SerialOutcome) => void): Promise<void> {
    const rootDefinition = this.requireScope(1)
    const rootPlacement = this.requirePlacement(1)
    const root = this.newScope(rootDefinition, 1, null, undefined, null, rootPlacement)
    try {
      this.checkpoint()
      let terminals: NonEmptyTerminals | undefined
      await this.runScopes(root, (completedTerminals) => {
        terminals = completedTerminals
      })
      this.checkpoint()
      if (terminals === undefined) throw new Error('scheduler completed without root terminals')
      const stats = this.stats()
      this.publishTerminal('completed')
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
        const stats = this.stats()
        this.publishTerminal('abandoned')
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
        this.publishRunCancellationIfNeeded()
        const stats = this.stats()
        this.publishTerminal('cancelled')
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
        this.publishRunFailureFence(error.packet.primary)
        const stats = this.stats()
        this.publishTerminal('failed')
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
          : this.newFailure('internal', 1, null, null, null, null, {
              type: 'internal',
              reason: 'scheduler_invariant',
            })
      this.publishRunFailureFence(failure)
      const stats = this.stats()
      this.publishTerminal('failed')
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

  private checkpoint(suppressed: readonly Failure[] = Object.freeze([])): void {
    this.checkCancelled(suppressed)
  }

  private commitDeadlineIfDue(): void {
    if (!this.cancellation.cancelled && this.runDeadline?.due()) {
      this.cancellation.cancel('deadline_exceeded', true)
    }
  }

  private checkCancelled(suppressed: readonly Failure[] = Object.freeze([])): void {
    if (this.failureFence !== undefined) throw this.failureFence
    this.commitDeadlineIfDue()
    if (this.cancellation.cancelled) {
      this.publishRunCancellationIfNeeded()
      throw new RunCancelled(Object.freeze(suppressed.slice()))
    }
  }

  private checkScopeCancelled(scope: RuntimeScope, suppressed: readonly Failure[] = Object.freeze([])): void {
    this.checkCancelled(suppressed)
    if (!scope.cancellation.cancelled) return
    const reason = scope.cancellation.reason
    if (isFailureFence(reason)) throw reason.produced
    throw new RunCancelled(suppressed)
  }

  private async acquireCallback(scope: RuntimeScope, readyCallback: boolean): Promise<void> {
    this.checkScopeCancelled(scope)
    try {
      await this.callbackGate.acquire(readyCallback, scope.cancellation, scope.scopeId)
    } catch {
      this.checkScopeCancelled(scope)
      throw new Error('callback permit acquisition lost its cancellation reason')
    }
    this.activeCallbacks += 1
    this.peakCallbacks = Math.max(this.peakCallbacks, this.activeCallbacks)
  }

  private async acquireCallbackSource(cancellation: RuntimeCancellation, readyCallback: boolean): Promise<void> {
    this.checkCancelled()
    try {
      await this.callbackGate.acquire(readyCallback, cancellation)
    } catch {
      this.checkCancelled()
      if (isFailureFence(cancellation.reason)) throw cancellation.reason.produced
      throw new RunCancelled()
    }
    this.activeCallbacks += 1
    this.peakCallbacks = Math.max(this.peakCallbacks, this.activeCallbacks)
  }

  private releaseCallback(): void {
    if (this.activeCallbacks <= 0) throw new Error('callback accounting lost its owner')
    this.activeCallbacks -= 1
    this.callbackGate.release()
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
      this.checkScopeCancelled(scope)
      while (scope.queueIndex < scope.queue.length && active.size < scope.definition.concurrency) {
        const activation = scope.queue[scope.queueIndex]!
        scope.queueIndex += 1
        this.readyCount -= 1
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
      this.publishScopeFailureFence(scope, failure.packet.primary)
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
        this.captureScopeFinishTerminals(scope)
        scope.terminals = recovered.slice()
        scope.cancellation.close()
        return
      }
      scope.cancellation.close()
      if (scope.parent === null) throw new RunFailure(packet)
      const finish = this.markScopeFinished(scope, 'failed')
      if (finish !== undefined) this.publisher.publishBundle([finish])
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
          this.captureScopeFinishTerminals(scope)
          scope.terminals = recovered.slice()
        }
        if (intents.length > 0) {
          this.captureScopeFinishTerminals(scope)
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
      this.checkCancelled()
      const scope = stack[stack.length - 1]!
      if (scope.queueIndex < scope.queue.length) {
        const activation = scope.queue[scope.queueIndex]!
        scope.queueIndex += 1
        this.readyCount -= 1
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
            this.captureScopeFinishTerminals(scope)
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
      this.checkCancelled([currentPacket.primary, ...currentPacket.suppressed])
      const settledBeforeFence = Object.freeze(currentScope.terminals.slice())
      currentScope.cancellation.cancel(
        Object.freeze({
          type: 'failure_fence' as const,
          produced: new ProducedFailure(currentPacket.primary, currentPacket.suppressed),
        }),
      )
      this.publishScopeFailureFence(currentScope, currentPacket.primary)
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
        this.captureScopeFinishTerminals(currentScope)
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
      const finish = this.markScopeFinished(completed, 'failed')
      if (finish !== undefined) this.publisher.publishBundle([finish])
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
      this.checkCancelled([packet.primary, ...packet.suppressed])
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
    this.checkCancelled([packet.primary, ...packet.suppressed])
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
      () => this.remainingMs(callbackSource, undefined),
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
        return this.newFailure(
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
      return this.newFailure(
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
    this.publishCallbackStarted(
      scope,
      scope.ownerActivationId,
      scope.ownerParentActivationId,
      scope.ownerPlacement.elementId,
      'flow_recover',
      null,
    )
    try {
      try {
        callbackResult = await this.awaitLifecycleCallback(context, callbackSource, () => callback(context, failureView), classify, {
          active: [packet.primary, ...packet.suppressed],
        })
      } catch (error) {
        if (!(error instanceof ProducedFailure)) {
          if (error instanceof RunCancelled || error instanceof RunAbandoned) {
            this.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_recover', null, {
              kind: 'discarded',
            })
          }
          throw error
        }
        this.publishCallbackFinished(
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

    this.checkCancelled([packet.primary, ...packet.suppressed])
    if (callbackResult !== undefined) {
      const failure = this.newFailure(
        'invalid_combination',
        scope.scopeId,
        scope.ownerActivationId,
        scope.ownerPlacement.elementId,
        null,
        null,
        { type: 'invalid_combination', reason: 'wrong_return_type' },
        packet.primary,
      )
      this.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_recover', null, { kind: 'failure', failure }, [
        failure,
      ])
      throw new RunFailure(replacePacket(packet, failure))
    }
    if (intents.length === 0) {
      this.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_recover', null, {
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
    this.readyCount -= discarded
  }

  private scopeResult(scope: RuntimeScope): ScopeResult {
    const terminals = Object.freeze(scope.terminals.slice()) as NonEmptyTerminals
    const outputs = Object.freeze(scope.terminals.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.output))
    return Object.freeze({ terminals, outputs })
  }

  private remainingMs(callbackSource: RuntimeCancellation, attemptDeadline: RuntimeDeadline | undefined): number | undefined {
    const nowMs = performance.now()
    const remaining: number[] = []
    if (!this.cancellation.cancelled && this.runDeadline !== undefined) {
      remaining.push(this.runDeadline.remainingMs(nowMs))
    }
    if (!callbackSource.cancelled && attemptDeadline !== undefined) {
      remaining.push(attemptDeadline.remainingMs(nowMs))
    }
    for (const source of [callbackSource, this.cancellation]) {
      if (source.cancelled && source.fencedAtMs !== undefined) {
        remaining.push(new RuntimeDeadline(source.fencedAtMs, this.options.cancelGraceMs).remainingMs(nowMs))
      }
    }
    return remaining.length === 0 ? undefined : Math.min(...remaining)
  }

  private async captureCallback(callback: () => unknown): Promise<CallbackCompletion> {
    let result: unknown
    let error: unknown
    let failed = false
    try {
      result = await callback()
    } catch (caught) {
      error = caught
      failed = true
    }
    const completion = Object.create(null) as {
      result: unknown
      error: unknown
      failed: boolean
      settledMs: number
    }
    completion.result = result
    completion.error = error
    completion.failed = failed
    completion.settledMs = performance.now()
    return Object.freeze(completion)
  }

  private async awaitLifecycleCallback(
    context: RuntimeContext<State>,
    callbackSource: RuntimeCancellation,
    callback: () => unknown,
    classify: (error: unknown, selected: Failure | null) => Failure,
    options: {
      readonly active?: readonly Failure[]
      readonly attemptDeadline?: RuntimeDeadline
      readonly timeoutFailure?: () => Failure
    } = {},
  ): Promise<unknown> {
    const active = options.active ?? Object.freeze([])
    const failureFence = (): ProducedFailure | undefined => {
      const reason = callbackSource.reason
      return isFailureFence(reason) ? reason.produced : undefined
    }
    const fencedProduced = (fence: ProducedFailure, completion: CallbackCompletion): ProducedFailure => {
      const suppressed = [...fence.suppressed]
      if (completion.failed && !isCooperativeCancellation(completion.error, callbackSource)) {
        suppressed.push(classify(completion.error, fence.failure))
      }
      return new ProducedFailure(fence.failure, suppressed)
    }
    this.checkCancelled(active)
    if (options.attemptDeadline?.due()) {
      if (options.timeoutFailure === undefined) throw new Error('attempt timeout has no Failure factory')
      const failure = options.timeoutFailure()
      callbackSource.cancel('attempt_timeout')
      this.publishAttemptTimeout(context, failure)
      callbackSource.close()
      context.close()
      throw new ProducedFailure(failure)
    }

    let completion: CallbackCompletion | undefined
    const callbackPromise = this.captureCallback(callback).then((settled) => {
      completion = settled
      return settled
    })
    let sourceListener: (() => void) | undefined
    const sourceWake = new Promise<void>((resolve) => {
      if (callbackSource.cancelled) resolve()
      else {
        sourceListener = resolve
        callbackSource.signal.addEventListener('abort', sourceListener, { once: true })
      }
    })
    const attemptStop = new AbortController()
    const stopAttempt = (): void => attemptStop.abort()
    callbackSource.signal.addEventListener('abort', stopAttempt, { once: true })
    const attemptWake =
      options.attemptDeadline === undefined
        ? undefined
        : waitRuntimeDeadline(options.attemptDeadline, attemptStop.signal).then((elapsed) => {
            if (elapsed && completion === undefined) callbackSource.cancel('attempt_timeout')
          })
    try {
      await Promise.race(attemptWake === undefined ? [callbackPromise, sourceWake] : [callbackPromise, sourceWake, attemptWake])

      if (completion !== undefined) {
        const attemptWon =
          options.attemptDeadline !== undefined &&
          completion.settledMs - options.attemptDeadline.originMs >= options.attemptDeadline.durationMs &&
          !this.cancellation.cancelled
        if (attemptWon) callbackSource.cancel('attempt_timeout')
        else if (!this.cancellation.cancelled) {
          const fence = failureFence()
          if (fence !== undefined) throw fencedProduced(fence, completion)
          if (completion.failed) {
            throw new ProducedFailure(classify(completion.error, null), active.length > 0 ? active.slice(1) : [])
          }
          return completion.result
        }
      }

      const localTimeout = callbackSource.cancelled && callbackSource.reason === 'attempt_timeout'
      const timeoutPrimary = localTimeout && options.timeoutFailure !== undefined ? options.timeoutFailure() : undefined
      if (timeoutPrimary !== undefined) this.publishAttemptTimeout(context, timeoutPrimary)

      while (completion === undefined) {
        const graceDeadlines: RuntimeDeadline[] = []
        if (callbackSource.cancelled && callbackSource.fencedAtMs !== undefined) {
          graceDeadlines.push(new RuntimeDeadline(callbackSource.fencedAtMs, this.options.cancelGraceMs))
        }
        if (this.cancellation.cancelled && this.cancellation.fencedAtMs !== undefined) {
          graceDeadlines.push(new RuntimeDeadline(this.cancellation.fencedAtMs, this.options.cancelGraceMs))
        }
        if (graceDeadlines.length === 0) throw new Error('signalled callback has no grace deadline')
        let earliest = graceDeadlines[0]!
        for (const candidate of graceDeadlines.slice(1)) {
          if (candidate.remainingMs() < earliest.remainingMs()) earliest = candidate
        }
        const graceCancellation = new AbortController()
        const graceWake = waitRuntimeDeadline(earliest, graceCancellation.signal)
        const runWake = this.cancellation.cancelled
          ? undefined
          : new Promise<void>((resolve) => {
              this.cancellation.signal.addEventListener('abort', () => resolve(), { once: true })
            })
        await Promise.race(runWake === undefined ? [callbackPromise, graceWake] : [callbackPromise, graceWake, runWake])
        graceCancellation.abort()
        if (completion !== undefined) break
        if (earliest.due()) {
          context.abandon()
          void callbackPromise.then(
            () => undefined,
            () => undefined,
          )
          if (this.failureFence !== undefined) throw new RunAbandoned(this.failureFence.failure, this.failureFence.suppressed)
          if (this.cancellation.cancelled) {
            const cancellation = Object.freeze({
              reason: this.cancellation.reason,
              deadline: this.cancellation.deadline,
            })
            const suppressed = timeoutPrimary === undefined ? active : [timeoutPrimary, ...active.slice(1)]
            throw new RunAbandoned(cancellation, suppressed)
          }
          const fence = failureFence()
          if (fence !== undefined) throw new RunAbandoned(fence.failure, fence.suppressed)
          if (timeoutPrimary === undefined) throw new Error('local grace expired without timeout')
          throw new RunAbandoned(timeoutPrimary, active.slice(1))
        }
      }

      if (completion === undefined) throw new Error('callback wakeup lost its settlement')
      const protectedSources = [callbackSource, this.cancellation].filter(
        (source) => source.cancelled && source.fencedAtMs !== undefined,
      )
      const graceExpired = protectedSources.some((source) => completion!.settledMs - source.fencedAtMs! >= this.options.cancelGraceMs)
      if (graceExpired) {
        context.abandon()
        if (this.failureFence !== undefined) throw new RunAbandoned(this.failureFence.failure, this.failureFence.suppressed)
        if (this.cancellation.cancelled) {
          const cancellation = Object.freeze({
            reason: this.cancellation.reason,
            deadline: this.cancellation.deadline,
          })
          const suppressed = timeoutPrimary === undefined ? active : [timeoutPrimary, ...active.slice(1)]
          throw new RunAbandoned(cancellation, suppressed)
        }
        const fence = failureFence()
        if (fence !== undefined) throw new RunAbandoned(fence.failure, fence.suppressed)
        if (timeoutPrimary === undefined) throw new Error('expired grace has no controlling timeout')
        throw new RunAbandoned(timeoutPrimary, active.slice(1))
      }
      if (this.failureFence !== undefined) throw fencedProduced(this.failureFence, completion)
      if (this.cancellation.cancelled) {
        const suppressed = [...(timeoutPrimary === undefined ? active : [timeoutPrimary, ...active.slice(1)])]
        if (completion.failed && !isCooperativeCancellation(completion.error, callbackSource)) {
          suppressed.push(classify(completion.error, timeoutPrimary ?? active[0] ?? null))
        }
        throw new RunCancelled(suppressed)
      }
      const fence = failureFence()
      if (fence !== undefined) throw fencedProduced(fence, completion)
      if (timeoutPrimary === undefined) throw new Error('attempt signal has no timeout Failure')
      const suppressed = [...active.slice(1)]
      if (completion.failed && !isCooperativeCancellation(completion.error, callbackSource)) {
        suppressed.push(classify(completion.error, timeoutPrimary))
      }
      throw new ProducedFailure(timeoutPrimary, suppressed)
    } finally {
      attemptStop.abort()
      if (sourceListener !== undefined) callbackSource.signal.removeEventListener('abort', sourceListener)
      callbackSource.signal.removeEventListener('abort', stopAttempt)
      callbackSource.close()
    }
  }

  private stats(): RunStats {
    this.terminalMs ??= performance.now()
    const durationMs = Math.min(MAX_SAFE_INTEGER, Math.max(0, Math.floor(this.terminalMs - this.startedMs)))
    return Object.freeze({
      activations: this.activations,
      attempts: this.attempts,
      transitions: this.transitions,
      retries: this.retries,
      reports: this.reports,
      scopes: this.scopesCreated,
      peakReady: this.peakReady,
      peakCallbacks: this.peakCallbacks,
      durationMs,
    })
  }

  private newFailure(
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
    failure.failureId = this.nextFailureId
    failure.kind = kind
    failure.message = failureMessages[kind]
    failure.cause = cause
    failure.scopeId = scopeId
    failure.activationId = activationId
    failure.elementId = elementId
    failure.attempt = attempt
    failure.detail = detail === null ? null : Object.freeze(detail)
    failure.previous = previous
    this.nextFailureId += 1
    return Object.freeze(failure)
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
      if (this.transitions + bufferedCount > this.options.maxTransitions) limit = 'max_transitions'
      else if (bufferedCount > MAX_PORTABLE_COLLECTION_LENGTH) limit = 'portable_collection'
      if (limit === null) return
      const produced = new ProducedFailure(
        this.newFailure('limit', scopeId, activationId, elementId, attempt, null, { type: 'limit', limit }, previous),
        suppressed,
      )
      this.failureFence ??= produced
      const fence = Object.freeze({ type: 'failure_fence' as const, produced: this.failureFence })
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
      if (this.publisher.isPublishing) {
        this.publisher.rejectReentrantReport()
        return
      }
      this.commitDeadlineIfDue()
      if (this.failureFence !== undefined) {
        throw callbackSource.reason ?? this.cancellation.reason
      }
      if (this.cancellation.cancelled) {
        this.publishRunCancellationIfNeeded()
        throw callbackSource.reason ?? this.cancellation.reason
      }
      if (callbackSource.cancelled) {
        throw callbackSource.reason ?? this.cancellation.reason
      }
      if (attemptDeadline?.due()) {
        if (timeoutFailure === undefined) throw new Error('attempt report checkpoint has no timeout')
        const failure = timeoutFailure()
        callbackSource.cancel('attempt_timeout')
        this.publishAttemptTimeout(context, failure)
        throw callbackSource.reason
      }
      if (typeof name !== 'string' || name.length === 0) {
        throw new SemanticMisuse('report_name', 'report name must be a nonempty string')
      }
      if (this.reports >= this.options.maxReports) {
        const produced = new ProducedFailure(
          this.newFailure('limit', scopeId, activationId, elementId, attempt, null, { type: 'limit', limit: 'max_reports' }, previous),
          suppressed,
        )
        this.failureFence ??= produced
        this.publishRunFailureFence(this.failureFence.failure)
        callbackSource.cancel(Object.freeze({ type: 'failure_fence' as const, produced: this.failureFence }))
        throw callbackSource.reason
      }
      this.reports += 1
      this.publisher.publish('report', Object.freeze({ scopeId, activationId, name, hasData, data }))
      this.commitDeadlineIfDue()
      if (this.cancellation.cancelled) this.publishRunCancellationIfNeeded()
      if (!callbackSource.cancelled && attemptDeadline?.due()) {
        if (timeoutFailure === undefined) throw new Error('attempt report checkpoint has no timeout')
        const failure = timeoutFailure()
        callbackSource.cancel('attempt_timeout')
        this.publishAttemptTimeout(context, failure)
      }
      if (this.failureFence !== undefined || this.cancellation.cancelled || callbackSource.cancelled) {
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
      else if (this.activations + 1 > this.options.maxActivations) limit = 'max_activations'
      else if (this.readyCount + 1 > this.options.maxReady) limit = 'max_ready'
      else if (this.nextScopeId > MAX_SAFE_INTEGER || this.nextActivationId > MAX_SAFE_INTEGER) limit = 'safe_integer'
      if (limit !== null) {
        throw new ProducedFailure(
          this.newFailure('limit', parent.scopeId, ownerActivationId, ownerPlacement.elementId, null, null, { type: 'limit', limit }),
        )
      }
      scopeId = this.nextScopeId
      this.nextScopeId += 1
      depth = parent.depth + 1
    }
    const entry: Activation = {
      elementId: definition.entryElementId,
      input: incomingInput,
      activationId: this.allocateActivationId(),
      parentActivationId: ownerActivationId,
    }
    this.scopesCreated += 1
    this.readyCount += 1
    this.peakReady = Math.max(this.peakReady, this.readyCount)
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
      this.publisher.publishBundle([this.scopeStartedSpec(runtimeScope)])
      this.checkScopeCancelled(parent)
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
      this.checkScopeCancelled(scope, activePacket)
      await this.acquireCallback(scope, attempt > 1)
      let permitHeld = true
      try {
        if (this.attempts >= this.options.maxAttempts) {
          throw new ProducedFailure(
            this.newFailure(
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
        this.attempts += 1
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
          this.checkScopeCancelled(scope, activePacket)
          const shouldRetry =
            attempt < placement.retry.maxAttempts && this.shouldRetry(scope, placement, activation, attempt, failure, packetSuppressed)
          if (shouldRetry) {
            if (this.attempts >= this.options.maxAttempts) {
              throw new ProducedFailure(
                this.newFailure(
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
            const delayMs = this.retryDelay(scope, placement, activation, attempt, failure, packetSuppressed)
            this.retries += 1
            this.publisher.publish(
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
            this.checkScopeCancelled(scope, activePacket)
            this.releaseCallback()
            permitHeld = false
            if (!(await waitRetryDelay(delayMs, scope.cancellation))) this.checkScopeCancelled(scope, activePacket)
            attempt += 1
            continue
          }
          this.releaseCallback()
          permitHeld = false
          this.checkScopeCancelled(scope, activePacket)
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

  private shouldRetry(
    scope: RuntimeScope,
    placement: CompiledNodePlacement,
    activation: Activation,
    attempt: number,
    failure: Failure,
    inheritedSuppressed: readonly Failure[],
  ): boolean {
    let result: unknown
    try {
      result = placement.retry.shouldRetry(failure)
    } catch (cause) {
      const replacement = this.newFailure(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        cause,
        null,
        failure,
      )
      this.commitDeadlineIfDue()
      if (this.cancellation.cancelled) throw new RunCancelled([failure, ...inheritedSuppressed, replacement])
      this.publishFailureRecorded(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    this.checkCancelled([failure, ...inheritedSuppressed])
    this.rejectAsynchronousPolicyResult(scope, placement, activation, attempt, failure, inheritedSuppressed, result)
    if (typeof result !== 'boolean') {
      const replacement = this.newFailure(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        null,
        null,
        failure,
      )
      this.publishFailureRecorded(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    return result
  }

  private retryDelay(
    scope: RuntimeScope,
    placement: CompiledNodePlacement,
    activation: Activation,
    attempt: number,
    failure: Failure,
    inheritedSuppressed: readonly Failure[],
  ): number {
    if (typeof placement.retry.delayMs === 'number') return placement.retry.delayMs
    let result: unknown
    try {
      result = placement.retry.delayMs(attempt, failure)
    } catch (cause) {
      const replacement = this.newFailure(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        cause,
        null,
        failure,
      )
      this.commitDeadlineIfDue()
      if (this.cancellation.cancelled) throw new RunCancelled([failure, ...inheritedSuppressed, replacement])
      this.publishFailureRecorded(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    this.checkCancelled([failure, ...inheritedSuppressed])
    this.rejectAsynchronousPolicyResult(scope, placement, activation, attempt, failure, inheritedSuppressed, result)
    if (typeof result !== 'number' || !Number.isSafeInteger(result) || result < 0) {
      const replacement = this.newFailure(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        null,
        null,
        failure,
      )
      this.publishFailureRecorded(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    return Object.is(result, -0) ? 0 : result
  }

  private rejectAsynchronousPolicyResult(
    scope: RuntimeScope,
    placement: CompiledNodePlacement,
    activation: Activation,
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
      const replacement = this.newFailure(
        'retry_policy',
        scope.scopeId,
        activation.activationId,
        placement.elementId,
        attempt,
        cause,
        null,
        failure,
      )
      this.commitDeadlineIfDue()
      if (this.cancellation.cancelled) throw new RunCancelled([failure, ...inheritedSuppressed, replacement])
      this.publishFailureRecorded(replacement)
      throw new ProducedFailure(replacement, inheritedSuppressed)
    }
    this.checkCancelled([failure, ...inheritedSuppressed])
    if (typeof then !== 'function') return
    disposeNativePromise(result)
    const replacement = this.newFailure(
      'retry_policy',
      scope.scopeId,
      activation.activationId,
      placement.elementId,
      attempt,
      null,
      null,
      failure,
    )
    this.publishFailureRecorded(replacement)
    throw new ProducedFailure(replacement, inheritedSuppressed)
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
      timeoutFailureValue ??= this.newFailure(
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
      () => this.remainingMs(callbackSource, attemptDeadline),
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
        return this.newFailure(
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
      return this.newFailure('handler', scope.scopeId, activation.activationId, placement.elementId, attempt, error, null, causal)
    }
    let result: unknown
    let intents: readonly Intent[]
    this.publishCallbackStarted(scope, activation.activationId, activation.parentActivationId, placement.elementId, 'handle', attempt)
    try {
      try {
        result = await this.awaitLifecycleCallback(context, callbackSource, () => handler(context), classify, {
          active: previous === null ? inheritedSuppressed : [previous, ...inheritedSuppressed],
          ...(attemptDeadline === undefined ? {} : { attemptDeadline }),
          timeoutFailure,
        })
      } finally {
        intents = context.close()
      }
      this.checkScopeCancelled(scope, previous === null ? inheritedSuppressed : [previous, ...inheritedSuppressed])
      if (result !== undefined) {
        throw new ProducedFailure(
          this.newFailure(
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
        this.publishCallbackFinished(
          scope.scopeId,
          activation.activationId,
          'handle',
          attempt,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
      } else if (error instanceof RunCancelled || error instanceof RunAbandoned) {
        this.publishCallbackFinished(scope.scopeId, activation.activationId, 'handle', attempt, { kind: 'discarded' })
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
      () => this.remainingMs(callbackSource, undefined),
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
        return this.newFailure(
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
      return this.newFailure('node_recovery', scope.scopeId, activation.activationId, placement.elementId, null, error, null, causal)
    }
    let result: unknown
    let intents: readonly Intent[]
    this.publishCallbackStarted(
      scope,
      activation.activationId,
      activation.parentActivationId,
      placement.elementId,
      'node_recover',
      null,
    )
    try {
      try {
        result = await this.awaitLifecycleCallback(context, callbackSource, () => callback(context, failure), classify, {
          active: [failure, ...inheritedSuppressed],
        })
      } finally {
        intents = context.close()
      }
      this.checkScopeCancelled(scope, [failure, ...inheritedSuppressed])
      if (result !== undefined) {
        throw new ProducedFailure(
          this.newFailure(
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
        this.publishCallbackFinished(
          scope.scopeId,
          activation.activationId,
          'node_recover',
          null,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
      } else if (error instanceof RunCancelled || error instanceof RunAbandoned) {
        this.publishCallbackFinished(scope.scopeId, activation.activationId, 'node_recover', null, { kind: 'discarded' })
      }
      throw error
    }
    if (intents.length === 0) {
      this.publishCallbackFinished(scope.scopeId, activation.activationId, 'node_recover', null, {
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
      () => this.remainingMs(callbackSource, undefined),
      this.makeIntentReserver(scope.scopeId, scope.ownerActivationId, scope.ownerPlacement.elementId, null, null, [], callbackSource),
      this.makeReporter(scope.scopeId, scope.ownerActivationId, scope.ownerPlacement.elementId, null, null, [], callbackSource),
    )
    const classify = (error: unknown, selected: Failure | null): Failure => {
      if (error instanceof SemanticMisuse) {
        return this.newFailure(
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
      return this.newFailure(
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
    this.publishCallbackStarted(
      scope,
      scope.ownerActivationId,
      scope.ownerParentActivationId,
      scope.ownerPlacement.elementId,
      'flow_combine',
      null,
    )
    try {
      try {
        result = await this.awaitLifecycleCallback(context, callbackSource, () => callback(context, resultView), classify)
      } finally {
        intents = context.close()
      }
      this.checkScopeCancelled(scope)
      if (result !== undefined) {
        throw new ProducedFailure(
          this.newFailure('invalid_combination', scope.scopeId, scope.ownerActivationId, scope.ownerPlacement.elementId, null, null, {
            type: 'invalid_combination',
            reason: 'wrong_return_type',
          }),
        )
      }
    } catch (error) {
      if (error instanceof ProducedFailure) {
        this.publishCallbackFinished(
          scope.scopeId,
          scope.ownerActivationId,
          'flow_combine',
          null,
          { kind: 'failure', failure: error.failure },
          [error.failure, ...error.suppressed],
        )
      } else if (error instanceof RunCancelled || error instanceof RunAbandoned) {
        this.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_combine', null, { kind: 'discarded' })
      }
      throw error
    }
    if (intents.length === 0) {
      this.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, 'flow_combine', null, {
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
      this.checkScopeCancelled(scope, previous === null ? [] : [previous])
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
            this.newFailure(
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
          this.publishCallbackFinished(
            scope.scopeId,
            sourceActivationId,
            callbackPhase,
            attempt,
            { kind: 'failure', failure: error.failure },
            [error.failure, ...error.suppressed],
          )
        } else this.publishFailureRecorded(error.failure)
      }
      throw error
    }

    if (callbackPhase !== undefined) {
      this.publishCallbackFinished(scope.scopeId, sourceActivationId, callbackPhase, attempt, {
        kind: 'outcome',
        outcome: this.intentOutcome(intents),
      })
      this.checkScopeCancelled(scope, previous === null ? [] : [previous])
    }
    this.transitions += intents.length
    scope.directActivations += targetCount
    const specs: EventSpec[] = []
    for (let index = 0; index < intents.length; index += 1) {
      const intent = intents[index]!
      const resolution = resolutions[index]!
      if (resolution.kind === 'target') {
        if (resolution.target === undefined) throw new Error('target resolution has no element')
        const activationId = this.allocateActivationId()
        scope.queue.push({
          elementId: resolution.target,
          input: intent.value,
          activationId,
          parentActivationId: sourceActivationId,
        })
        this.readyCount += 1
        this.peakReady = Math.max(this.peakReady, this.readyCount)
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
          sequence: this.allocateTerminalSequence(),
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
    this.publisher.publishBundle(specs)
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
      this.checkCancelled(previous === null ? [] : [previous])
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
            this.newFailure(
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
        this.publishCallbackFinished(
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
    this.publishCallbackFinished(scope.scopeId, scope.ownerActivationId, callbackPhase, null, {
      kind: 'outcome',
      outcome: this.intentOutcome(intents),
    })
    this.checkCancelled(previous === null ? [] : [previous])
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
          sequence: this.allocateTerminalSequence(),
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
    this.transitions += intents.length
    this.publisher.publishBundle(specs)
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
    if (this.transitions + transitionCount > this.options.maxTransitions) limit = 'max_transitions'
    else if (
      transitionCount > MAX_PORTABLE_COLLECTION_LENGTH ||
      queued + targetCount > MAX_PORTABLE_COLLECTION_LENGTH ||
      scope.terminals.length + terminalCount > MAX_PORTABLE_COLLECTION_LENGTH
    )
      limit = 'portable_collection'
    else if (this.activations + targetCount > this.options.maxActivations) limit = 'max_activations'
    else if (scope.definition.maxActivations !== undefined && scope.directActivations + targetCount > scope.definition.maxActivations)
      limit = 'scope_max_activations'
    else if (this.readyCount + targetCount > this.options.maxReady) limit = 'max_ready'
    else if (
      (targetCount > 0 && this.nextActivationId + targetCount - 1 > MAX_SAFE_INTEGER) ||
      (terminalCount > 0 && this.nextTerminalSequence + terminalCount - 1 > MAX_SAFE_INTEGER)
    )
      limit = 'safe_integer'
    if (limit === null) return
    throw new ProducedFailure(
      this.newFailure('limit', scope.scopeId, sourceActivationId, source.elementId, attempt, null, { type: 'limit', limit }, previous),
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
    const finish = this.scopeFinishedSpec(child, 'completed')
    this.route(child.parent, child.ownerPlacement, child.ownerActivationId, intents, null, null, [], undefined, true, [finish])
    child.finished = true
  }

  private endTerminal(intent: Intent, sourceActivationId: number): EndTerminal {
    const common = {
      type: 'end' as const,
      sequence: this.allocateTerminalSequence(),
      sourceActivationId,
    }
    return intent.present
      ? Object.freeze({ ...common, hasOutput: true as const, output: intent.value })
      : Object.freeze({ ...common, hasOutput: false as const, output: undefined })
  }

  private allocateActivationId(): number {
    const value = this.nextActivationId
    this.nextActivationId += 1
    this.activations += 1
    return value
  }

  private allocateTerminalSequence(): number {
    const value = this.nextTerminalSequence
    this.nextTerminalSequence += 1
    return value
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

function startRuntime<State extends object>(snapshot: CompiledSnapshot, state: State, options: ResolvedRunOptions): RunHandle<State> {
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

function projectState<State extends object>(handle: RunHandle<State>): Promise<State> {
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

function captureRunOptions(value: unknown): ResolvedRunOptions {
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

async function waitRetryDelay(delayMs: number, cancellation: RuntimeCancellation): Promise<boolean> {
  let remaining = delayMs
  if (remaining === 0) return await waitTimerChunk(0, cancellation)
  while (remaining > 0) {
    const chunk = Math.min(remaining, MAX_HOST_TIMER_DELAY_MS)
    if (!(await waitTimerChunk(chunk, cancellation))) return false
    remaining -= chunk
  }
  return true
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

async function waitRuntimeDeadline(deadline: RuntimeDeadline, signal: AbortSignal): Promise<boolean> {
  while (!signal.aborted) {
    const remaining = deadline.remainingMs()
    if (remaining === 0) return true
    if (!(await waitSignalTimerChunk(Math.min(remaining, MAX_HOST_TIMER_DELAY_MS), signal))) return false
  }
  return false
}

function isCooperativeCancellation(error: unknown, cancellation: RuntimeCancellation): boolean {
  if (!cancellation.cancelled) return false
  if (error === cancellation.reason) return true
  try {
    return typeof DOMException !== 'undefined' && error instanceof DOMException && error.name === 'AbortError'
  } catch {
    return false
  }
}

function waitTimerChunk(delayMs: number, cancellation: RuntimeCancellation): Promise<boolean> {
  return waitSignalTimerChunk(delayMs, cancellation.signal)
}

function waitSignalTimerChunk(delayMs: number, signal: AbortSignal): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    if (signal.aborted) {
      resolve(false)
      return
    }
    let settled = false
    const finish = (elapsed: boolean): void => {
      if (settled) return
      settled = true
      signal.removeEventListener('abort', onAbort)
      resolve(elapsed)
    }
    const timer = setTimeout(() => finish(true), delayMs)
    const onAbort = (): void => {
      clearTimeout(timer)
      finish(false)
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

function disposeNativePromise(value: object): void {
  try {
    Reflect.apply(intrinsicPromiseThen, value, [(): undefined => undefined, (): undefined => undefined])
  } catch {
    // Arbitrary thenables and hostile Promise species are outside best-effort cleanup.
  }
}

function captureInitialState<State extends object>(initialState: Readonly<State>): State {
  if (typeof initialState !== 'object' || initialState === null || Array.isArray(initialState)) {
    throw new OptionValidationError('initialState must be a plain data record')
  }
  const prototype = captureOptionValue(() => Object.getPrototypeOf(initialState), 'initialState prototype could not be read')
  if (prototype !== Object.prototype && prototype !== null) {
    throw new OptionValidationError('initialState must be a plain data record')
  }
  const keys = captureOptionValue(() => Reflect.ownKeys(initialState), 'initialState keys could not be read')
  if (keys.length > MAX_PORTABLE_COLLECTION_LENGTH) {
    throw new OptionValidationError('initialState exceeds the portable limit')
  }
  const target: Record<string, unknown> = {}
  for (const key of keys) {
    if (typeof key !== 'string') throw new OptionValidationError('initialState keys must be strings')
    const descriptor = captureOptionValue(
      () => Reflect.getOwnPropertyDescriptor(initialState, key),
      'initialState property could not be captured',
    )
    if (descriptor === undefined || !descriptor.enumerable || !('value' in descriptor)) {
      throw new OptionValidationError('initialState properties must be enumerable data properties')
    }
    Object.defineProperty(target, key, {
      value: descriptor.value,
      writable: true,
      enumerable: true,
      configurable: true,
    })
  }
  const carrier = new Proxy(target, stateProxyHandler) as State
  stateTargets.set(carrier, target)
  return carrier
}

const stateProxyHandler: ProxyHandler<Record<string, unknown>> = {
  get(target, property, receiver) {
    if (typeof property === 'symbol') return undefined
    return Reflect.get(target, property, receiver)
  },
  set(target, property, value) {
    if (typeof property !== 'string') {
      throw new SemanticMisuse('state_record_misuse', 'state keys must be strings')
    }
    Object.defineProperty(target, property, stateDataDescriptor(value))
    return true
  },
  deleteProperty(target, property) {
    if (typeof property !== 'string') {
      throw new SemanticMisuse('state_record_misuse', 'state keys must be strings')
    }
    return Reflect.deleteProperty(target, property)
  },
  defineProperty(target, property, descriptor) {
    if (
      typeof property !== 'string' ||
      'get' in descriptor ||
      'set' in descriptor ||
      descriptor.configurable === false ||
      descriptor.enumerable === false ||
      descriptor.writable === false
    ) {
      throw new SemanticMisuse('state_record_misuse', 'invalid state property descriptor')
    }
    const previous = Reflect.getOwnPropertyDescriptor(target, property)
    Object.defineProperty(target, property, stateDataDescriptor('value' in descriptor ? descriptor.value : previous?.value))
    return true
  },
  getOwnPropertyDescriptor(target, property) {
    if (typeof property !== 'string') return undefined
    return Reflect.getOwnPropertyDescriptor(target, property)
  },
  ownKeys(target) {
    return Reflect.ownKeys(target)
  },
  has(target, property) {
    if (typeof property === 'symbol') return false
    return Reflect.has(target, property)
  },
  getPrototypeOf() {
    return Object.prototype
  },
  setPrototypeOf() {
    throw new SemanticMisuse('state_record_misuse', 'state prototype is fixed')
  },
  isExtensible() {
    return true
  },
  preventExtensions() {
    throw new SemanticMisuse('state_record_misuse', 'state must remain extensible')
  },
}

function stateDataDescriptor(value: unknown): PropertyDescriptor {
  return {
    value,
    writable: true,
    enumerable: true,
    configurable: true,
  }
}

function resolveStateCarrier<State extends object>(resolve: (value: State | PromiseLike<State>) => void, state: State): void {
  const target = requireGraphValue(stateTargets, state, 'state carrier target')
  const previous = Reflect.getOwnPropertyDescriptor(target, 'then')
  Object.defineProperty(target, 'then', stateDataDescriptor(undefined))
  try {
    resolve(state)
  } finally {
    if (previous === undefined) Reflect.deleteProperty(target, 'then')
    else Object.defineProperty(target, 'then', previous)
  }
}

function captureOptionValue<Value>(operation: () => Value, message: string): Value {
  try {
    return operation()
  } catch (error) {
    throw new OptionValidationError(message, { cause: error })
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

function captureRetry(value: unknown): RetryPolicy {
  const captured = captureOptions(value, ['maxAttempts', 'shouldRetry', 'delayMs'], 'RetryPolicy')
  const maxAttempts = captured.maxAttempts === undefined ? 1 : requirePositiveInteger(captured.maxAttempts, 'RetryPolicy.maxAttempts')
  const shouldRetry =
    captured.shouldRetry === undefined
      ? (_failure: Failure): boolean => true
      : requireCallback<(failure: Failure) => boolean>(captured.shouldRetry, 'RetryPolicy.shouldRetry')
  let delayMs: RetryPolicy['delayMs']
  if (captured.delayMs === undefined) {
    delayMs = 0
  } else if (typeof captured.delayMs === 'function') {
    delayMs = captured.delayMs as (failedAttempt: number, failure: Failure) => number
  } else {
    delayMs = requireNonnegativeInteger(captured.delayMs, 'RetryPolicy.delayMs')
  }
  return Object.freeze({ maxAttempts, shouldRetry, delayMs })
}

function captureExits(value: unknown): readonly string[] {
  const isArray = captureHostValue(() => Array.isArray(value), 'Flow.exits could not be captured')
  if (!isArray) throw new GraphDefinitionError('Flow.exits must be an array of actions')
  const arrayValue = value as unknown[]
  const length = captureHostValue(() => Reflect.get(arrayValue, 'length') as unknown, 'Flow.exits could not be captured')
  if (typeof length !== 'number' || !Number.isSafeInteger(length) || length < 0) {
    throw new GraphDefinitionError('Flow.exits length must be a nonnegative safe integer')
  }
  if (length > MAX_PORTABLE_COLLECTION_LENGTH) {
    throw new GraphDefinitionError('Flow.exits exceeds the portable limit')
  }
  const captured: string[] = []
  const seen = new Set<string>()
  for (let index = 0; index < length; index += 1) {
    const rawAction = captureHostValue(() => Reflect.get(arrayValue, String(index)), 'Flow.exits could not be captured')
    const action = requireControlString(rawAction, 'Flow exit')
    if (seen.has(action)) throw new GraphDefinitionError(`duplicate Flow exit: ${JSON.stringify(action)}`)
    seen.add(action)
    captured.push(action)
  }
  return Object.freeze(captured)
}

function captureOptions(value: unknown, declaredKeys: readonly string[], owner: string): Record<string, unknown> {
  if (value === undefined) return Object.create(null) as Record<string, unknown>
  if (value === null || typeof value !== 'object') {
    throw new GraphDefinitionError(`${owner} options must be a plain record`)
  }

  const prototype = captureHostValue(() => Reflect.getPrototypeOf(value), `${owner} options could not be captured`)
  if (prototype !== Object.prototype && prototype !== null) {
    throw new GraphDefinitionError(`${owner} options must be a plain record`)
  }

  const ownKeys = captureHostValue(() => Reflect.ownKeys(value), `${owner} options could not be captured`)
  if (ownKeys.length > MAX_PORTABLE_COLLECTION_LENGTH) {
    throw new GraphDefinitionError(`${owner} options exceed the portable limit`)
  }
  const allowed = new Set(declaredKeys)
  const present = new Set<string>()
  for (const key of ownKeys) {
    if (typeof key !== 'string') throw new GraphDefinitionError(`${owner} options cannot contain symbol keys`)
    if (!allowed.has(key)) throw new GraphDefinitionError(`${owner} options contain unknown field ${JSON.stringify(key)}`)
    const descriptor = captureHostValue(() => Reflect.getOwnPropertyDescriptor(value, key), `${owner} options could not be captured`)
    if (descriptor === undefined || !descriptor.enumerable) {
      throw new GraphDefinitionError(`${owner} option ${JSON.stringify(key)} must be enumerable`)
    }
    present.add(key)
  }

  const captured = Object.create(null) as Record<string, unknown>
  for (const key of declaredKeys) {
    if (!present.has(key)) continue
    const field = captureHostValue(() => Reflect.get(value, key), `${owner} options could not be captured`)
    if (field !== undefined) captured[key] = field
  }
  return captured
}

function captureHostValue<Value>(operation: () => Value, message: string): Value {
  try {
    return operation()
  } catch (cause) {
    throw new GraphDefinitionError(message, { cause })
  }
}

function inferHandlerName(handler: Function): string {
  try {
    const name = Reflect.get(handler, 'name')
    return typeof name === 'string' && name.length > 0 ? name : 'anonymous'
  } catch (error) {
    throw new GraphDefinitionError('node handler name could not be read', { cause: error })
  }
}

function requireControlString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new GraphDefinitionError(`${field} must be a nonempty string`)
  }
  return value
}

function requirePositiveInteger(value: unknown, field: string): number {
  const result = requireSafeInteger(value, field)
  if (result <= 0) throw new GraphDefinitionError(`${field} must be positive`)
  return result
}

function requireNonnegativeInteger(value: unknown, field: string): number {
  const result = requireSafeInteger(value, field)
  if (result < 0) throw new GraphDefinitionError(`${field} must be nonnegative`)
  return result
}

function requireSafeInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) {
    throw new GraphDefinitionError(`${field} must be a safe integer`)
  }
  return Object.is(value, -0) ? 0 : value
}

function requireCallback<Callback extends Function>(value: unknown, field: string): Callback {
  if (typeof value !== 'function') throw new GraphDefinitionError(`${field} must be callable`)
  return value as Callback
}

function requireOptionalCallback<Callback extends Function>(value: unknown, field: string): Callback | undefined {
  return value === undefined ? undefined : requireCallback<Callback>(value, field)
}

function requireGraphValue<Key extends object, Value>(store: WeakMap<Key, Value>, key: Key, field: string): Value {
  const value = store.get(key)
  if (value === undefined && !store.has(key)) throw new Error(`${field} is not initialized`)
  return value as Value
}
