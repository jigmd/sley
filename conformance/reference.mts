type JsonObject = Record<string, unknown>
type Program = {
  root: string
  elements: Record<string, ElementDefinition>
  links: LinkDefinition[]
  initial_state: JsonObject
}
type NodeDefinition = { kind: 'node'; steps: Step[] }
type FlowDefinition = {
  kind: 'flow'
  entry: string
  exits?: string[]
  concurrency?: number
  combine?: Step[]
}
type ElementDefinition = NodeDefinition | FlowDefinition
type LinkDefinition = { source: string; target: string; action?: string }
type Step = Record<string, unknown> & { op: string }

const MISSING = Symbol('host-missing')
type RuntimeValue = unknown | typeof MISSING
type Arm = {
  kind: 'emit' | 'end'
  action: string | null
  value: RuntimeValue
  present: boolean
}
type Terminal = {
  type: 'end' | 'exit'
  action: string | null
  value: RuntimeValue
  hasOutput: boolean
}
type ContractFailure = { kind: 'unknown_action'; action: string; source: string }

const hasOwn = (value: object, key: PropertyKey): boolean => Object.prototype.hasOwnProperty.call(value, key)

export function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as JsonObject)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalize(item)]),
    )
  }
  return value
}

function normalize(value: RuntimeValue): unknown {
  if (value === MISSING) return { $host: 'missing' }
  if (Array.isArray(value)) return value.map(normalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value as JsonObject).map(([key, item]) => [key, normalize(item)]))
  }
  return value
}

function readPath(value: RuntimeValue, path: string[]): RuntimeValue {
  let current = value
  for (const key of path) {
    if (current === null || current === MISSING || typeof current !== 'object' || !hasOwn(current, key)) {
      throw new Error(`fixture expression cannot read ${JSON.stringify(path)}`)
    }
    current = (current as JsonObject)[key]
  }
  return current
}

export class ReferenceInterpreter {
  private readonly program: Program
  private readonly elements: Record<string, ElementDefinition>
  private readonly links: LinkDefinition[]
  private readonly callerState: JsonObject
  private readonly state: JsonObject
  private readonly events: string[] = []
  private readonly stats = {
    activations: 0,
    attempts: 0,
    transitions: 0,
    retries: 0,
    reports: 0,
    scopes: 0,
    peak_ready: 0,
    peak_callbacks: 0,
    duration_ms: 0,
  }

  constructor(program: Program) {
    this.program = structuredClone(program)
    this.elements = this.program.elements
    this.links = this.program.links
    this.validateProgram()
    this.callerState = structuredClone(this.program.initial_state)
    this.state = { ...this.callerState }
  }

  private validateProgram(): void {
    const root = this.elements[this.program.root]
    if (root?.kind !== 'flow') throw new Error('program root must name a Flow')

    const seen = new Set<string>()
    for (const [key, element] of Object.entries(this.elements)) {
      if (element.kind === 'flow' && this.elements[element.entry] === undefined) {
        throw new Error(`Flow ${JSON.stringify(key)} has an unknown entry`)
      }
    }
    for (const link of this.links) {
      if (this.elements[link.source] === undefined || this.elements[link.target] === undefined) {
        throw new Error('link source and target must name elements')
      }
      const identity = `${link.source}\u0000${link.action ?? ''}`
      if (seen.has(identity)) throw new Error(`duplicate fixture link ${identity}`)
      seen.add(identity)
    }
  }

