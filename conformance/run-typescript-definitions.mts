import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Flow, node } from '../typescript/caskada.ts'

import type { GraphElement, Node } from '../typescript/caskada.ts'

type DefinitionFixture = {
  id: string
  nodes: Array<{
    id: string
    handler_name: string
    options?: {
      name?: string
      retry?: { max_attempts?: number; delay_ms?: number }
      timeout_ms?: number
    }
  }>
  flow: {
    entry: string
    name?: string
    exits?: string[]
    concurrency?: number
    max_activations?: number
  }
  links: Array<{ source: string; target: string; action?: string }>
  expect: Record<string, unknown>
}

const fixtureUrl = new URL('./fixtures/definitions.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as {
  schema_version: number
  fixtures: DefinitionFixture[]
}

const observed: Array<{ id: string; snapshot: Record<string, unknown> }> = []
for (const fixture of collection.fixtures) {
  const elements = new Map<string, GraphElement<Record<string, unknown>>>()
  const nodes: Array<[string, Node<Record<string, unknown>>]> = []
  for (const definition of fixture.nodes) {
    const callback = (_context: unknown): void => {}
    Object.defineProperty(callback, 'name', { value: definition.handler_name })
    const options = definition.options
    const occurrence = node(callback, {
      name: options?.name,
      retry:
        options?.retry === undefined
          ? undefined
          : {
              maxAttempts: options.retry.max_attempts,
              delayMs: options.retry.delay_ms,
            },
      timeoutMs: options?.timeout_ms,
    })
    elements.set(definition.id, occurrence)
    nodes.push([definition.id, occurrence])
  }

  const flowDefinition = fixture.flow
  const flow = new Flow(requireElement(elements, flowDefinition.entry), {
    name: flowDefinition.name,
    exits: flowDefinition.exits,
    concurrency: flowDefinition.concurrency,
    maxActivations: flowDefinition.max_activations,
  })
  elements.set('$flow', flow)

  for (const link of fixture.links) {
    const source = requireElement(elements, link.source)
    const target = requireElement(elements, link.target)
    if (link.action === undefined) source.link(target)
    else source.link(target, link.action)
  }

  const ids = new Map(Array.from(elements, ([identifier, element]) => [element, identifier]))
  const snapshotLinks = (element: GraphElement<Record<string, unknown>>) =>
    element.links().map((link) => ({ action: link.action, target: ids.get(link.target) }))
  const snapshot = {
    nodes: nodes.map(([id, occurrence]) => ({
      id,
      name: occurrence.name,
      retry: {
        max_attempts: occurrence.retry.maxAttempts,
        delay_ms: occurrence.retry.delayMs,
      },
      timeout_ms: occurrence.timeoutMs ?? null,
      links: snapshotLinks(occurrence),
    })),
    flow: {
      name: flow.name,
      entry: ids.get(flow.entry),
      exits: Array.from(flow.exits),
      concurrency: flow.concurrency,
      max_activations: flow.maxActivations ?? null,
      links: snapshotLinks(flow),
    },
  }
  assert.deepEqual(snapshot, fixture.expect, `${fixture.id} mismatch`)
  observed.push({ id: fixture.id, snapshot })
}

console.log(JSON.stringify(canonicalize({ schema_version: 1, fixtures: observed })))

function requireElement(
  elements: Map<string, GraphElement<Record<string, unknown>>>,
  id: string,
): GraphElement<Record<string, unknown>> {
  const element = elements.get(id)
  assert(element !== undefined, `unknown fixture element ${id}`)
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
