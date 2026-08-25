# RFC 0001: Sley Graph Runtime

- Status: accepted
- Revised: 2026-08-23

## Decision

Sley is a small structured graph runner. Its complete author model is:

```text
node(handler)                  wrap one callback
source.link(target, action?)   connect one route
context.state                 shared run state
context.input                 this branch's message
context.emit(action?, input?) continue or fan out
context.end(output?)          finish this branch
Flow(entry, ...)              run a graph scope
```

A callback that emits nothing follows its unlabelled link. A Flow can join its
completed branches with `combine`. Retry and recovery are explicit policies.
Everything else belongs in application code or later, evidence-backed RFCs.

The Python and TypeScript ports must expose the same behavior. Host-language
spelling may differ where forcing symmetry would make either API less natural.

## Public surface

The ordinary import surface is deliberately short:

```text
node, Node, Flow, CompiledFlow, Context, RetryPolicy
```

Advanced code may also import:

```text
GraphElement, Link
Failure, ScopeFailure, ScopeResult
Terminal, EndTerminal, ExitTerminal
RunHandle, RunResult, Completed, Failed
SleyError, GraphDefinitionError, DuplicateLinkError, RunError
CompiledDescription
```

Description record types may be public when the host language needs them for
static typing. Internal scheduler types are never public.

The runtime does not expose observers, reports, statistics, cancellation,
deadlines, timeouts, grace periods, abandonment, run-wide admission controls,
or scheduler event records.

## Definitions

`node(handler)` returns a final `Node`. Nodes are values rather than classes
authors subclass. It accepts optional `name`, `retry`, and `recover` settings.
The handler and recovery callback may be synchronous or asynchronous and must
return `None` in Python or `undefined` in TypeScript.

`GraphElement.link(target, action?)` creates a link owned by the source.
`target` comes first because it is always required and makes the common
unlabelled form read as `first.link(second)`. An action is a nonempty string.
Each source may have at most one link for an action and at most one unlabelled
link. Duplicate links fail immediately.

```python
classify.link(build, "build")
build.link(review)
```

```typescript
classify.link(build, 'build')
build.link(review)
```

`Flow` accepts:

```text
entry             required Node or Flow
name              optional diagnostic name
exits             named actions allowed to leave this Flow
concurrency       positive local worker count; default 1
max_activations   optional positive local cycle guard
combine           optional successful-scope callback
recover           optional failed-scope callback
```

Invalid definitions fail when constructed or compiled. `compile()` snapshots
the reachable topology and validates it. Later mutations of definitions do not
change a compiled Flow. Definitions and compiled Flows hold no run state.

`describe()` returns the compiled elements, links, entry, exits, and scalar
limits in fresh, detached plain records suitable for inspection and
visualization. It is not a run trace.

Version 1 has this exact portable shape:

```text
CompiledDescription {
  schema_version: 1
  root: { element_id: 1, scope_id: 1 }
  scopes: [{
    scope_id, owner_element_id, parent_scope_id, entry_element_id,
    name, exits, concurrency, max_activations
  }]
  elements: [DescriptionNode | DescriptionFlow]
}

DescriptionNode {
  element_id, kind: "node", name, links, max_attempts
}

DescriptionFlow {
  element_id, kind: "flow", name, links, owned_scope_id
}

DescriptionLink { action, target_element_id }
```

IDs, limits, concurrency, and retry counts are integers. Names, actions, and
exits are strings. `action`, `parent_scope_id`, and `max_activations` may be
null. Element and scope IDs follow deterministic compilation order, beginning
with root element and scope 1. Record arrays follow ID order, and link arrays
preserve definition order. Both ports expose matching structural types for
these records. A future shape change requires a new `schema_version`.

## State and input

Each run shallow-copies its initial top-level mapping once. Python uses an
ordinary `dict`; TypeScript accepts a plain object and uses an ordinary object.
All activations in that run share the copied top-level state and its nested
references. The caller's top-level mapping is not mutated.

`context.input` is the message for one branch. The root input is absent. An
emission without a new input forwards the current input. State and input are
separate by design:

