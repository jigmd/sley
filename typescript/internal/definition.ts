// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// Graph definitions, validation, compilation, and topology inspection.

import {
  DuplicateLinkError,
  GraphDefinitionError,
  MAX_PORTABLE_COLLECTION_LENGTH,
  MAX_SAFE_INTEGER,
  nodeConstructionToken,
  stateInvariant,
} from './contracts.js'

import type {
  Action,
  Failure,
  FlowCombineHandler,
  FlowRecoveryHandler,
  NodeHandler,
  NodeRecoveryHandler,
  RetryOptions,
  RetryPolicy,
} from './contracts.js'

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

export const nodeHandlers = new WeakMap<object, NodeHandler<object, unknown>>()

export const nodeRecoveries = new WeakMap<object, NodeRecoveryHandler<object, unknown> | undefined>()

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

export const flowConstructionToken = Symbol('caskada.flowConstruction')

export class FlowDefinition<State extends object = Record<string, unknown>> extends GraphElement<State> {
  protected readonly _caskadaKind = 'flow' as const

  constructor(token: typeof flowConstructionToken, entry: GraphElement<State>, options?: FlowOptions<State>) {
    if (token !== flowConstructionToken) throw new TypeError('Use Flow(entry) to create a Flow')
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

export type CompiledNodePlacement = CompiledPlacementBase & {
  readonly kind: 'node'
  readonly definition: Node<any>
  readonly retry: RetryPolicy
  readonly timeoutMs: number | undefined
}

type CompiledFlowPlacement = CompiledPlacementBase & {
  readonly kind: 'flow'
  readonly definition: FlowDefinition<any>
  readonly ownedScopeDefinitionId: number
}

export type CompiledPlacement = CompiledNodePlacement | CompiledFlowPlacement

export type CompiledScope = {
  readonly scopeDefinitionId: number
  readonly ownerElementId: number
  readonly parentScopeDefinitionId: number | null
  readonly entryElementId: number
  readonly exits: readonly Action[]
  readonly concurrency: number
  readonly maxActivations: number | undefined
  readonly flow: FlowDefinition<any>
  readonly combine: FlowCombineHandler<any> | undefined
  readonly recover: FlowRecoveryHandler<any> | undefined
}

export type CompiledSnapshot = {
  readonly root: FlowDefinition<any>
  readonly autoMaxConcurrency: number
  readonly scopes: readonly CompiledScope[]
  readonly placements: readonly CompiledPlacement[]
}

type ScopeWork = {
  readonly scopeDefinitionId: number
  readonly ownerElementId: number
  readonly parentScopeDefinitionId: number | null
  readonly flow: FlowDefinition<any>
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

  constructor(private readonly root: FlowDefinition<any>) {
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
      const nested = element as FlowDefinition<any>
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
    const occurrence = element as FlowDefinition<any>
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

export function compileFlow<State extends object>(root: FlowDefinition<State>): CompiledSnapshot {
  if (!flowEntries.has(root)) {
    throw new GraphDefinitionError('only runtime-created Flow definitions can compile')
  }
  validateContainment(root)
  return new DefinitionCompiler(root).compile()
}

function validateContainment(root: FlowDefinition<any>): void {
  const adjacency = new Map<FlowDefinition<any>, readonly FlowDefinition<any>[]>()
  const colors = new Map<FlowDefinition<any>, 'active' | 'complete'>([[root, 'active']])
  const stack: Array<{ flow: FlowDefinition<any>; childIndex: number }> = [{ flow: root, childIndex: 0 }]

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

function nestedFlowDefinitions(flow: FlowDefinition<any>): readonly FlowDefinition<any>[] {
  const seen = new Set<GraphElement<any>>()
  const worklist: GraphElement<any>[] = [flow.entry]
  const nested: FlowDefinition<any>[] = []
  for (let workIndex = 0; workIndex < worklist.length; workIndex += 1) {
    const element = worklist[workIndex]!
    if (seen.has(element)) continue
    seen.add(element)
    const kind = graphDefinitionKind(element)
    if (kind === null) throw new GraphDefinitionError('unsupported GraphElement definition')
    if (kind === 'flow') nested.push(element as FlowDefinition<any>)
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

export function describeCompiled(snapshot: CompiledSnapshot): CompiledDescription {
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
