// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2026, Victor Duarte

import { DuplicateLinkError, GraphDefinitionError, RunError } from './contracts.js'
import { startRuntime } from './runner.js'
import { captureInitialState, resolveState } from './state.js'

import type {
  Action,
  FlowCombineHandler,
  FlowRecoveryHandler,
  NodeHandler,
  NodeRecoveryHandler,
  NormalizedRetryPolicy,
  RetryPolicy,
  RunHandle,
} from './contracts.js'

const stateInvariant: unique symbol = Symbol('caskada.state')

export interface Link<State extends object = Record<string, unknown>> {
  readonly action: Action | null
  readonly target: GraphElement<State>
}

export abstract class GraphElement<State extends object = Record<string, unknown>> {
  declare private readonly [stateInvariant]: (state: State) => State
  readonly name: string
  readonly #links = new Map<Action | null, Link<State>>()

  protected constructor(name: string) {
    this.name = nonemptyString(name, 'element name')
  }

  link(target: GraphElement<State>): void
  link(target: GraphElement<State>, action: Action): void
  link(target: GraphElement<State>, action?: Action): void {
    if (!(target instanceof GraphElement)) throw new GraphDefinitionError('link target must be a Node or Flow')
    const key = arguments.length === 1 ? null : nonemptyString(action, 'link action')
    if (this.#links.has(key)) {
      throw new DuplicateLinkError(`duplicate link action: ${key === null ? 'unlabelled' : JSON.stringify(key)}`)
    }
    this.#links.set(key, Object.freeze({ action: key, target }))
  }

