---
title: Sley
machine-display: false
---

# Sley

Sley is a structured graph runtime for Python and TypeScript. It runs
ordinary functions as nodes in nested directed graphs and stays independent of
LLM providers, databases, web frameworks, and application schemas.

A sley is the moving loom frame that carries the reed, keeps warp threads
separated, and advances the fabric. To sley also means threading the warp in a
prescribed pattern: the graph defines that pattern, branches and state are its
threads, and a completed run is the woven result.

## What It Provides

- Function-backed nodes and explicit directed links
- Named routing, loops, atomic fan-out, and hard branch termination
- Structured Flow scopes with one synchronization point for aggregation
- One run-wide state map plus per-branch input and terminal output
- Retry and recovery policies, local concurrency, and activation limits
- Typed completed and failed results with settled terminal records
- Equivalent Python and TypeScript behavior

## The Small Model

1. A `node(handler)` performs one unit of work.
2. `context.state` holds facts shared across the run.
3. `context.input` carries the value for one branch.
4. `context.emit(...)` selects what runs next.
5. `context.end(...)` hard-terminates one branch.
6. A `Flow` owns a structured scope and may `combine` its settled branches.
7. `run(initial_state)` returns the completed state; `start(initial_state)`
   exposes the full completed or failed result.

Sley validates its graph and control protocol. Application data keeps normal
host-language behavior: static types can describe it, but runtime schema
validation remains application code.

## Continue

- [Install Sley](installation.md)
- [Build your first Flow](getting_started.md)
- [Understand the core model](core_abstraction/index.md)
- [Browse complete examples](../cookbook/)
