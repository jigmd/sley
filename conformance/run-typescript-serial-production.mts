import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Flow, node, RunError } from '../typescript/caskada.ts'

import type { Context, GraphElement, ScopeResult, Terminal } from '../typescript/caskada.ts'

type Step = { op: string; [key: string]: unknown }
type ElementDefinition =
  | { kind: 'node'; steps?: Step[] }
  | {
      kind: 'flow'
      entry: string
      exits?: string[]
      concurrency?: number
      combine?: Step[]
    }
type Program = {
  root: string
  elements: Record<string, ElementDefinition>
  links: Array<{ source: string; target: string; action?: string }>
  initial_state: Record<string, unknown>
}
type Fixture = { id: string; program: Program; expect: Record<string, unknown> }

const IMPLEMENTED_FIXTURES = new Set([
  'S01_implicit_default',
  'S02_explicit_input',
  'S03_hard_end',
  'S04_output_presence',
  'S05_fanout_combine',
  'S06_combine_replacement',
  'S07_declared_exit',
  'S08_unknown_action',
  'S09_nested_forwarding',
  'S11_state_copy',
  'S12_explicit_null_input',
  'S13_atomic_batch_rejection',
])

class FixtureRuntime {
  constructor(private readonly program: Program) {}

  build(): Flow<Record<string, unknown>> {
    const elements = new Map<string, GraphElement<Record<string, unknown>>>()
    const unresolved = new Map<string, Extract<ElementDefinition, { kind: 'flow' }>>()
    for (const [identifier, definition] of Object.entries(this.program.elements)) {
      if (definition.kind === 'node') {
        elements.set(identifier, node(this.nodeHandler(definition.steps ?? []), { name: identifier }))
      } else unresolved.set(identifier, definition)
    }

    while (unresolved.size > 0) {
      let progressed = false
      for (const [identifier, definition] of Array.from(unresolved)) {
        const entry = elements.get(definition.entry)
        if (entry === undefined) continue
        const combine = this.combineHandler(definition.combine ?? [])
        elements.set(
          identifier,
          new Flow(entry, {
            name: identifier,
            exits: definition.exits,
            concurrency: definition.concurrency,
            combine,
          }),
        )
        unresolved.delete(identifier)
        progressed = true
      }
      assert(progressed, 'fixture Flow entries contain an unresolved cycle')
    }

    for (const link of this.program.links) {
      const source = requireElement(elements, link.source)
      const target = requireElement(elements, link.target)
      if (link.action === undefined) source.link(target)
      else source.link(target, link.action)
    }
    const root = requireElement(elements, this.program.root)
    assert(root instanceof Flow, 'fixture root must be a Flow')
    return root
  }

  private nodeHandler(steps: Step[]): (context: Context<Record<string, unknown>>) => void {
    return (context) => this.executeSteps(context, steps, undefined)
  }

  private combineHandler(steps: Step[]): ((context: Context<Record<string, unknown>>, result: ScopeResult) => void) | undefined {
    if (steps.length === 0) return undefined
    return (context, result) => {
      this.executeSteps(context, steps, result.outputs)
    }
  }

  private executeSteps(context: Context<Record<string, unknown>>, steps: Step[], outputs: readonly unknown[] | undefined): void {
    for (const step of steps) {
      if (step.op === 'set') {
        setPath(context.state, step.path as string[], this.evaluate(context, step.value, outputs))
      } else if (step.op === 'append') {
        const target = readPath(context.state, step.path as string[])
        assert(Array.isArray(target), 'append target must be an array')
        target.push(this.evaluate(context, step.value, outputs))
      } else if (step.op === 'emit') {
        const valuePresent = Object.hasOwn(step, 'input')
        const value = valuePresent ? this.evaluate(context, step.input, outputs) : context.input
        if (Object.hasOwn(step, 'action')) {
          if (valuePresent) context.emit(step.action as string, value)
          else context.emit(step.action as string)
        } else if (valuePresent) context.emit({ input: value })
        else context.emit()
      } else if (step.op === 'end') {
        if (Object.hasOwn(step, 'output')) context.end(this.evaluate(context, step.output, outputs))
        else context.end()
      } else throw new Error(`unknown fixture operation ${JSON.stringify(step.op)}`)
    }
  }

