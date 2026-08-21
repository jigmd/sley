# TypeScript Runtime Design

The TypeScript port is five production files:

- `caskada.ts` declares the public facade;
- `internal/contracts.ts` holds public values and callback types;
- `internal/definition.ts` builds and snapshots graphs;
- `internal/state.ts` validates and shallow-copies initial state;
- `internal/scheduling.ts` executes activations and Flow scopes.

Definitions contain callbacks, policies, and links but no run state. Compilation
assigns placement ids and snapshots every reachable scope. Each invocation owns
one state object plus simple counters for scopes, activations, failures, and
terminal order.

The scheduler uses native Promises and `Promise.all` batches bounded by the
current Flow's `concurrency`. Serial Flows use the same path as concurrent ones.
Nested Flows call the same scope executor with their compiled scope id. Cyclic
node links remain iterative; only Flow nesting consumes the JavaScript stack.

A callback-local Context buffers `emit` and `end` intents. The runner validates
the complete buffer before routing it, so a throw or one unknown action commits
no partial fan-out. State writes and external effects are ordinary application
effects and are not rolled back.

`run()` briefly masks a state object's own `then` property while resolving its
Promise. This preserves state identity without turning application state into a
thenable. No Proxy wraps normal object behavior.

Application throws are caught only at handler, policy, combine, and recovery
boundaries. Impossible compiled states reject immediately instead of becoming
fallback workflow outcomes. The core has no Node.js imports and remains browser
compatible.

The authoritative behavior is
[RFC 0001](../internal/rfcs/0001-caskada-v3-runtime.md).
