import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Flow, node } from '../typescript/caskada.ts'

import type { Context, GraphElement, RunResult } from '../typescript/caskada.ts'

type State = Record<string, unknown>
type Fixture = {
  readonly id: string
  readonly kind: 'node_chain' | 'nested_flows' | 'wide_fanout' | 'concurrent_reuse'
  readonly size: number
  readonly expect: Record<string, unknown>
}

const fixtureUrl = new URL('./fixtures/runtime-scale.json', import.meta.url)
const collection = JSON.parse(await readFile(fixtureUrl, 'utf8')) as {
  readonly schema_version: number
  readonly fixtures: readonly Fixture[]
}
const observed = []
for (const fixture of collection.fixtures) {
  const snapshot = await run(fixture)
  assert.deepEqual(snapshot, fixture.expect, `${fixture.id} mismatch`)
  observed.push({ id: fixture.id, snapshot })
}
process.stdout.write(JSON.stringify(canonicalize({ schema_version: 1, fixtures: observed })) + '\n')

async function run(fixture: Fixture): Promise<Record<string, unknown>> {
  const { kind, size } = fixture
  if (kind === 'node_chain') {
    const handler = (): void => {}
    const nodes = Array.from({ length: size }, (_, index) => node<State>(handler, { name: `node-${index}` }))
    for (let index = 0; index < size - 1; index += 1) nodes[index]!.link(nodes[index + 1]!)
    const result = await new Flow(nodes[0]!).start(
      {},
      {
        maxActivations: size + 1,
        maxAttempts: size,
        maxTransitions: size,
        maxReady: size,
      },
    ).result
    return resultSnapshot(result)
  }
  if (kind === 'nested_flows') {
    let entry: GraphElement<State> = node<State>(() => undefined, { name: 'leaf' })
    for (let index = 0; index < size; index += 1) entry = new Flow(entry, { name: `nested-${index}` })
    const result = await new Flow(entry, { name: 'root' }).start(
      {},
      {
        maxDepth: size + 1,
        maxActivations: size + 2,
        maxAttempts: 1,
        maxTransitions: size * 2 + 1,
      },
    ).result
    return resultSnapshot(result)
  }
  if (kind === 'wide_fanout') {
    const dispatch = node<State>(
      (context) => {
        for (let index = 0; index < size; index += 1) context.emit('work', index)
      },
      { name: 'dispatch' },
    )
    const work = node<State, number>((context) => context.end(context.input), { name: 'work' })
    dispatch.link(work, 'work')
    const result = await new Flow(dispatch).start(
      {},
      {
        maxActivations: size + 2,
        maxAttempts: size + 1,
        maxTransitions: size * 2,
        maxReady: size,
      },
    ).result
    return {
      ...resultSnapshot(result),
      first_output: result.terminals[0]!.output,
      last_output: result.terminals.at(-1)!.output,
    }
  }
  const work = node<State>(
    async (context) => {
      await Promise.resolve()
      context.state.value = context.state.seed
    },
    { name: 'work' },
  )
  const compiled = new Flow(work).compile()
  const states = await Promise.all(Array.from({ length: size }, (_, index) => compiled.run({ seed: index })))
  return {
    runs: states.length,
    unique_state_carriers: new Set(states).size,
    first_value: states[0]!.value,
    last_value: states.at(-1)!.value,
  }
}

function resultSnapshot(result: RunResult<State>): Record<string, unknown> {
  return {
    status: result.status,
    activations: result.stats.activations,
    attempts: result.stats.attempts,
    transitions: result.stats.transitions,
    scopes: result.stats.scopes,
    peak_ready: result.stats.peakReady,
    terminal_count: result.terminals.length,
  }
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, canonicalize(entry)]),
    )
  }
  return value
}
