# Python Runtime Design

The Python port implements the language-neutral v3 contract in the public
`caskada` package plus the optional `caskada_logging` adapter package. Both
packages publish their inline types through PEP 561 markers.

## Definition Layer

`node(...)`, `Node`, `Flow`, and `GraphElement.link(...)` build immutable
callback configuration and mutable definition topology. A Node is a final,
runtime-created occurrence rather than a subclass extension point.

`compile()` performs deterministic breadth-first validation and produces a
snapshot that can be reused by concurrent runs. Runtime execution never reads
later definition mutations.

## Runtime Layer

Each invocation owns:

- one shallow-copied dict-compatible state carrier;
- scope, activation, callback, timer, and ready-queue records;
- failure packets and cancellation fences;
- an event publisher, counters, diagnostics, and final result.

Callbacks run through a guarded handoff after admission. A callback-local
Context buffers control intents and reports identity, deadlines, and
cancellation. The state carrier itself persists beyond callback settlement;
Context methods do not.

## Scheduler

The scheduler uses explicit queues and iterative scope processing rather than
recursive graph execution. Scope-local concurrency limits direct activations;
one run-wide permit ceiling controls callback admission across scopes. Nested
Flow creation is permit-free but still bounded by ready, depth, activation, and
scope-local limits.

All user callbacks may be synchronous or awaitable. Python catch boundaries use
`BaseException` so every admitted lifecycle wrapper settles exactly once;
token-correlated `asyncio.CancelledError` is the only cooperative cancellation
special case.

## Results And Observation

Control facts commit before synchronous observation. Observer errors become
diagnostics and never replace workflow outcomes. Public result and identity
objects have bounded representations and identity semantics where the
cross-language contract requires them.

The authoritative algorithm, tie rules, resource bounds, failure provenance,
and event ordering live in
[RFC 0001](../internal/rfcs/0001-caskada-v3-runtime.md).