- use state for facts shared for the life of the run;
- use input for the item carried by one branch;
- use an end output for a completed branch value intended for combination.

Sley validates its control protocol, not application schemas. Python retains
normal mapping behavior, including `KeyError` for a missing indexed key.
TypeScript retains normal object behavior, including `undefined` for a missing
property. Static types document payload agreements but do not validate runtime
data. Applications that cross a trust boundary validate at the start of a
handler or in a dedicated validation node.

## Control

The portable control calls are:

```text
emit()                  unlabelled route, current input
emit(input=value)       unlabelled route, new input
emit(action)            named route, current input
emit(action, value)     named route, new input
end()                   hard terminal without output
end(value)              hard terminal with output, including explicit null
```

TypeScript uses overloads that preserve the same distinctions without an
`{ input: ... }` wrapper.

Control calls append intent to the current callback buffer. They do not stop
the host function. Use `return context.end(...)` only when ordinary language
control flow should also return; `end` itself has no application return value.

The buffer commits only after the callback returns normally with the required
empty return value. A thrown exception or invalid return discards it. This keeps
partial fan-out from escaping a failed attempt without transactions.

For a node handler only, zero explicit control calls means one implicit
`emit()`. Thus `first.link(second)` still advances when `first` is silent. If no
unlabelled link exists, the branch exits the current Flow normally.

Flow `combine` and recovery callbacks do not create an implicit emission. Zero
emissions preserve their documented input outcome; explicit emissions replace
it. This avoids accidental extra branches from callback fall-through.

An action resolves in this order:

1. follow the source element's matching link;
2. otherwise, leave the current Flow when the action is a declared exit;
3. otherwise, fail with an unknown-action failure.

The unlabelled action may leave any Flow without being declared. A named string
such as `"default"` is ordinary data and is not the unlabelled action.

## Flow completion

A Flow is one structured execution scope. Its entry receives the Flow's input.
Branches settle as terminals:

- `context.end()` produces an `EndTerminal` with no output;
- `context.end(value)` produces an output-bearing `EndTerminal`;
- leaving a Flow produces an `ExitTerminal` whose output is the branch input.

`end` bypasses links and ends only its current branch. Other branches continue.
A root Flow completes after all of its branches settle.

Without `combine`, the Flow forwards its terminals to its parent. At the root,
they become the run terminals.

With `combine`, the callback runs once after every branch in that scope has
settled successfully:

```python
def combine(context, result):
    context.emit(input=sum(result.outputs))
```

`result.terminals` contains every terminal. `result.outputs` is the ordered
projection of output-bearing terminal values. It does not contain state,
handler returns, or intermediate emissions. Terminal order is settlement order.

If `combine` emits, its buffer replaces the child terminals and routes from the
Flow element. If it emits nothing, the original terminals are preserved. A
combiner may call `end` to replace them with hard terminals.

## Retry and recovery

`RetryPolicy` has only:

```text
max_attempts   positive integer; default 1
should_retry   synchronous Failure -> bool; default true
delay_ms       nonnegative integer or synchronous (attempt, Failure) -> integer
```

An attempt runs the whole node handler. A failed attempt discards buffered
control. Direct state mutations and external effects are ordinary application
effects and are not rolled back, so validation belongs before them and effects
that may repeat should be idempotent.

After a handler failure, the runtime retries only when attempts remain and
`should_retry` returns true. `delay_ms` is evaluated before a retry. Errors or
invalid values from retry policy code fail immediately as retry-policy failures.

When retry stops, the node's `recover(context, failure)` runs once when present.
Its explicit emissions replace the failure. Zero emissions propagate the
failure. A recovery error replaces the failure while retaining the previous
failure reference.

When any activation in a Flow remains failed, new activations in that Flow stop
being admitted and already-running local work is awaited. The Flow's
`recover(context, scope_failure)` then runs once when present. Its explicit
emissions replace the scope failure and route from the Flow element. Zero
emissions propagate the failure. Settled terminals are exposed on
`ScopeFailure`; recovery does not pretend they never happened.

