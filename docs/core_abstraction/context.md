# Context

Every handler, recovery callback, and Flow callback receives a runtime-issued
Context. It is valid only while that callback is active.

## Data

- `context.state`: the run-owned shared state carrier
- `context.input`: the value carried by this activation

The Context object is callback-scoped. An alias obtained from `context.state`
is the persistent state carrier and remains usable; the Context itself and its
control, report, cancellation, and metadata access close at settlement.

## Emit

`emit` appends one outward route intent.

| Meaning                           | Python                          | TypeScript                       |
| --------------------------------- | ------------------------------- | -------------------------------- |
| Unlabelled, forward current input | `context.emit()`                | `context.emit()`                 |
| Unlabelled, replace input         | `context.emit(input=value)`     | `context.emit({ input: value })` |
| Named, forward current input      | `context.emit("review")`        | `context.emit('review')`         |
| Named, replace input              | `context.emit("review", value)` | `context.emit('review', value)`  |

An action is a nonempty string. It first resolves against the current graph
element's links, then against the owning Flow's declared exits. An unresolved
named action fails with `unknown_action`.

## End

`end` appends one hard terminal intent. It bypasses normal links and ends only
the current branch.

```python
context.end()       # End with no output
context.end(None)   # End with one explicit None output
```

```typescript
context.end() // End with no output
context.end(undefined) // End with one explicit undefined output
```

The call does not return from the handler:

```python
context.end()
return  # Ordinary language control keeps later statements from running.
```

Several `emit` and `end` calls may intentionally create several fan-out arms.

## Cancellation And Deadlines

- `context.cancellation.cancelled` reports whether work is fenced.
- Python `await context.cancellation.wait()` waits for cancellation.
- Python `raise_if_cancelled()` and TypeScript `throwIfCancelled()` provide an
  explicit cooperative checkpoint.
- `remaining_ms()` / `remainingMs()` returns the nearest applicable work or
  grace deadline while the Context is live.

Caskada cannot preempt synchronous blocking application code. Use asynchronous
clients, provider timeouts, and cooperative checkpoints for long operations.

## Reports And Identity

`report(name)` or `report(name, data)` publishes an application progress event
to the run observer. The name must be a nonempty string. Omitted data remains
distinguishable from explicit `None`/`undefined`.

Context also exposes run, scope, activation, parent activation, attempt, and
phase identity. Python uses snake case; TypeScript uses camel case.
