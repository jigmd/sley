import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Flow, node } from '../typescript/caskada.ts'

import type { GraphElement } from '../typescript/caskada.ts'

type ElementDefinition =
  | { kind: 'node' }
  | {
      kind: 'flow'
      entry: string
      exits?: string[]
      concurrency?: number
      max_activations?: number
    }

type Program = {
  root: string
  elements: Record<string, ElementDefinition>
  links: Array<{ source: string; target: string; action?: string }>
}

const fixtureUrl = new URL('./fixtures/serial.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as {
  fixtures: Array<{ id: string; program: Program; expect: { compiled?: unknown } }>
}
const fixture = collection.fixtures.find((item) => item.id === 'S00_compile_nested')
assert(fixture !== undefined)
const root = build(fixture.program)
const actual = root.compile().describe()
assert.deepEqual(actual, fixture.expect.compiled, 'S00_compile_nested production mismatch')
console.log(JSON.stringify(canonicalize(actual)))

function build(program: Program): Flow<Record<string, unknown>> {
  const elements = new Map<string, GraphElement<Record<string, unknown>>>()
  const unresolved = new Map<string, Extract<ElementDefinition, { kind: 'flow' }>>()
  for (const [identifier, definition] of Object.entries(program.elements)) {
    if (definition.kind === 'node')
      elements.set(
        identifier,
        node(() => {}, { name: identifier }),
      )
    else unresolved.set(identifier, definition)
  }

  while (unresolved.size > 0) {
    let progressed = false
    for (const [identifier, definition] of Array.from(unresolved)) {
      const entry = elements.get(definition.entry)
      if (entry === undefined) continue
      elements.set(
        identifier,
        new Flow(entry, {
          name: identifier,
          exits: definition.exits,
          concurrency: definition.concurrency,
          maxActivations: definition.max_activations,
        }),
      )
      unresolved.delete(identifier)
      progressed = true
    }
    assert(progressed, 'fixture Flow entries contain an unresolved cycle')
  }

  for (const link of program.links) {
    const source = requireElement(elements, link.source)
    const target = requireElement(elements, link.target)
    if (link.action === undefined) source.link(target)
    else source.link(target, link.action)
  }
  const root = requireElement(elements, program.root)
  assert(root instanceof Flow, 'fixture root must be a Flow')
  return root
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
