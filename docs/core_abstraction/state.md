# State, Input, And Output

Caskada separates application data into three roles.

| Role                 | Surface                           | Lifetime                     |
| -------------------- | --------------------------------- | ---------------------------- |
| Shared facts         | `context.state`                   | Entire run                   |
| Branch message       | `context.input`                   | One activation lineage       |
| Settled branch value | `context.end(value)` or Flow exit | Collected by a Flow boundary |

## State Ownership

`run(initial_state)` and `start(initial_state)` shallow-copy the caller's
top-level mapping into one fresh run-owned state carrier. Every branch and
nested Flow in that run sees the same carrier.

```python
initial = {"count": 0, "settings": settings}
final = await flow.run(initial)

assert initial["count"] == 0
assert final["count"] >= 0
assert final["settings"] is settings
```

The final result exposes that same carrier; Caskada does not make another copy
at settlement. Retained aliases remain live references, not snapshots.

Top-level state supports normal record operations. Python uses a dict carrier;
TypeScript uses a guarded object proxy. State keys must be ordinary strings and
properties must remain data properties.

## Shared-State Concurrency

Parallel branches share state. Conflicting reads and writes therefore have the
same race concerns as any concurrent application code. Prefer disjoint keys,
immutable values, synchronization in injected services, or branch outputs plus
a Flow combiner.

The shallow boundary does not isolate nested objects. If two inputs or branches
share a mutable list, object, client, or index, they share that reference.

## Branch Input

Input is a read-only binding; the referenced value is not frozen or copied.
Omitting a new input from `emit` forwards the current input by identity.

```python
for document in context.state["documents"]:
    context.emit("embed", document)


@node
def embed(context: Context[State, Document]) -> None:
    vector = model.embed(context.input["text"])
    context.end(vector)
```

Python's optional second `Context` type and TypeScript's second `Context`/
`node` generic describe one handler's expected input. They do not prove that a
predecessor emits the matching shape.

## Host-Language Data Semantics

Caskada validates its own state container and control protocol, not application
schemas.

- Python `context.state["missing"]` raises `KeyError`; uncaught callback errors
  become handler failures.
- TypeScript `context.state.missing` normally evaluates to `undefined`.
- Static types find many mistakes but do not validate dynamic data.

Validate untrusted or phase-specific data before state writes and external
effects:

```python
def work(context):
    job = parse_job(context.input)
    result = process(job)
    context.state["result"] = result
```

An ordinary preparation node is useful when validation should be visible in
the graph.