  compile(): JsonObject {
    let nextElementId = 1
    let nextScopeId = 2
    const placements = new Map<string, number>()
    const elementRecords = new Map<number, JsonObject>()
    const scopeRecords: JsonObject[] = []
    const pendingScopes: Array<[string, number, number | null]> = [[this.program.root, 1, null]]

    const placementKey = (scopeId: number, key: string): string => `${scopeId}\u0000${key}`
    const place = (scopeId: number, key: string, parentScopeId: number | null): number => {
      const identity = placementKey(scopeId, key)
      const existing = placements.get(identity)
      if (existing !== undefined) return existing
      const elementId = nextElementId++
      placements.set(identity, elementId)
      const element = this.elements[key]!
      if (element.kind === 'flow') {
        const ownedScopeId = elementId === 1 ? 1 : nextScopeId++
        if (elementId !== 1) pendingScopes.push([key, ownedScopeId, scopeId])
        elementRecords.set(elementId, {
          element_id: elementId,
          kind: 'flow',
          name: key,
          parent_scope_definition_id: parentScopeId,
          owned_scope_definition_id: ownedScopeId,
          links: [],
        })
      } else {
        elementRecords.set(elementId, {
          element_id: elementId,
          kind: 'node',
          name: key,
          parent_scope_definition_id: scopeId,
          links: [],
          retry: { max_attempts: 1 },
          timeout_ms: null,
        })
      }
      return elementId
    }

    const rootElementId = place(1, this.program.root, null)

    while (pendingScopes.length > 0) {
      const [flowKey, scopeId, parentScopeId] = pendingScopes.shift()!
      const flow = this.elements[flowKey]!
      if (flow.kind !== 'flow') throw new Error('pending scope must be a Flow')
      const flowElementId = placements.get(placementKey(parentScopeId ?? 1, flowKey))!
      const entryKey = flow.entry
      const entryId = place(scopeId, entryKey, scopeId)
      scopeRecords.push({
        scope_definition_id: scopeId,
        owner_element_id: flowElementId,
        parent_scope_definition_id: parentScopeId,
        entry_element_id: entryId,
        exits: flow.exits ?? [],
        concurrency: flow.concurrency ?? 1,
        max_activations: null,
      })

      const queue = [entryKey]
      const visited = new Set<string>()
      while (queue.length > 0) {
        const source = queue.shift()!
        if (visited.has(source)) continue
        visited.add(source)
        const sourceId = place(scopeId, source, scopeId)
        for (const link of this.links) {
          if (link.source !== source) continue
          const targetIdentity = placementKey(scopeId, link.target)
          const targetWasNew = !placements.has(targetIdentity)
          const targetId = place(scopeId, link.target, scopeId)
          const sourceRecord = elementRecords.get(sourceId)!
          ;(sourceRecord.links as JsonObject[]).push({
            action: link.action ?? null,
            target_element_id: targetId,
          })
          if (targetWasNew) queue.push(link.target)
        }
      }
    }

    const autoMax = Math.max(
      ...Object.values(this.elements)
        .filter((element): element is FlowDefinition => element.kind === 'flow')
        .map((flow) => flow.concurrency ?? 1),
    )
    return {
      schema_version: 1,
      auto_max_concurrency: autoMax,
      root: { element_id: rootElementId, scope_definition_id: 1 },
      elements: [...elementRecords.entries()].sort(([left], [right]) => left - right).map(([, value]) => value),
      scope_definitions: scopeRecords,
    }
  }

  run(): JsonObject {
    this.events.push('run_started')
    this.stats.activations = 1
    const { terminals, failure } = this.executeFlow(this.program.root, MISSING)
    this.events.push('run_finished')

    const result: JsonObject =
      failure === null
        ? {
            status: 'completed',
            state: normalize(this.state),
            terminals: terminals.map((terminal) => this.normalizeTerminal(terminal)),
            terminal_outputs: terminals.filter((terminal) => terminal.hasOutput).map((terminal) => normalize(terminal.value)),
          }
        : {
            status: 'failed',
            state: normalize(this.state),
            terminals: terminals.map((terminal) => this.normalizeTerminal(terminal)),
            failure,
          }
    if (failure === null && terminals.length === 0) {
      throw new Error('a completed root Flow must have a terminal')
    }
    const runProjection: JsonObject =
      failure === null
        ? { type: 'return', state: normalize(this.state) }
        : {
            type: 'throw',
            error: {
              name: 'RunError',
              message: 'Caskada run failed',
              result_status: 'failed',
            },
          }

    return {
      compiled: this.compile(),
      result,
      run_projection: runProjection,
      event_kinds: [...this.events],
      stats: { ...this.stats },
      initial_state_after: normalize(this.callerState),
    }
  }

