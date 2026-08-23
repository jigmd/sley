---
machine-display: false
---

# Choosing Sley

Sley is a structured graph runtime. It provides graph definition,
branching, nested scopes, local concurrency and limits, retry and recovery, and
structured results. It intentionally does not provide model clients,
vector stores, tool registries, prompt templates, or domain-specific agent
classes.

This is a tradeoff, not a claim that one framework fits every project.

## What Sley Optimizes For

### A Small Authoring Model

Ordinary workflows use:

- function handlers wrapped by `node(...)`;
- target-first `link(...)` topology;
- one shared run state and branch-local input;
- buffered `emit(...)` and `end(...)` control;
- nested Flow boundaries and optional combine callbacks.

The same concepts exist in the Python and TypeScript packages.

### Explicit Control

Links authorize routing. A name with no link or declared Flow exit is an
`unknown_action` failure. Fan-out is visible as several emissions, and fan-in is
visible as a Flow combine callback.

Sley does not infer graph control from model output, object shape, or an
integration wrapper.

### Structured Runtime Semantics

The runtime owns local callback admission, scope quiescence, retry, recovery,
activation bounds, and terminal settlement. `start()` exposes a structured
result rather than using native exceptions as the complete runtime protocol.

### Bring-Your-Own Integrations

Application code calls provider SDKs and databases directly. This avoids a
Sley-specific wrapper layer, but it also means the application owns service
configuration, runtime data validation, rate limiting, and fakes.

## Architectural Tradeoffs

| Choice                      | Benefit                                     | Cost                                                 |
| --------------------------- | ------------------------------------------- | ---------------------------------------------------- |
| Function-first nodes        | Little framework ceremony                   | No lifecycle phase dedicated to validation           |
| One shared run state        | One authoritative result state              | Concurrent writes need application discipline        |
| Branch input and End output | Explicit per-branch data flow               | Connected handlers must agree on payload shape       |
| Buffered control            | Atomic 0/1/N routing                        | `end()` does not stop host-language execution        |
| First-class Flow combine    | Correct structured fan-in                   | Authors must understand terminal replacement         |
| No built-in integrations    | Direct provider APIs and fewer abstractions | Less ready-made ecosystem functionality              |
| Python/TypeScript parity    | Portable workflow semantics                 | Contract follows the smaller common semantic surface |

## Compare Against Your Requirements

When evaluating Sley, LangChain, LangGraph, CrewAI, AutoGen, PocketFlow, or a
custom scheduler, compare the current releases on these questions:

1. **Control:** Is topology explicit, model-directed, or conversation-directed?
2. **State:** Is state shared, copied per branch, immutable, or externally owned?
3. **Fan-in:** Who knows when a dynamic set of branches is complete?
4. **Failure:** Are retry, recovery, and partial results structured data?
5. **Limits:** Which local resources are bounded?
6. **Inspection:** Can graph topology and terminal outcomes be inspected?
7. **Integrations:** Does the framework wrap providers or use their SDKs directly?
8. **Portability:** Are multiple language implementations behaviorally aligned?
9. **Testing:** Can the real graph run with test-owned service fakes?
10. **Operations:** Which timeouts and rate limits remain application concerns?

Product surfaces change frequently. Use each project's current official
documentation rather than codebase-size or feature-count tables.

## Relationship to PocketFlow

Sley began from PocketFlow's graph-oriented minimalism but has a different
authoring and runtime contract. It uses function-first nodes, shared run state,
branch input, buffered emissions, structured Flow combine, local limits, and
cross-language result schemas.

Migration is therefore a design conversion rather than an import rename. See
[Migrating from PocketFlow](./guides/migrating_from_pocketflow.md).

## When Sley Fits

Choose Sley when the workflow graph and its runtime behavior should remain
visible in application code, you want to bring your own integrations, and
Python/TypeScript parity matters.

Prefer a higher-level framework when built-in provider components, opinionated
agent roles, or ecosystem-specific tooling matters more than a small execution
kernel. Prefer an ordinary function or queue when the problem does not need a
workflow runtime at all.
