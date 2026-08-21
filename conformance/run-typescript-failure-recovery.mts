import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { canonicalize, evaluateFailureRecovery } from './failure-recovery-reference.mts'

import type { FailureRecoveryProgram } from './failure-recovery-reference.mts'

type Fixture = {
  id: string
  program: FailureRecoveryProgram
  expect: Record<string, unknown>
}

const fixtureUrl = new URL('./fixtures/failure-recovery.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as { schema_version: number; fixtures: Fixture[] }
assert.equal(collection.schema_version, 1, 'unsupported failure fixture schema')

const fixtureIds = new Set<string>()
const observed: Array<{ id: string; snapshot: Record<string, unknown> }> = []
for (const fixture of collection.fixtures) {
  assert(!fixtureIds.has(fixture.id), `duplicate fixture ID ${fixture.id}`)
  fixtureIds.add(fixture.id)
  const actual = evaluateFailureRecovery(fixture.program)
  assert.deepEqual(actual, fixture.expect, `${fixture.id} mismatch`)
  observed.push({ id: fixture.id, snapshot: actual })
}

console.log(JSON.stringify(canonicalize({ schema_version: 1, fixtures: observed })))