  private executeFlow(
    flowKey: string,
    incoming: RuntimeValue,
  ): {
    terminals: Terminal[]
    failure: ContractFailure | null
  } {
    const flow = this.elements[flowKey]!
    if (flow.kind !== 'flow') throw new Error('executeFlow requires a Flow')
    this.stats.scopes++
    this.events.push('scope_started')
    this.stats.activations++
    const queue: Array<[string, RuntimeValue]> = [[flow.entry, incoming]]
    this.recordReady(queue)
    let terminals: Terminal[] = []

    while (queue.length > 0) {
      const [elementKey, branchInput] = queue.shift()!
      const element = this.elements[elementKey]!
      if (element.kind === 'flow') {
        const child = this.executeFlow(elementKey, branchInput)
        if (child.failure !== null) {
          this.events.push('scope_finished')
          return { terminals, failure: child.failure }
        }
        const failure = this.forwardChild(flowKey, elementKey, child.terminals, queue, terminals)
        if (failure !== null) {
          this.events.push('scope_finished')
          return { terminals, failure }
        }
        continue
      }

      this.stats.attempts++
      this.stats.peak_callbacks = Math.max(this.stats.peak_callbacks, 1)
      this.events.push('callback_started')
      let arms = this.executeSteps(element.steps, branchInput, null)
      if (arms.length === 0) {
        arms = [{ kind: 'emit', action: null, value: branchInput, present: true }]
      }
      this.events.push('callback_finished')
      const failure = this.routeArms(flowKey, elementKey, arms, queue, terminals)
      if (failure !== null) {
        this.events.push('scope_finished')
        return { terminals, failure }
      }
    }

    if (flow.combine !== undefined) {
      const outputs = terminals.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.value)
      this.events.push('callback_started')
      const combineArms = this.executeSteps(flow.combine, incoming, outputs)
      this.events.push('callback_finished')
      if (combineArms.length > 0) {
        terminals = []
        for (const arm of combineArms) {
          this.stats.transitions++
          this.events.push('transition_committed')
          const terminal: Terminal =
            arm.kind === 'end'
              ? { type: 'end', action: null, value: arm.value, hasOutput: arm.present }
              : { type: 'exit', action: arm.action, value: arm.value, hasOutput: true }
          terminals.push(terminal)
          this.events.push('terminal_committed')
        }
      }
    }

