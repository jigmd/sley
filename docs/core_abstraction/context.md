# Context

Every handler, recovery callback, and Flow callback receives a runtime-issued
Context. It is valid only while that callback is active.

## Data

- `context.state`: the run-owned shared state carrier
- `context.input`: the value carried by this activation

The Context object is callback-scoped. An alias obtained from `context.state`
is the persistent state carrier and remains usable; the Context itself closes
when the callback settles.

## Emit

`emit` appends one outward route intent.

| Meaning                           | Python                          | TypeScript                       |
| --------------------------------- | ------------------------------- | -------------------------------- |
| Unlabelled, forward current input | `context.emit()`                | `context.emit()`                 |
| Unlabelled, replace input         | `context.emit(input=value)`     | `context.emit(undefined, value)` |
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
