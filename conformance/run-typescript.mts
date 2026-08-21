import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { canonicalize, ReferenceInterpreter } from './reference.mts'

type Fixture = {
  id: string
  program: ConstructorParameters<typeof ReferenceInterpreter>[0]
  expect: Record<string, unknown>
}

const fixtureUrl = new URL('./fixtures/serial.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as {
  schema_version: number
  fixtures: Fixture[]
}
assert.equal(collection.schema_version, 1, 'unsupported fixture schema')

const fixtureIds = new Set<string>()
const observed: Array<{ id: string; snapshot: Record<string, unknown> }> = []
for (const fixture of collection.fixtures) {
  assert(!fixtureIds.has(fixture.id), `duplicate fixture ID ${fixture.id}`)
  fixtureIds.add(fixture.id)

  const actual = new ReferenceInterpreter(fixture.program).run()
  const selected = Object.fromEntries(Object.keys(fixture.expect).map((key) => [key, actual[key]]))
  assert.deepEqual(selected, fixture.expect, `${fixture.id} mismatch`)
  observed.push({ id: fixture.id, snapshot: selected })
}

console.log(JSON.stringify(canonicalize({ schema_version: 1, fixtures: observed })))