  private evaluate(context: Context<Record<string, unknown>>, expression: unknown, outputs: readonly unknown[] | undefined): unknown {
    if (Array.isArray(expression)) return expression.map((item) => this.evaluate(context, item, outputs))
    if (expression === null || typeof expression !== 'object') return expression
    const record = expression as Record<string, unknown>
    if (!Object.hasOwn(record, '$')) {
      return Object.fromEntries(Object.entries(record).map(([key, value]) => [key, this.evaluate(context, value, outputs)]))
    }
    if (record.$ === 'input') return readPath(context.input, (record.path as string[] | undefined) ?? [])
    if (record.$ === 'state') return readPath(context.state, (record.path as string[] | undefined) ?? [])
    if (record.$ === 'outputs') {
      assert(outputs !== undefined, 'outputs expression is combine-only')
      return outputs.slice()
    }
    if (record.$ === 'add')
      return (this.evaluate(context, record.left, outputs) as number) + (this.evaluate(context, record.right, outputs) as number)
    if (record.$ === 'multiply')
      return (this.evaluate(context, record.left, outputs) as number) * (this.evaluate(context, record.right, outputs) as number)
    if (record.$ === 'sum') {
      const values = this.evaluate(context, record.items, outputs)
      assert(Array.isArray(values), 'sum expression requires an array')
      return values.reduce<number>((total, value) => total + (value as number), 0)
    }
    throw new Error(`unknown fixture expression ${JSON.stringify(record.$)}`)
  }
}

const fixtureUrl = new URL('./fixtures/serial.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as { fixtures: Fixture[] }
const fixtures = []
for (const fixture of collection.fixtures) {
  if (!IMPLEMENTED_FIXTURES.has(fixture.id)) continue
  const initialState = fixture.program.initial_state
  const runtime = new FixtureRuntime(fixture.program)
  const compiled = runtime.build().compile()
  const settled = await compiled.start(initialState).result
  const terminals = settled.terminals.map(normalizeTerminal)
  if (settled.status === 'failed') {
    assert(settled.failure.detail?.type === 'unknown_action', 'S08 requires unknown_action detail')
    const names = new Map(compiled.describe().elements.map((element) => [element.element_id, element.name]))
    const source = settled.failure.elementId === null ? undefined : names.get(settled.failure.elementId)
    assert(source !== undefined, 'failed source element must be described')
    let runProjection: Record<string, unknown> | undefined
    try {
      await compiled.run(initialState)
    } catch (error) {
      assert(error instanceof RunError, 'failed run projection must throw RunError')
      runProjection = {
        type: 'throw',
        error: {
          name: error.name,
          message: error.message,
          result_status: error.result.status,
        },
      }
    }
    assert(runProjection !== undefined, 'failed run projection did not throw')
    const failedRecord: Record<string, unknown> = {
      id: fixture.id,
      result: {
        status: 'failed',
        state: settled.state,
        terminals,
        failure: {
          kind: settled.failure.kind,
          action: settled.failure.detail.action,
          source,
        },
      },
      run_projection: runProjection,
    }
    if (fixture.id === 'S13_atomic_batch_rejection') {
      delete failedRecord.run_projection
      failedRecord.stats = {
        activations: settled.stats.activations,
        attempts: settled.stats.attempts,
        transitions: settled.stats.transitions,
        retries: settled.stats.retries,
        reports: settled.stats.reports,
        scopes: settled.stats.scopes,
        peak_ready: settled.stats.peakReady,
        peak_callbacks: settled.stats.peakCallbacks,
      }
    }
    fixtures.push(failedRecord)
    continue
  }
  const result: Record<string, unknown> = {
    id: fixture.id,
    result: {
      status: 'completed',
      state: settled.state,
      terminals,
      terminal_outputs: terminals.filter((terminal) => terminal.has_output).map((terminal) => terminal.output),
    },
  }
  if (Object.hasOwn(fixture.expect, 'initial_state_after')) result.initial_state_after = initialState
  fixtures.push(result)
}
console.log(JSON.stringify(canonicalize({ fixtures })))

function normalizeTerminal(terminal: Terminal): Record<string, unknown> {
  const result: Record<string, unknown> =
    terminal.type === 'end'
      ? { type: 'end', has_output: terminal.hasOutput }
      : { type: 'exit', action: terminal.action, has_output: true }
  if (terminal.hasOutput) result.output = normalize(terminal.output)
  return result
}

function normalize(value: unknown): unknown {
  if (value === undefined) return { $host: 'missing' }
  if (Array.isArray(value)) return value.map(normalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, normalize(entry)]))
  }
  return value
}

function readPath(value: unknown, path: string[]): unknown {
  let current = value
  for (const key of path) {
    assert(current !== null && typeof current === 'object' && !Array.isArray(current), 'fixture path must reference a record')
    current = (current as Record<string, unknown>)[key]
  }
  return current
}

function setPath(state: Record<string, unknown>, path: string[], value: unknown): void {
  assert(path.length > 0, 'state path cannot be empty')
  let current = state
  for (const key of path.slice(0, -1)) {
    let child = current[key]
    if (child === null || typeof child !== 'object' || Array.isArray(child)) {
      child = {}
      current[key] = child
    }
    current = child as Record<string, unknown>
  }
  current[path[path.length - 1]!] = value
}

function requireElement(
  elements: Map<string, GraphElement<Record<string, unknown>>>,
  identifier: string,
): GraphElement<Record<string, unknown>> {
  const element = elements.get(identifier)
  assert(element !== undefined, `unknown fixture element ${identifier}`)
  return element
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, canonicalize(entry)]),
    )
  }
  return value
}
