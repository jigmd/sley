---
machine-display: false
---

# Limits and Concurrency

Caskada limits workflow scheduling. Provider quotas and application resource
limits remain application concerns.

## Local Flow Concurrency

`Flow(..., concurrency=N)` limits the number of direct child activations that
the Flow scope may run at once. A nested Flow owns its own scope and local limit.

```python
workers = Flow(dispatch, concurrency=8, combine=collect)
```

```typescript
const workers = new Flow(dispatch, { concurrency: 8, combine: collect })
```

Fan-out does not require a special parallel Flow type. Several buffered
`emit(...)` calls create branches; the scheduler applies the Flow's local cap.

## Run-Wide Concurrency

`RunOptions.max_concurrency` / `maxConcurrency` is the global callback ceiling.
When omitted, Caskada derives the ceiling from the maximum local Flow
concurrency in the compiled graph. An explicit value may throttle below that
number or permit more aggregate work across separate scopes.

Local caps still apply when the run-wide ceiling is higher.

```python
final_state = await flow.run(
    initial_state,
    options=RunOptions(max_concurrency=4),
)
```

```typescript
const finalState = await flow.run(initialState, { maxConcurrency: 4 })
```

Use `flow.compile().describe()["auto_max_concurrency"]` in Python or
`flow.compile().describe().auto_max_concurrency` in TypeScript to inspect the
derived default.

## Work Limits

RunOptions provides portable run-wide bounds:

| Python            | TypeScript       | Bounds                       |
| ----------------- | ---------------- | ---------------------------- |
| `max_activations` | `maxActivations` | admitted graph activations   |
| `max_attempts`    | `maxAttempts`    | admitted handler attempts    |
| `max_transitions` | `maxTransitions` | committed control arms       |
| `max_ready`       | `maxReady`       | queued ready work            |
| `max_reports`     | `maxReports`     | accepted application reports |
| `max_depth`       | `maxDepth`       | active nested Flow depth     |

A Flow may also set `max_activations` / `maxActivations` for direct activations
inside each invocation of that scope. Use it for a deliberate local loop bound.
It does not count descendants or retry attempts.

Limit exhaustion becomes a structured unrecoverable `limit` Failure in the run
result. It is not an application exception from the handler.

## Deadlines and Cancellation

Use `deadline_ms` / `deadlineMs` for a run deadline and
`cancel_grace_ms` / `cancelGraceMs` for cooperative shutdown grace. A node may
also have `timeout_ms` / `timeoutMs`.

Handlers can inspect `context.remaining_ms()` / `remainingMs()` and the
cancellation token. Long loops should checkpoint cancellation between units of
work.

Runtime timers can signal async work, but they cannot preempt synchronous
blocking code. Prefer:

1. native async clients with their own request timeout;
2. cancellation-aware library calls;
3. deliberate thread or process isolation when no async client exists.

Thread offload keeps the scheduler responsive but cannot kill the underlying
thread. The provider timeout remains necessary.

## Provider Rate Limits

Flow concurrency controls simultaneous Caskada callbacks, not requests made
inside one callback and not quotas shared with other processes. Put a limiter in
the injected service client when several workflows share a provider:

```python
async def call_model(prompt):
    async with provider_limiter:
        return await client.generate(prompt, timeout=30)
```

Keep retry ownership clear. Use a provider client's retry policy for transport
details, or Caskada's node retry for the whole application operation. Stacking
both without explicit bounds can multiply attempts and latency.

## Choosing Values

Start with each Flow at concurrency 1. Raise the cap only where branches are
independent and the downstream service can absorb the load. Set explicit
run-wide work budgets for cycles and dynamic fan-out, and use a deadline for a
wall-clock bound.

Measure peak callbacks and terminal behavior through `start()` results and
events before increasing limits.
