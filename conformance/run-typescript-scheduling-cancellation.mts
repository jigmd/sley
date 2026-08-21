import { readFileSync } from 'node:fs'
import { canonicalize, evaluateSchedulingCancellation } from './scheduling-cancellation-reference.mts'

const FIXTURE_PATH = new URL('./fixtures/scheduling-cancellation.json', import.meta.url)
const collection = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8')) as {
  readonly fixtures: ReadonlyArray<{
    readonly id: string
    readonly program: { readonly scenario: string; readonly width?: number; readonly max_concurrency?: number }
    readonly expect: unknown
  }>
}
const fixtures = collection.fixtures.map((fixture) => {
  const snapshot = evaluateSchedulingCancellation(fixture.program)
  if (JSON.stringify(canonicalize(snapshot)) !== JSON.stringify(canonicalize(fixture.expect))) {
    throw new Error(`${fixture.id} reference mismatch`)
  }
  return { id: fixture.id, snapshot }
})
process.stdout.write(JSON.stringify(canonicalize({ schema_version: 1, fixtures })) + '\n')