When a failed nested Flow has settled terminals, those terminals propagate with
the failure into each enclosing scope's `ScopeFailure` and the final `Failed`
result. Explicit recovery emissions replace them like any other settled
terminals.

`Failure` is a small immutable record containing an id, kind, message, cause,
scope id, activation id, element id, attempt, and optional previous failure.
Failure kinds distinguish handler, retry policy, node recovery, flow combine,
flow recovery, invalid outcome, unknown action, activation limit, and internal
invariant failures. There is no public scheduler-fence taxonomy.

## Scheduling

Scheduling is local to each Flow. `concurrency=1` processes one activation at a
time. A larger value permits at most that many activations in that Flow to run
at once. Nested Flows apply their own limits. There is no run-global fairness or
admission policy.

The runtime uses ordinary host tasks and queues. Shared state is not made
transactional or race-free. Authors who opt into concurrency coordinate shared
writes with normal application primitives or aggregate branch outputs through
`combine`.

`max_activations` counts started activations in that Flow invocation and fails
before starting one beyond the limit. It exists as a simple guard for cyclic
graphs, not as a general resource-budget system.

## Results

`start(initial_state)` starts a compiled snapshot and returns a `RunHandle`.
The handle exposes `done()` and async `result()`. It does not expose framework
cancellation.

`result()` returns exactly one of:

```text
Completed(status, state, terminals)
Failed(status, state, terminals, failure)
```

`Flow.run(initial_state)` is the everyday projection. It awaits completion and
returns the final shared state. On failure it raises `RunError`, whose `result`
is the exact `Failed` value. When `result.failure.cause` is non-null, native
chaining exposes that identical value: `error.__cause__ is
error.result.failure.cause` in Python and `error.cause ===
error.result.failure.cause` in TypeScript. Only the controlling `result.failure`
participates; superseded failures remain available through `Failure.previous`.
Native task cancellation remains native task cancellation; the runtime adds no
second cancellation model.

Each terminal exposes:

```text
type                   "end" or "exit"
action                 exit action only
has_output             distinguishes omission from explicit null
output                 captured terminal value
sequence               settlement order
source_activation_id   activation that produced it
```

The state in a result is the run's shallow-copied top-level state object. It is
not copied again at completion.

## Error behavior

Sley fails fast on invalid definitions, control arguments, handler return
values, unknown actions, policy return values, and broken internal invariants.
It does not silently drop branches, coerce malformed values, or invent routes.

Ordinary application exceptions become `Failure` values so declared retry and
recovery policies can handle them. Unhandled failures become `Failed` results.

## Non-goals

Sley does not include:

- observers, event streams, reports, built-in logging, or run statistics;
- deadlines, node timeouts, grace periods, cancellation tokens, or abandonment;
- run-wide concurrency, fairness, ready-queue, or resource-limit matrices;
- persistence, distribution, replay, transactional state, or schema validation;
- special data structures for extreme graph size or failure volume;
- compatibility packages or a second legacy runtime.

These require new evidence and a separate RFC. They must not be scaffolded in
the current implementation.

## Implementation constraints

The graph runner is the project's strictest simplicity boundary. The public API
must be thinner still: validation plus delegation, with no scheduler logic.

Implementations use standard-library or native platform primitives first. A
custom heap, queue, proxy, persistent collection, event protocol, or scheduler
abstraction requires a measured need. Code for a hypothetical future feature is
out of scope.

Tests may be extensive because they reduce risk without becoming shipped
runtime. Cookbook examples may be detailed when that detail teaches a concept.
Neither is a reason to enlarge the production runner.

## Conformance

Language-neutral fixtures cover the retained semantic surface: definitions,
routing, state/input, fan-out, terminals, nested Flows, combine, retry,
recovery, concurrency, activation limits, results, and fail-fast errors. Python
and TypeScript must agree on those observable facts.

Port-specific tests may be broader and should enforce host-language typing and
native behavior. Conformance tests do not justify public types or runtime
branches that are absent from this RFC.
