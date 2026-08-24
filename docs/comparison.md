---
machine-display: false
---

# PocketFlow, Caskada, and Sley

Sley is the third step in one design lineage:

1. **PocketFlow** established the small, graph-oriented workflow model.
2. **Caskada** expanded that model with richer memory, routing, concurrency, and
   matching Python and TypeScript APIs.
3. **Sley** keeps the graph runtime but replaces implicit and class-heavy parts
   of Caskada with a smaller, explicit execution contract.

Sley is the graph runtime formerly designed as Caskada v3. It now has its own
name, packages, and version history while remaining a proud fork and successor
of Caskada. In this page, **Caskada means the v2 API** that existing users
migrate from; comparing Sley with the proposed Caskada v3 would compare Sley
with an earlier draft of itself.

## The Evolution

PocketFlow made graph workflows approachable through nodes, actions, and a
shared store. Caskada kept that foundation and made it more capable, but its
`prep` / `exec` / `post` lifecycle, `Memory` proxy, trigger propagation, and
execution trees increased the number of rules an author had to hold at once.

Sley does not reject that history. It applies what Caskada taught us: keep the
graph, make branch data and completion explicit, let the runtime own fan-in,
and remove machinery that is not required to execute the graph.

| Concern               | PocketFlow                        | Caskada v2                              | Sley                                            |
| --------------------- | --------------------------------- | --------------------------------------- | ----------------------------------------------- |
| Node authoring        | `Node` subclasses                 | `Node` subclasses                       | Functions wrapped by `node(...)`                |
| Handler lifecycle     | `prep` / `exec` / `post`          | `prep` / `exec` / `post`                | One sync or async handler                       |
| Data                  | Shared store and params           | Global and local `Memory`               | Shared `state`, branch `input`, terminal output |
| Routing               | Returned actions and operators    | `trigger()`, `next()`, `on()`, and `>>` | Buffered `emit()` and target-first `link()`     |
| Fan-out               | Batch classes                     | Multiple targets or parallel Flows      | Several explicit emissions                      |
| Fan-in                | Application aggregation           | Shared counters or Flow `post`          | Flow `combine` after the scope settles          |
| Named Flow boundaries | Action conventions                | Terminal trigger propagation            | Declared exits; unknown actions fail            |
| Common run result     | Mutated shared store              | Execution tree beside mutated memory    | Final shared state                              |
| Detailed result       | Framework-specific execution data | Execution tree                          | Terminal records from `start()`                 |
| Cycle limit           | Application/framework convention  | Hidden default `max_visits=15`          | Optional explicit `max_activations`             |

## Sley Compared with Caskada

Sley is better when explicit behavior and a smaller mental model matter more
than lifecycle hooks and implicit convenience. It is worse when an application
benefited from those Caskada conveniences and does not want to spell out their
replacement.

### What Sley Improves

- **Less authoring ceremony:** one function replaces a lifecycle subclass.
- **Clearer data ownership:** shared state, branch input, and completed branch
  output are separate channels instead of views through one `Memory` proxy.
- **Fail-fast routing:** a misspelled or missing route fails unless it is a
  declared Flow exit.
- **Visible fan-out:** one action has one physical target; several destinations
  require several emissions, so broadcast is intentional at the call site.
- **Structured fan-in:** `combine` runs when the Flow is quiet, without shared
  counters recreating scheduler state in application code.
- **A useful default result:** `run()` returns the final shared state directly;
  callers opt into terminal detail with `start()`.
- **A smaller runtime:** graph compilation, callback control, state capture,
  and one scope runner implement the contract in both languages.
- **Executable parity:** language-neutral conformance cases verify that Python
  and TypeScript settle the same graphs the same way.

### What Caskada Did Better

- **Lifecycle boundaries were obvious:** `prep` gave validation a named home,
  and retry could focus on `exec`. Sley authors must validate before writes or
  effects because retry repeats the whole handler.
- **Subclassing offered extension points:** custom Node and Flow behavior fitted
  object-oriented applications. Sley deliberately exposes fewer hooks.
- **Local Memory was convenient:** branch-local cloning and global fallback
  required less explicit payload plumbing, even though the proxy rules were
  harder to reason about.
- **Trigger propagation was permissive:** a nested Flow could pass a named
  action outward without declaring an exit. Sley requires the boundary to say
  which actions may leave it.
- **One action could broadcast:** connecting several physical targets was terse.
  Sley makes the same fan-out more verbose by requiring separate emissions.
- **Cycle protection was automatic:** Caskada imposed a default visit bound.
  Sley has no hidden limit; cyclic Flows should set `max_activations` explicitly.
- **`run()` always produced an execution tree:** that was useful for tracing.
  Sley's detailed result records terminals, not a complete execution history.

These are intentional tradeoffs, not compatibility gaps waiting to be filled.
Adding lifecycle hooks, implicit routing, proxy memory, or tracing to Sley would
require evidence that the benefit outweighs the added runtime and authoring
rules.

## Sley's Own Tradeoffs

| Choice                      | Benefit                                     | Cost                                              |
| --------------------------- | ------------------------------------------- | ------------------------------------------------- |
| Function-first nodes        | Little framework ceremony                   | No lifecycle phase dedicated to validation        |
| One shared run state        | One authoritative result state              | Concurrent writes need application discipline     |
| Branch input and End output | Explicit per-branch data flow               | Connected handlers must agree on payload shape    |
| Buffered control            | Atomic zero, one, or many routes            | `end()` does not stop host-language execution     |
| First-class Flow combine    | Correct structured fan-in                   | Authors must understand terminal replacement      |
| No built-in integrations    | Direct provider APIs and fewer abstractions | Applications own provider configuration and fakes |
| Python/TypeScript parity    | Portable workflow semantics                 | The contract follows the smaller common surface   |

Sley validates its control protocol, not application schemas. Missing Python
mapping keys raise `KeyError`; missing TypeScript properties normally produce
`undefined`. Static types document connected payloads but do not validate them
at runtime. Validate external data at the beginning of a handler or in an
ordinary preparation node.

## Which One Should You Use?

Use **Sley** for new graph runtimes when explicit topology, structured fan-in,
fail-fast routing, a small implementation, and Python/TypeScript parity are the
priority.

Keep **Caskada v2** when maintaining an existing application whose lifecycle
subclasses, Memory behavior, or execution-tree consumers are stable and useful.
Migration is worthwhile when those features create more complexity than value,
not merely because Sley is newer.

Return to **PocketFlow** when its original minimal model already solves the
problem. Prefer an ordinary function or queue when the problem does not need a
graph runtime at all.

For concrete conversions, see [Migrating from PocketFlow](./guides/migrating_from_pocketflow.md)
and [Migrating from Caskada v2](./guides/migration.md).
