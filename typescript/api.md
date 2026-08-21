# TypeScript API

The package provides ESM, CommonJS, and declarations. The normative contract is
[RFC 0001](../internal/rfcs/0001-caskada-v3-runtime.md).

## Graphs

```typescript
function node<State extends object, Input = unknown>(
  handler: NodeHandler<State, Input>,
  options?: NodeOptions<State, Input>,
): Node<State, Input>
```

`NodeOptions` contains only `name`, `retry`, and `recover`. Handlers and recovery
callbacks may be synchronous or asynchronous and return `undefined`.

```typescript
interface RetryPolicy {
  readonly maxAttempts?: number
  readonly shouldRetry?: (failure: Failure) => boolean
  readonly delayMs?: number | ((attempt: number, failure: Failure) => number)
}
```

Every Node and Flow is a `GraphElement`:

```typescript
source.link(target)
source.link(target, 'review')
source.links()
```

A source has at most one unlabelled link and one link per named action.

```typescript
new Flow(entry, {
  name?: string,
  exits?: readonly string[],
  concurrency?: number,
  maxActivations?: number,
  combine?: FlowCombineHandler,
  recover?: FlowRecoveryHandler,
})
```

Flows may be nested and linked like Nodes. `compile()` snapshots reachable
topology. `CompiledFlow.describe()` returns plain topology and policy records.

## Context

```typescript
interface Context<State extends object, Input = unknown> {
  readonly state: State
  readonly input: Input

  emit(): void
  emit(action: undefined, input: unknown): void
  emit(action: string): void
  emit(action: string, input: unknown): void
  end(): void
  end(output: unknown): void
}
```

`state` is one shallow-copied object shared by the run. `input` is one branch
message. Omitted emission input forwards the current input. Use
`emit(undefined, value)` to replace input on an unlabelled route. `end()` and
`end(undefined)` differ: the first has no output and the second outputs
`undefined`.

## Execution

```typescript
const compiled = flow.compile()
const handle = compiled.start(initialState)
const result = await handle.result()
const state = await compiled.run(initialState)
```

A handle has only `done()` and `result()`. `run()` returns state for `Completed`
and rejects with `RunError` containing the exact `Failed` result otherwise.

`RunResult<State>` has two variants:

```text
Completed { status: 'completed', state, terminals }
Failed    { status: 'failed', state, terminals, failure }
```

`ScopeResult.terminals` contains all settled branch terminals.
`ScopeResult.outputs` projects only output-bearing values for `combine`.
`ScopeFailure` gives Flow recovery the primary Failure, settled terminals, an
optional failed combine result, and the failing activation id.

## Errors

- `GraphDefinitionError`: invalid definition or callback policy
- `DuplicateLinkError`: duplicate unlabelled or named link
- `RunError`: unhandled workflow failure projected by `run()`
- `TypeError`: invalid initial state carrier

Application throws become `Failure` records for retry and recovery. Their
original values remain available as `failure.cause`.