    this.events.push('scope_finished')
    return { terminals, failure: null }
  }

  private forwardChild(
    parentFlowKey: string,
    childKey: string,
    childTerminals: Terminal[],
    queue: Array<[string, RuntimeValue]>,
    terminals: Terminal[],
  ): ContractFailure | null {
    const arms: Arm[] = childTerminals.map((terminal) =>
      terminal.type === 'end'
        ? { kind: 'end', action: null, value: terminal.value, present: terminal.hasOutput }
        : { kind: 'emit', action: terminal.action, value: terminal.value, present: true },
    )
    return this.routeArms(parentFlowKey, childKey, arms, queue, terminals)
  }

  private routeArms(
    flowKey: string,
    sourceKey: string,
    arms: Arm[],
    queue: Array<[string, RuntimeValue]>,
    terminals: Terminal[],
  ): ContractFailure | null {
    const flow = this.elements[flowKey]!
    if (flow.kind !== 'flow') throw new Error('routeArms requires an owning Flow')
    const resolutions: Array<{ kind: 'end' | 'target' | 'exit'; target: string | null }> = []

    for (const arm of arms) {
      if (arm.kind === 'end') {
        resolutions.push({ kind: 'end', target: null })
        continue
      }
      const target = this.linkTarget(sourceKey, arm.action)
      if (target !== null) resolutions.push({ kind: 'target', target })
      else if (arm.action === null || (flow.exits ?? []).includes(arm.action)) {
        resolutions.push({ kind: 'exit', target: null })
      } else {
        return { kind: 'unknown_action', action: arm.action, source: sourceKey }
      }
    }

    arms.forEach((arm, index) => {
      const resolution = resolutions[index]!
      this.stats.transitions++
      this.events.push('transition_committed')
      if (resolution.kind === 'target') {
        this.stats.activations++
        queue.push([resolution.target!, arm.value])
        this.recordReady(queue)
      } else if (resolution.kind === 'end') {
        terminals.push({ type: 'end', action: null, value: arm.value, hasOutput: arm.present })
        this.events.push('terminal_committed')
      } else {
        terminals.push({ type: 'exit', action: arm.action, value: arm.value, hasOutput: true })
        this.events.push('terminal_committed')
      }
    })
    return null
  }

  private linkTarget(source: string, action: string | null): string | null {
    const match = this.links.find((link) => link.source === source && (link.action ?? null) === action)
    return match?.target ?? null
  }

  private executeSteps(steps: Step[], branchInput: RuntimeValue, outputs: RuntimeValue[] | null): Arm[] {
    const arms: Arm[] = []
    for (const step of steps) {
      if (step.op === 'set') {
        this.setPath(step.path as string[], this.evaluate(step.value, branchInput, outputs))
      } else if (step.op === 'append') {
        const target = readPath(this.state, step.path as string[])
        if (!Array.isArray(target)) throw new Error('append target must be a list')
        target.push(this.evaluate(step.value, branchInput, outputs))
      } else if (step.op === 'emit') {
        arms.push({
          kind: 'emit',
          action: typeof step.action === 'string' ? step.action : null,
          value: hasOwn(step, 'input') ? this.evaluate(step.input, branchInput, outputs) : branchInput,
          present: true,
        })
      } else if (step.op === 'end') {
        const present = hasOwn(step, 'output')
        arms.push({
          kind: 'end',
          action: null,
          value: present ? this.evaluate(step.output, branchInput, outputs) : MISSING,
          present,
        })
      } else {
        throw new Error(`unknown fixture operation ${JSON.stringify(step.op)}`)
      }
    }
    return arms
  }

  private evaluate(expression: unknown, branchInput: RuntimeValue, outputs: RuntimeValue[] | null): RuntimeValue {
    if (Array.isArray(expression)) return expression.map((item) => this.evaluate(item, branchInput, outputs))
    if (expression === null || typeof expression !== 'object') return expression
    const record = expression as JsonObject
    if (!hasOwn(record, '$')) {
      return Object.fromEntries(Object.entries(record).map(([key, value]) => [key, this.evaluate(value, branchInput, outputs)]))
    }

    const kind = record.$
    if (kind === 'input') return readPath(branchInput, (record.path as string[] | undefined) ?? [])
    if (kind === 'state') return readPath(this.state, (record.path as string[] | undefined) ?? [])
    if (kind === 'outputs') {
      if (outputs === null) throw new Error('outputs expression is combine-only')
      return [...outputs]
    }
    if (kind === 'add') {
      return Number(this.evaluate(record.left, branchInput, outputs)) + Number(this.evaluate(record.right, branchInput, outputs))
    }
    if (kind === 'multiply') {
      return Number(this.evaluate(record.left, branchInput, outputs)) * Number(this.evaluate(record.right, branchInput, outputs))
    }
    if (kind === 'sum') {
      const items = this.evaluate(record.items, branchInput, outputs)
      if (!Array.isArray(items)) throw new Error('sum expression requires a list')
      return items.reduce((total, item) => total + Number(item), 0)
    }
    throw new Error(`unknown fixture expression ${JSON.stringify(kind)}`)
  }

  private setPath(path: string[], value: RuntimeValue): void {
    if (path.length === 0) throw new Error('state path cannot be empty')
    let current = this.state
    for (const key of path.slice(0, -1)) {
      const child = current[key]
      if (child === null || typeof child !== 'object' || Array.isArray(child)) current[key] = {}
      current = current[key] as JsonObject
    }
    current[path.at(-1)!] = value
  }

  private recordReady(queue: Array<[string, RuntimeValue]>): void {
    this.stats.peak_ready = Math.max(this.stats.peak_ready, queue.length)
  }

  private normalizeTerminal(terminal: Terminal): JsonObject {
    const value: JsonObject =
      terminal.type === 'end'
        ? { type: 'end', has_output: terminal.hasOutput }
        : { type: 'exit', action: terminal.action, has_output: true }
    if (terminal.hasOutput) value.output = normalize(terminal.value)
    return value
  }
}
