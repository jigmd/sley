# Python Runtime Design

The Python port is six production files:

- `__init__.py` declares the public facade;
- `_contracts.py` holds public values and callback protocols;
- `_graph.py` builds and snapshots graphs;
- `_context.py` validates callback control and buffers intents;
- `_state.py` validates and shallow-copies initial state;
- `_runner.py` executes activations and Flow scopes.

Definitions contain callbacks, policies, and links but no run state. Compilation
assigns placement ids and snapshots every reachable scope. Each invocation owns
one state dictionary plus simple counters for scopes, activations, failures, and
terminal order.

The scheduler uses `asyncio.gather` in batches bounded by the current Flow's
`concurrency`. Serial Flows therefore use the same path as concurrent ones.
Nested Flows call the same scope executor with their compiled scope id. Cyclic
node links remain iterative; only Flow nesting consumes the Python call stack.

A callback-local Context buffers `emit` and `end` intents. The runner validates
the complete buffer before routing it, so a throw or one unknown action commits
no partial fan-out. State writes and external effects are ordinary application
effects and are not rolled back.

The runtime catches ordinary application exceptions only at handler, policy,
combine, and recovery boundaries. Native `BaseException` subclasses, including
task cancellation, keep native behavior. Impossible compiled states raise
immediately instead of being converted into graceful fallback results.

The authoritative behavior is
[RFC 0001](../architecture/rfcs/0001-caskada-v3-runtime.md).
