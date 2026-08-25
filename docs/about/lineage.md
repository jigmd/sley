---
description: See how PocketFlow evolved into Caskada and Sley, including what Sley improves and what it deliberately gives up.
---

# PocketFlow, Caskada, and Sley

Sley did not appear in a vacuum. It exists because two earlier runtimes taught
us which graph ideas stayed small and which conveniences became difficult to
reason about. Knowing that history makes Sley's sharp edges easier to judge.

Sley is the third step in one design lineage:

1. **PocketFlow** established a small graph-oriented workflow model.
2. **Caskada** expanded it with richer memory, routing, concurrency, and matching
   Python and TypeScript APIs.
3. **Sley** keeps the graph runtime while replacing implicit and class-heavy
   behavior with a smaller explicit contract.

Sley is the runtime formerly designed as Caskada v3. It now has its own name,
packages, and version history while remaining a proud fork and successor. The
Caskada comparison below means the published v2 API; comparing Sley with the
proposed Caskada v3 would compare Sley with an earlier draft of itself.

## The design moved toward explicit boundaries

| Concern          | PocketFlow                     | Caskada v2                          | Sley                                        |
| ---------------- | ------------------------------ | ----------------------------------- | ------------------------------------------- |
| Node authoring   | Lifecycle subclasses           | Lifecycle subclasses                | Functions wrapped by `node(...)`            |
| Data             | Shared store and params        | Global and local `Memory`           | Shared state, branch input, terminal output |
| Routing          | Returned actions and operators | `trigger()`, `next()`, `on()`, `>>` | Buffered `emit()` and target-first `link()` |
| Fan-out          | Batch classes                  | Multiple targets or parallel Flows  | Several explicit emissions                  |
| Fan-in           | Application aggregation        | Counters or Flow `post`             | Flow `combine` after settlement             |
| Named boundaries | Action conventions             | Terminal trigger propagation        | Declared exits; unknown actions fail        |
| Everyday result  | Mutated shared store           | Execution tree beside Memory        | Final shared state                          |
| Cycle limit      | Application convention         | Hidden default `max_visits=15`      | Optional explicit `max_activations`         |

## What Sley improves

- One function replaces `prep`, `exec`, and `post` lifecycle ceremony.
- State, branch input, and completed output have distinct ownership.
- Unhandled named routes fail instead of silently escaping a Flow.
- Intentional fan-out is visible as several emissions.
- `combine` joins dynamic branches without application counters.
- `run()` returns the state most callers actually need.
- Python and TypeScript share executable conformance cases.

## What Caskada did better

- `prep` gave validation a named phase, and retry could focus on `exec`.
- Subclassing offered more Node and Flow extension points.
- Local `Memory` cloning reduced explicit branch-payload plumbing.
- Trigger propagation crossed nested Flows without declared exits.
- One action could broadcast to several physical targets tersely.
- A default visit limit protected every cycle automatically.
- `run()` always produced a complete execution tree for tracing.

Sley makes the opposite choices to keep control and failure behavior easy to
trace. Those costs are intentional, not compatibility gaps waiting for another
option.

## Sley's accepted tradeoffs

| Choice                       | Benefit                       | Cost                                                            |
| ---------------------------- | ----------------------------- | --------------------------------------------------------------- |
| Function handlers            | Little framework ceremony     | No dedicated validation phase                                   |
| One shared state             | One authoritative final state | Concurrent writes need discipline                               |
| Explicit branch input        | Visible per-branch data       | Linked handlers must agree on shape                             |
| Buffered control             | Atomic branch outcomes        | `end()` does not return from the function                       |
| Structured combine           | Runtime-owned fan-in          | Terminal replacement must be understood                         |
| Host-language data           | No proxy or schema layer      | Python and TypeScript fail differently on missing fields        |
| Application-owned operations | Small runtime                 | No built-in timeouts, tracing, persistence, or cancellation API |

## Choose for the problem you have

Choose Sley when graph topology and runtime behavior should stay visible in
application code, structured fan-in matters, and Python/TypeScript parity is
valuable.

Keep Caskada v2 when an existing application's lifecycle subclasses, Memory
behavior, or execution-tree consumers are stable and useful. Use PocketFlow
when its original model already solves the problem. Use an ordinary function or
queue when no graph runtime is needed.

Ready to move? Follow the [Caskada migration](migrate-from-caskada.md) or
[PocketFlow migration](migrate-from-pocketflow.md).
