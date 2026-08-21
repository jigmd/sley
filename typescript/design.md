# TypeScript Runtime Design

The TypeScript port implements the language-neutral v3 contract in the public
`caskada.ts` entry point. `caskada-logging.ts` is an optional browser-safe event
adapter.

## Definition Layer

`node(...)`, `Node`, `Flow`, and `GraphElement.link(...)` capture callback
configuration and topology without host-framework dependencies. Node and Flow
state generics describe application record shapes; they do not preserve the
caller container's concrete class.

`compile()` validates definitions and creates a reusable deterministic snapshot.
WeakMap-owned private data prevents invalid public construction from becoming a
partially initialized runtime object.

## State Carrier

Each run shallow-copies initial state into one ordinary object. Every callback
and result sees that same object, whose reads and mutations follow JavaScript
rules.

`run()` uses a final native Promise capability and briefly masks the private
state object's `then` binding while resolving. This preserves exact state identity
even when application state legitimately contains a callable `then` property.

## Scheduler

The runtime uses iterative scope and callback queues. Scope-local concurrency
limits direct activations; a run-wide permit ceiling controls callbacks across
scopes. Callback admission, timer checkpoints, result settlement, control
linearization, and event publication follow the same ordering as the Python
port.

Callbacks may return `undefined` or `Promise<void>`. Synchronous work remains
synchronous and cannot be preempted by timers or `AbortSignal` cancellation.

## Portability

The core and logging adapter avoid Node.js runtime imports and are browser
compatible. Public integer and collection bounds are chosen for exact Python/
JavaScript representation. Host-specific naming follows language convention;
schemas and behavior remain equivalent.

The authoritative algorithm, failure provenance, timer tie rules, event order,
and complexity bounds live in
[RFC 0001](../internal/rfcs/0001-caskada-v3-runtime.md).
