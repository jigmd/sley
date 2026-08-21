import { readFileSync } from 'node:fs'
import { canonicalize, evaluateEventsReportsLimits } from './events-reports-limits-reference.mts'

const FIXTURE_PATH = new URL('./fixtures/events-reports-limits.json', import.meta.url)
const collection = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8')) as {
  readonly fixtures: ReadonlyArray<{
    readonly id: string
    readonly program: { readonly scenario: string }
    readonly expect: unknown
  }>
}
const fixtures = collection.fixtures.map((fixture) => {
  const snapshot = evaluateEventsReportsLimits(fixture.program.scenario)
  if (JSON.stringify(canonicalize(snapshot)) !== JSON.stringify(canonicalize(fixture.expect))) {
    throw new Error(`${fixture.id} reference mismatch`)
  }
  return { id: fixture.id, snapshot }
})
process.stdout.write(JSON.stringify(canonicalize({ schema_version: 1, fixtures })) + '\n')
