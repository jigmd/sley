# TypeScript API

The package provides ESM, CommonJS, and declaration exports. The normative
cross-language contract is
[RFC 0001](../internal/rfcs/0001-caskada-v3-runtime.md).

## Graph Definition

```typescript
function node<State extends object, Input = unknown>(
  handler: NodeHandler<State, Input>,
  options?: NodeOptions<State, Input>,
): Node<State>
```

```typescript
interface NodeOptions<State extends object, Input> {
  readonly name?: string | undefined
  readonly retry?: RetryOptions | undefined
  readonly timeoutMs?: number | undefined
  readonly recover?: NodeRecoveryHandler<State, Input> | undefined
}
```

Handlers and recovery callbacks may be synchronous or asynchronous and must
return `undefined`. `Node` is final and created only through `node(...)`.

```typescript
abstract class GraphElement<State extends object> {
  readonly name: string
  link(target: GraphElement<State>, action?: Action): void
  links(): readonly Link<State>[]
}
```

```typescript
class Flow<State extends object> extends GraphElement<State> {
  constructor(entry: GraphElement<State>, options?: FlowOptions<State>)
  compile(): CompiledFlow<State>
  start(initialState: Readonly<State>, options?: RunOptions): RunHandle<State>
  run(initialState: Readonly<State>, options?: RunOptions): Promise<State>
}
```

`FlowOptions` provides `name`, declared `exits`, local `concurrency`, local
`maxActivations`, `combine`, and `recover`.

## Context

```typescript
interface Context<State extends object, Input = unknown> {
  readonly state: State
  readonly input: Input
  readonly runId: string
  readonly scopeId: number
  readonly activationId: number
  readonly parentActivationId: number | null
  readonly attempt: number | null
  readonly phase: Phase
  readonly cancellation: Cancellation

  remainingMs(): number | undefined
  emit(): void
  emit(replacement: { readonly input: unknown }): void
  emit(action: Action): void
  emit(action: Action, input: unknown): void
  end(): void
  end(output: unknown): void
  report(name: string): void
  report(name: string, data: unknown): void
}
```

Arity matters: omitted input/output/data differs from explicit `undefined`.
Unlabelled input replacement uses `emit({ input: value })`; named input is
direct: `emit('work', value)`.

`Cancellation` exposes `cancelled`, `reason`, an `AbortSignal`, and
`throwIfCancelled()`.

## Execution

```typescript
interface RunHandle<State extends object> {
  readonly done: boolean
  readonly result: Promise<RunResult<State>>
  cancel(reason?: unknown): void
}
```

```typescript
interface RunOptions {
  readonly maxConcurrency?: number | undefined
  readonly maxActivations?: number | undefined
  readonly maxAttempts?: number | undefined
  readonly maxTransitions?: number | undefined
  readonly maxReady?: number | undefined
  readonly maxReports?: number | undefined
  readonly maxDepth?: number | undefined
  readonly deadlineMs?: number | undefined
  readonly cancelGraceMs?: number | undefined
  readonly observer?: Observer | undefined
  readonly runId?: string | undefined
}
```

Omitted numeric fields use the portable defaults. Omitted `maxConcurrency`
selects the topology-derived automatic ceiling.

`CompiledFlow.describe()` returns the portable compiled graph description.
`CompiledFlow.start()` and `.run()` reuse the snapshot.

## Results And Failures

`RunResult<State>` is a discriminated union of `CompletedResult`,
`FailedResult`, `CancelledResult`, and `AbandonedResult`. Every variant exposes
`state`, terminals, statistics, and observer diagnostics. Failure-like variants
add their structured cause and suppressed failures.

`RunError.result` retains the exact non-completed result raised by `run()`. If a
native thrown value caused the controlling Failure, `RunError.cause` is that
exact value.

`ScopeResult` exposes `terminals` and `outputs`. `ScopeFailure` provides boundary
recovery information. `Failure` carries identity, kind, canonical message,
cause, provenance, detail, and previous replacement.

## Events And Logging

`Observer` synchronously receives the `RunEvent` discriminated union. The event
kinds and schema match the [Python API](../python/api.md). Application values in
causes, reasons, inputs, outputs, state, and reports remain borrowed values.

The browser-safe logging adapter is a separate export:

```typescript
import { createLoggingObserver } from 'caskada/logging'
```

## Errors

- `GraphDefinitionError`: invalid graph definition or callback configuration
- `DuplicateLinkError`: duplicate unlabelled or named link
- `OptionValidationError`: invalid run options or initial state capture
- `RunError`: a completed handle whose result is not `Completed`

## Constants

- `MAX_SAFE_INTEGER`
- `MAX_PORTABLE_COLLECTION_LENGTH`
- `RUN_EVENT_SCHEMA_VERSION`