  links(): readonly Link<State>[] {
    return Object.freeze([...this.#links.values()])
  }
}

export interface NodeOptions<State extends object = Record<string, unknown>, Input = unknown> {
  readonly name?: string
  readonly retry?: RetryPolicy
  readonly recover?: NodeRecoveryHandler<State, Input>
}

export class Node<State extends object = Record<string, unknown>, Input = unknown> extends GraphElement<State> {
  constructor(handler: NodeHandler<State, Input>, options: NodeOptions<State, Input> = {}) {
    if (typeof handler !== 'function') throw new GraphDefinitionError('node handler must be a function')
    const captured = optionsRecord(options, ['name', 'retry', 'recover'], 'Node')
    const inferredName = typeof handler.name === 'string' && handler.name ? handler.name : 'anonymous'
    const name = captured.name === undefined ? inferredName : nonemptyString(captured.name, 'Node.name')
    const recover = optionalFunction<NodeRecoveryHandler<State, Input>>(captured.recover, 'Node.recover')
    super(name)
    nodeData.set(this, {
      handler,
      retry: normalizeRetry(captured.retry),
      recover,
    })
  }
}

export function node<State extends object = Record<string, unknown>, Input = unknown>(
  handler: NodeHandler<State, Input>,
  options: NodeOptions<State, Input> = {},
): Node<State, Input> {
  return new Node(handler, options)
}

export interface FlowOptions<State extends object = Record<string, unknown>> {
  readonly name?: string
  readonly exits?: readonly Action[]
  readonly concurrency?: number
  readonly maxActivations?: number
  readonly combine?: FlowCombineHandler<State>
  readonly recover?: FlowRecoveryHandler<State>
}

export class Flow<State extends object = Record<string, unknown>> extends GraphElement<State> {
  constructor(entry: GraphElement<State>, options: FlowOptions<State> = {}) {
    if (!(entry instanceof GraphElement)) throw new GraphDefinitionError('Flow.entry must be a Node or Flow')
    const captured = optionsRecord(options, ['name', 'exits', 'concurrency', 'maxActivations', 'combine', 'recover'], 'Flow')
    const name = captured.name === undefined ? 'Flow' : nonemptyString(captured.name, 'Flow.name')
    const exits = captureExits(captured.exits)
    const concurrency = captured.concurrency === undefined ? 1 : positiveInteger(captured.concurrency, 'Flow.concurrency')
    const maxActivations =
      captured.maxActivations === undefined ? undefined : positiveInteger(captured.maxActivations, 'Flow.maxActivations')
    const combine = optionalFunction<FlowCombineHandler<State>>(captured.combine, 'Flow.combine')
    const recover = optionalFunction<FlowRecoveryHandler<State>>(captured.recover, 'Flow.recover')
    super(name)
    flowData.set(this, { entry, exits, concurrency, maxActivations, combine, recover })
  }

  get entry(): GraphElement<State> {
    return requireData(flowData, this, 'Flow').entry
  }

  get exits(): readonly Action[] {
    return requireData(flowData, this, 'Flow').exits
  }

  get concurrency(): number {
    return requireData(flowData, this, 'Flow').concurrency
  }

  get maxActivations(): number | undefined {
    return requireData(flowData, this, 'Flow').maxActivations
  }

  compile(): CompiledFlow<State> {
    return new CompiledFlowImpl(compile(this))
  }

  start(initialState: Readonly<State>): RunHandle<State> {
    return this.compile().start(initialState)
  }

  run(initialState: Readonly<State>): Promise<State> {
    return this.compile().run(initialState)
  }
}

export interface CompiledFlow<State extends object = Record<string, unknown>> {
  start(initialState: Readonly<State>): RunHandle<State>
  run(initialState: Readonly<State>): Promise<State>
  describe(): CompiledDescription
}

class CompiledFlowImpl<State extends object> implements CompiledFlow<State> {
  readonly #snapshot: CompiledSnapshot

  constructor(snapshot: CompiledSnapshot) {
    this.#snapshot = snapshot
  }

  start(initialState: Readonly<State>): RunHandle<State> {
    return startRuntime(this.#snapshot, captureInitialState(initialState))
  }

  run(initialState: Readonly<State>): Promise<State> {
    const handle = this.start(initialState)
    return new Promise<State>((resolve, reject) => {
      handle.result().then((result) => {
        if (result.status === 'failed') {
          reject(new RunError(result))
        } else {
          resolveState(resolve, result.state)
        }
      }, reject)
    })
  }

  describe(): CompiledDescription {
    return describe(this.#snapshot)
  }
}

export interface CompiledLink {
  readonly action: Action | null
  readonly targetElementId: number
}

export interface CompiledPlacement {
  readonly elementId: number
  readonly kind: 'node' | 'flow'
  readonly name: string
  readonly links: readonly CompiledLink[]
  readonly handler?: NodeHandler<any, any>
  readonly retry?: NormalizedRetryPolicy
  readonly recover?: NodeRecoveryHandler<any, any>
  readonly ownedScopeId?: number
}

export interface CompiledScope {
  readonly scopeId: number
  readonly ownerElementId: number
  readonly parentScopeId: number | null
  readonly entryElementId: number
  readonly name: string
  readonly exits: readonly Action[]
  readonly concurrency: number
  readonly maxActivations: number | undefined
  readonly combine: FlowCombineHandler<any> | undefined
  readonly recover: FlowRecoveryHandler<any> | undefined
}

export interface CompiledSnapshot {
  readonly scopes: readonly CompiledScope[]
  readonly placements: readonly CompiledPlacement[]
}

export interface CompiledDescription {
  readonly schema_version: 1
  readonly root: { readonly element_id: 1; readonly scope_id: 1 }
  readonly scopes: readonly Record<string, unknown>[]
  readonly elements: readonly Record<string, unknown>[]
}

interface NodeData {
  readonly handler: NodeHandler<any, any>
  readonly retry: NormalizedRetryPolicy
  readonly recover: NodeRecoveryHandler<any, any> | undefined
}

interface FlowData {
  readonly entry: GraphElement<any>
  readonly exits: readonly Action[]
  readonly concurrency: number
  readonly maxActivations: number | undefined
  readonly combine: FlowCombineHandler<any> | undefined
  readonly recover: FlowRecoveryHandler<any> | undefined
}

const nodeData = new WeakMap<Node<any, any>, NodeData>()
const flowData = new WeakMap<Flow<any>, FlowData>()

interface ScopeWork {
  readonly scopeId: number
  readonly ownerElementId: number
  readonly parentScopeId: number | null
  readonly flow: Flow<any>
  readonly ancestors: readonly Flow<any>[]
}

class Compiler {
  readonly placements = new Map<number, CompiledPlacement>()
  readonly scopes = new Map<number, CompiledScope>()
  readonly work: ScopeWork[]
  readonly ownedScopes = new Map<number, number>()
  nextElementId = 2
  nextScopeId = 2

  constructor(root: Flow<any>) {
    this.placements.set(1, { elementId: 1, kind: 'flow', name: root.name, links: [], ownedScopeId: 1 })
    this.ownedScopes.set(1, 1)
    this.work = [{ scopeId: 1, ownerElementId: 1, parentScopeId: null, flow: root, ancestors: [root] }]
  }

  compile(): CompiledSnapshot {
    for (const scope of this.work) this.compileScope(scope)
    return Object.freeze({
      scopes: Object.freeze(Array.from({ length: this.nextScopeId - 1 }, (_, index) => required(this.scopes, index + 1))),
      placements: Object.freeze(Array.from({ length: this.nextElementId - 1 }, (_, index) => required(this.placements, index + 1))),
    })
  }

  private compileScope(scope: ScopeWork): void {
    const ids = new Map<GraphElement<any>, number>()
    const elements: GraphElement<any>[] = []

    const add = (element: GraphElement<any>): number => {
      const existing = ids.get(element)
      if (existing !== undefined) return existing
      if (!(element instanceof Node) && !(element instanceof Flow)) {
        throw new GraphDefinitionError('unsupported graph element')
      }
      const elementId = this.nextElementId++
      ids.set(element, elementId)
      elements.push(element)
      if (element instanceof Flow) {
        if (scope.ancestors.includes(element)) {
          throw new GraphDefinitionError('recursive Flow containment is not allowed')
        }
        const ownedScopeId = this.nextScopeId++
        this.ownedScopes.set(elementId, ownedScopeId)
        this.work.push({
          scopeId: ownedScopeId,
          ownerElementId: elementId,
          parentScopeId: scope.scopeId,
          flow: element,
          ancestors: [...scope.ancestors, element],
        })
      }
      return elementId
    }

    const entryElementId = add(requireData(flowData, scope.flow, 'Flow').entry)
    for (const element of elements) {
      const links = Object.freeze(element.links().map((link) => ({ action: link.action, targetElementId: add(link.target) })))
      const elementId = required(ids, element)
      if (element instanceof Node) {
        const data = requireData(nodeData, element, 'Node')
        this.placements.set(elementId, {
          elementId,
          kind: 'node',
          name: element.name,
          links,
          handler: data.handler,
          retry: data.retry,
          ...(data.recover === undefined ? {} : { recover: data.recover }),
        })
      } else {
        this.placements.set(elementId, {
          elementId,
          kind: 'flow',
          name: element.name,
          links,
          ownedScopeId: required(this.ownedScopes, elementId),
        })
      }
    }

    const data = requireData(flowData, scope.flow, 'Flow')
    this.scopes.set(scope.scopeId, {
      scopeId: scope.scopeId,
      ownerElementId: scope.ownerElementId,
      parentScopeId: scope.parentScopeId,
      entryElementId,
      name: scope.flow.name,
      exits: data.exits,
      concurrency: data.concurrency,
      maxActivations: data.maxActivations,
      combine: data.combine,
      recover: data.recover,
    })
  }
}

function compile(root: Flow<any>): CompiledSnapshot {
  return new Compiler(root).compile()
}

function describe(snapshot: CompiledSnapshot): CompiledDescription {
  return {
    schema_version: 1,
    root: { element_id: 1, scope_id: 1 },
    scopes: snapshot.scopes.map((scope) => ({
      scope_id: scope.scopeId,
      owner_element_id: scope.ownerElementId,
      parent_scope_id: scope.parentScopeId,
      entry_element_id: scope.entryElementId,
      name: scope.name,
      exits: [...scope.exits],
      concurrency: scope.concurrency,
      max_activations: scope.maxActivations ?? null,
    })),
    elements: snapshot.placements.map((element) => ({
      element_id: element.elementId,
      kind: element.kind,
      name: element.name,
      links: element.links.map((link) => ({ action: link.action, target_element_id: link.targetElementId })),
      ...(element.retry === undefined ? { owned_scope_id: element.ownedScopeId } : { max_attempts: element.retry.maxAttempts }),
    })),
  }
}

function normalizeRetry(value: unknown): NormalizedRetryPolicy {
  const retry = optionsRecord(value ?? {}, ['maxAttempts', 'shouldRetry', 'delayMs'], 'RetryPolicy')
  const maxAttempts = retry.maxAttempts === undefined ? 1 : positiveInteger(retry.maxAttempts, 'RetryPolicy.maxAttempts')
  const shouldRetry =
    retry.shouldRetry === undefined
      ? () => true
      : optionalFunction<(failure: any) => boolean>(retry.shouldRetry, 'RetryPolicy.shouldRetry')
  const delayMs =
    retry.delayMs === undefined
      ? 0
      : typeof retry.delayMs === 'function'
        ? retry.delayMs
        : nonnegativeInteger(retry.delayMs, 'RetryPolicy.delayMs')
  return Object.freeze({ maxAttempts, shouldRetry: shouldRetry!, delayMs })
}

function captureExits(value: unknown): readonly string[] {
  if (value === undefined) return Object.freeze([])
  if (!Array.isArray(value)) throw new GraphDefinitionError('Flow.exits must be an array of actions')
  const exits = value.map((action) => nonemptyString(action, 'Flow exit'))
  if (new Set(exits).size !== exits.length) throw new GraphDefinitionError('Flow.exits contains a duplicate action')
  return Object.freeze(exits)
}

function optionsRecord(value: unknown, allowed: readonly string[], name: string): Record<string, any> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new GraphDefinitionError(`${name} options must be an object`)
  }
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) throw new GraphDefinitionError(`unknown ${name} option: ${key}`)
  }
  return value as Record<string, any>
}

function optionalFunction<T>(value: unknown, field: string): T | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'function') throw new GraphDefinitionError(`${field} must be a function`)
  return value as T
}

function nonemptyString(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value) throw new GraphDefinitionError(`${field} must be a nonempty string`)
  return value
}

function positiveInteger(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 1) {
    throw new GraphDefinitionError(`${field} must be a positive safe integer`)
  }
  return value as number
}

function nonnegativeInteger(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw new GraphDefinitionError(`${field} must be a nonnegative safe integer`)
  }
  return value as number
}

function requireData<K extends object, V>(map: WeakMap<K, V>, key: K, name: string): V {
  const value = map.get(key)
  if (value === undefined) throw new Error(`${name} data is missing`)
  return value
}

function required<K, V>(map: Map<K, V>, key: K): V {
  const value = map.get(key)
  if (value === undefined) throw new Error('compiled graph data is missing')
  return value
}
