import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Flow, node } from '../typescript/caskada.ts'

import type { GraphElement } from '../typescript/caskada.ts'

type Fixture = {
  id: string
  kind: 'node_chain' | 'nested_flows'
  size: number
  expect: { elements: number; scopes: number; last_element_id: number }
}

const fixtureUrl = new URL('./fixtures/compile-scale.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as {
  schema_version: number
  fixtures: Fixture[]
}
const observed: Array<{ id: string; snapshot: Fixture['expect'] }> = []
for (const fixture of collection.fixtures) {
  const snapshot = run(fixture)
  assert.deepEqual(snapshot, fixture.expect, `${fixture.id} mismatch`)
  observed.push({ id: fixture.id, snapshot })
}
console.log(JSON.stringify(canonicalize({ schema_version: 1, fixtures: observed })))

function run(fixture: Fixture): Fixture['expect'] {
  let root: Flow<Record<string, unknown>>
  if (fixture.kind === 'node_chain') {
    const nodes = Array.from({ length: fixture.size }, (_, index) => node(() => {}, { name: `node-${index}` }))
    for (let index = 0; index < fixture.size - 1; index += 1) nodes[index]!.link(nodes[index + 1]!)
    root = new Flow(nodes[0]!, { name: 'root' })
  } else {
    let entry: GraphElement<Record<string, unknown>> = node(() => {}, { name: 'leaf' })
    for (let index = 0; index < fixture.size; index += 1) {
      entry = new Flow(entry, { name: `nested-${index}` })
    }
    root = new Flow(entry, { name: 'root' })
  }

  const description = root.compile().describe()
  return {
    elements: description.elements.length,
    scopes: description.scope_definitions.length,
    last_element_id: description.elements.at(-1)!.element_id,
  }
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
