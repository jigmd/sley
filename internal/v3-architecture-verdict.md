# Caskada v3 Architecture Verdict

- Status: current v3 decision record with a preserved historical appendix
- Date: 2026-08-16
- Scope: clean-sheet Caskada v3 architecture, including ideas prompted by the
  proposed Jig and Jig Graph designs
- Current authority: [RFC 0001: Caskada v3 Structured Graph Runtime](rfcs/0001-caskada-v3-runtime.md)

## Current v3 decision

The original court answered a narrow question: which ideas from the proposed Jig
and Jig Graph designs improve Caskada independently while preserving the v2 API.
The subsequent v3 brief removed that compatibility constraint because Caskada has
not acquired production users. That changes the admissible solution, not the
standard: every feature must still improve Caskada as a general-purpose graph
runtime and preserve its small mental model.

RFC 0001 is the normative specification. The A1-A12 table below summarizes its
actionable architectural calls; RFC 0001's D1-D15 ledger is the binding index.
RFC 0001 is also the sole authority for release gates. The current boundary and
decision record appear before one explicit historical appendix; everything in
that appendix is non-normative evidence from the earlier court.

The final author-API review rejected an earlier draft that exported too many
runtime distinctions as author-owned objects. V3 keeps fan-out, termination,
and advanced outcomes precise, but gives ordinary authors only three data roles:
one invocation-owned shared state, one branch input, and one terminal output.
Control is recorded through one callback-local Context rather than returned
descriptor objects, and ordinary callers never inspect terminal arrays merely
to recover the run state.

### What survived the original verdict

Two findings became foundations rather than isolated additions:

1. **Portable inspection survives as `links()` and `describe()`.** C1's
   general need was correct. The clean-sheet API narrows each action to one target,
   exposes declaration-ordered link snapshots, and adds compiled,
   scope-aware inspection. Named actions are nonempty strings in both languages;
   an unlabelled edge uses a private sentinel and appears as null only in
   inspection/events.
2. **Invocation isolation survives as compile plus schedule.** C13's general
   correctness requirement was correct. V3 snapshots topology once, stores all
   framework execution state in an invocation, and uses lightweight activations.
   It removes public cloning instead of standardizing an unnecessary clone API.

The C2-C12 boundary also survives: semantic route metadata, decision engines,
router classes, workflow contracts, registries, agents, and declarative authoring
remain extensions. The v3 kernel makes them easier to build without knowing they
exist.

### What the clean-sheet brief superseded

| Historical constraint                       | Current v3 decision                                                                                                               |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Preserve `prep` / `exec` / `post`           | One ordinary handler function wrapped by `node(...)`; Node subclassing is removed.                                                |
| Preserve definition-owned `trigger()` state | Invocation-local `context.emit(...)` / `context.end()` buffers; a normal return with no emission takes the implicit default path. |
| Preserve `on()` / `next()` and operators    | One portable `node.link(...)` topology method.                                                                                    |
| Preserve `Memory` proxy semantics           | One invocation-owned `context.state`, normalized from `initial_state` once at run start, plus branch-specific `context.input`.    |
| Preserve repeated targets per action        | One target per source/action; repeated emissions express dynamic fan-out.                                                         |
| Preserve `ParallelFlow`                     | `Flow.concurrency` plus a topology-derived run-wide callback ceiling that can be explicitly overridden.                           |
| Define manual `clone()` parity              | Remove clone from v3; compile a definition and isolate every run.                                                                 |
| Preserve mandatory `ExecutionTree`          | `run()` returns shared state after any successful completion; `start()` exposes the exact structured outcome.                     |

This is intentionally aggressive. It removes concepts only when their capability
has a simpler explicit replacement.

The complete everyday Python grammar is deliberately small:

```python
from typing import TypedDict

from caskada import Context, Flow, node


class Model:
    async def answer(self, question: str) -> str:
        return question.upper()


class Reviewer:
    async def check(self, question: str, answer: str) -> None:
        assert question and answer


model = Model()
reviewer = Reviewer()


class AnswerState(TypedDict):
    question: str
    answer: str


@node
async def answer(context: Context[AnswerState]) -> None:
    question = context.state["question"]
    context.state["answer"] = await model.answer(question)
    context.emit("review", question)


@node
async def review(context: Context[AnswerState, str]) -> None:
    await reviewer.check(context.input, context.state["answer"])
    # No control call exits the root Flow.


answer.link(review, "review")


async def run_answer() -> None:
    final_state = await Flow(answer).run({"question": "Why?", "answer": ""})
    assert final_state["answer"]
```

`node(...)` creates the graph object; a raw function is not itself a graph
placement. The decorator is only the ordinary Python spelling of that wrapper.
The handler does not return a framework control object. `emit()` and `end()`
append to a buffer owned by that one callback invocation, and the scheduler
validates and commits the whole buffer only after the handler returns normally.
Ignoring the return value of `emit()` cannot lose a transition, and concurrent
runs cannot share its buffer. Zero calls preserve the convenient implicit default
transition. Multiple calls make fan-out visible as multiple statements.
The buffer belongs on `context`, not `self`: a Node is reusable definition data,
while an emission belongs to exactly one attempt of one activation in one run.
This retains the directness of v2's statement-style trigger without reintroducing
definition-owned mutable execution state. The verb is `emit`, not `trigger`,
because the call records an outgoing intent that may still be discarded if the
callback fails, times out, or produces an invalid batch; it does not immediately
schedule a target.

`link` puts topology first: `source.link(target)` declares the unlabelled edge,
and `source.link(target, action)` qualifies that same target with a named action.
V2's `on(action, target)` put the condition first because it read as “on this
action, use this target”; that grammar does not control a verb that means “link
this source to that target.” Target-first keeps both overloads stable. Omitting
`action` is the only unlabelled spelling; explicit Python `None` or TypeScript
`null` / `undefined` is invalid.

Each source/action has one physical target. Allowing several targets made an
apparently singular decision such as `trigger("review")` silently become a
broadcast when topology changed, with no place to attach branch-specific input or
reason about ordering. Repeating `emit("review", value)` makes dynamic fan-out,
cardinality, order, and payload explicit at the decision site.

`context.state`, `context.input`, and terminal `output` are deliberately distinct.
The runtime shallow-copies the caller's top-level state exactly once, and every
activation in the invocation sees that same map; nested references remain
borrowed. The root begins with a nullish input. `emit(action, value)` supplies
a branch-specific value to a successor;
omitting `input` forwards the current input, while explicitly passing a nullish
value preserves that value. `end(value)` publishes a terminal value; `end()`
hard-ends that arm without publishing an output. Explicitly passing a nullish
value still publishes that value. Terminals never carry independent state maps.

`input` and `output` are payload roles, not option records. Labelled routing and
termination therefore take values directly: `context.emit("review", question)`
and `context.end(answer)`. Only the rare TypeScript form that replaces input on
an unlabelled route needs the disambiguating `context.emit({ input: value })`;
Python spells it `context.emit(input=value)`.

State bindings, branch input, emitted input, and terminal output remain opaque
application data. Caskada validates its control protocol and initial state
container, not application fields or schemas. Python missing-key indexing raises
the native `KeyError`, while `.get(...)` retains defaulting behavior; an escaping
error becomes the ordinary Failure for that callback phase and follows its retry
or recovery policy. JavaScript missing-property access remains `undefined`.
TypeScript's `--noUncheckedIndexedAccess` helps expose potentially absent reads
statically without changing runtime language conventions. Local
`Context<State, Input>` types are author assertions, not runtime validators or
proof that a predecessor emitted the asserted shape.

Application code should parse at its first consumer before state writes or
external effects. When parsing must remain outside a retried operation, use an
ordinary validation node that emits the parsed value to the retried work node.
A strict missing-property Proxy would break optional chaining and fallback while
still missing nested, wrong-type, and input errors; a core schema or validator
hook would imply graph-wide guarantees that payload-untyped links cannot make.
Higher layers may provide schema-bearing wrappers without adding a lifecycle
phase to core.

The result surface has two levels over one execution:

- `run(initial_state)` waits for the entire root scope and returns its one shared state
  for every successful completion, independent of terminal kind or count;
- `start(initial_state)` exposes a `RunHandle` whose result preserves status, the same
  state, terminal kinds/actions/outputs, failures, cancellation, abandonment,
  statistics, and diagnostics.

Choosing `run()` deliberately discards successful terminal kinds, actions, and
outputs; callers that need them choose `start()`. Failed, cancelled, and
abandoned executions raise one typed `RunError` carrying the exact `RunResult`
produced by that execution. Projection never reruns the graph or selects a
terminal as the authoritative state. Every result exposes the exact persistent
run-owned state carrier as a live reference, not a snapshot. Settlement closes
the scheduler's callback capabilities, including later `context.state` lookup,
but it does not revoke a state alias obtained while a Context was live. Such an
alias can still mutate top-level or nested state after completion, failure, or
abandonment, and uncooperative work may still produce external effects.
Abandonment means the runtime stopped waiting, not that it rolled application
effects back.

Flow combination is the explicit aggregation boundary. A combiner receives the
ordered `result.outputs` for ordinary aggregation and may inspect
`result.terminals` when control provenance matters. It can reduce outputs into
`context.state`, then forward or replace the terminal set. Ordinary `run()`
callers still receive the shared state, so fan-out does not force terminal
indexing or map-reduce ceremony.
Neither feature is ceremonial: most leaves emit nothing and most Flows use the
default Flow boundary behavior, which preserves the terminal set exactly.
Authors call `end()` only for a deliberate output-free hard stop, call
`end(value)` for a terminal output, and
supply `combine` only when branch outputs need aggregation or the Flow must
replace its outward control.

The top-level input container is a seed, not a borrowed cell. Caskada validates
and shallow-normalizes `initial_state` once into a fresh persistent carrier. Every
activation and result in that invocation observes the same carrier identity;
nested values remain borrowed. This one copy prevents two concurrent runs
started from the same seed from mutating each other's top-level state. The
returned carrier remains live rather than becoming an immutable publication.
Logically continuous phases should therefore be linked under one root Flow;
deliberately separate runs may spell `state = await next_flow.run(state)`, with
the next run making its own top-level copy.

Parallelism has one ordinary knob. Every Flow still defaults to local concurrency
one. When `RunOptions.max_concurrency` is omitted, the compiler derives the
run-wide callback ceiling as the largest `Flow.concurrency` in the compiled
topology. A Flow declaring concurrency eight therefore works without a second
opt-in, while nested declarations do not multiply into an accidental global
budget. An explicit run option remains an advanced global throttle or expansion.

A Flow may also declare an optional direct-activation budget. Each runtime scope
invocation gets a fresh counter; it counts that Flow's entry and direct child
activations, but not retries, callbacks, or descendants inside nested Flows. This
restores a reusable component-level loop safeguard without reviving v2's hidden,
refactor-sensitive per-node `max_visits` default.

The tradeoff is explicit: parallel callbacks mutate one shared map. Serial
execution is deterministic, but concurrent writes to the same mutable location
are application-coordinated and otherwise unspecified. Parallel workflows should
use disjoint state keys, an explicit synchronization/service boundary, or isolated
terminal outputs followed by a Flow combiner. Caskada does not pretend shared
mutable state is transactional.

### Actionable architecture summary

| ID  | Binding decision                                                                                                                           | Implementation consequence                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Required proof before freeze                                                                                                                                                                                                                       |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1  | Caskada remains an in-process, zero-dependency structured graph runtime.                                                                   | Keep one Python module and one browser-safe TypeScript module until splitting demonstrably improves comprehension.                                                                                                                                                                                                                                                                                                                                                                                | Dependency audit, browser test, and source-size review.                                                                                                                                                                                            |
| A2  | Everyday authoring is `node(handler)`, `Flow`, `context.state`, `context.input`, buffered `emit`/`end`, implicit default, and `node.link`. | No route-result constructor import, second graph DSL, lifecycle protocol, join graph element/scheduler primitive, or runtime service appears in core. Raw callables must be wrapped before they become graph objects. `@node` creates one topology-bearing occurrence; reusable behavior is wrapped inside a graph factory.                                                                                                                                                                       | Official guide teaches the complete grammar before advanced policy, with imports visible and state/input/output roles explicit.                                                                                                                    |
| A3  | A node wraps one handler; retry is whole-handler and at-least-once.                                                                        | Remove `prep`, `exec`, `post`, definition-owned trigger state, and framework cleanup hooks; retain optional one-shot recovery as wrapper configuration. Retry delay accepts either a constant duration or a policy callback.                                                                                                                                                                                                                                                                      | Retry fixtures expose retained mutations/effects, discard emissions from failed attempts, accept constant and dynamic delay policies, and never overlap timed-out attempts.                                                                        |
| A4  | Routing uses a Context-owned emission buffer.                                                                                              | `emit()` and `end()` append inert records during the live callback; a normal return validates and atomically commits the complete buffer. Zero emissions apply the phase-specific rule: a handler synthesizes one unlabelled route, while recovery and combination preserve the exact failure or terminal set. Handler return values do not carry graph control. Omitted emit input forwards the current input; `end()` carries no output; explicitly supplied nullish values remain real values. | Cross-language fixtures cover default/emit/end, argument-presence capture, stale Contexts, repeated emissions, mixed invalid buffers, retries, and all budget rejections.                                                                          |
| A5  | Each source/action has at most one target through target-first `node.link`.                                                                | `link(target)` is unlabelled and `link(target, action)` is named; omission alone selects unlabelled routing. Reject duplicate or explicit nullish actions immediately, use repeated emissions for repeated activations, and reserve no user action string.                                                                                                                                                                                                                                        | Ordered snapshot, argument-order, nullish-action rejection, duplicate, cycle, and repeated-emission fixtures.                                                                                                                                      |
| A6  | Every Flow is a structured scope and advanced combination has identical root/nested meaning.                                               | Track exact live tokens and preserve terminal kind/action/output/order/cardinality losslessly. A combiner uses ordered `outputs` for ordinary aggregation and `terminals` for advanced provenance. `run()` projects every successful completion to shared state and raises one typed error for a non-completed result; `start()` preserves every status and all terminal metadata.                                                                                                                | Root/nested equivalence, mixed terminals, output aggregation, plural completion, failure/cancellation/abandonment errors, no-rerun, failure, and atomic forwarding fixtures.                                                                       |
| A7  | Definitions and invocations are separate.                                                                                                  | `compile()` captures placements/topology once; runs own activations, scopes, queues, counters, timers, fences, and signals.                                                                                                                                                                                                                                                                                                                                                                       | Concurrent reuse and 100,000-placement nonrecursive compile/run tests.                                                                                                                                                                             |
| A8  | Execution is serial unless a Flow explicitly opts into structured parallelism.                                                             | One iterative scheduler enforces per-scope direct slots. An omitted run ceiling resolves to the maximum local Flow concurrency in the compiled topology; an explicit ceiling throttles or expands aggregate parallelism. Retries reacquire only callback permits.                                                                                                                                                                                                                                 | Fairness, all-concurrency-one serial proof, nested local concurrency, topology-auto derivation, explicit override, retry-delay, and global-ceiling tests.                                                                                          |
| A9  | State ownership and application-data boundaries are honest, not magical.                                                                   | Validate and shallow-normalize the caller's `initial_state` once per invocation and share that exact persistent run-owned carrier across all activations and results. Treat state values, branch input, emitted input, and terminal output as opaque application data with host-language missing-field behavior. Retained state aliases remain live, and concurrent writes are application-coordinated and otherwise unspecified.                                                                 | Caller isolation, one-carrier identity, host missing-field semantics, opaque input/output capture, retry visibility, plural fan-out, shared-write race documentation, terminal aggregation, and exact state identity in every `RunResult` fixture. |
| A10 | Failure, cancellation, deadlines, and work are bounded.                                                                                    | Typed packet-owned failures, universal replacement, deterministic run-fence drain, hierarchical cancellation, non-resetting grace per fence, portable collection/event bounds, overflow-safe timers, and a final `Abandoned` envelope whose retained-state-alias and external-effect limits are documented.                                                                                                                                                                                       | Packet lifecycle/drain matrix, uncooperative callback and post-fence state-alias tests, post-fence reporting, timer arithmetic, and every work/cardinality limit.                                                                                  |
| A11 | Observation is typed, causally ordered, and nonfatal.                                                                                      | Read-only definition/compiled inspection and one synchronous event observer; causally ordered facts publish in contiguous bounded bundles; no retained tree or async buffer in core.                                                                                                                                                                                                                                                                                                              | Per-event and reentrant-order parity fixtures, observer failure/backpressure tests, and tree-adapter reconstruction.                                                                                                                               |
| A12 | Higher layers remain higher layers.                                                                                                        | Jig Graph may own contracts, schema-bearing validation wrappers, and semantic routers; Jig may own agents, catalogues, planning, persistence, and policy.                                                                                                                                                                                                                                                                                                                                         | No provider, schema, validator lifecycle, registry, or authoring dependency enters core without a separate general-purpose RFC.                                                                                                                    |

### Implementation order

The implementation is gated, not a simultaneous rewrite:

1. Freeze language-neutral topology, emission, state, terminal, failure, result, event,
   and statistics fixtures.
2. Build the definition compiler and inspection contract in both languages.
3. Build the serial iterative scheduler and prove root/nested scope semantics.
4. Add retry, packet-owned recovery, universal replacement/drain, limits, and
   first-fence behavior.
5. Add structured concurrency, deadline, cancellation, grace, and abandonment.
6. Add the observer and reference tree/logging adapters outside core.
7. Migrate every official example, then delete the v2 API rather than carrying
   aliases in core.

An implementation phase cannot weaken an earlier fixture to accommodate one
language. A semantic change requires an RFC amendment and matching fixture change
before either port lands it.

### Design tournament record

The summit deliberately compared incompatible clean-sheet directions rather than
editing v2 names in place:

- a minimal stateful single-handler runtime;
- a pure value-passing dataflow runtime with immutable packets and explicit
  mount/group ownership;
- a conservative v2-shaped runtime with return-value transition control;
- the selected structured-scope synthesis, whose final author grammar is normative
  in RFC 0001.

Independent critics rejected the early minimalist, conservative, and first two
synthesis revisions for concrete flaws in root result preservation, nested
semantics, retry permits, failure identity, cancellation precedence, event
typing, deadline ordering, and author-facing control/state fragmentation.
The value-passing direction reached the quality
bar as a credible alternate, but lost on everyday concept count and ownership
burden. A later API jury also rejected return-value control objects, raw-function
graph elements, and terminal-array-only results: each made a runtime distinction
precise by transferring avoidable bookkeeping to ordinary authors. This history
is recorded to prevent those resolved tradeoffs from being silently reopened
during implementation. A final result-model challenge then rejected per-terminal
state maps and a plural-state convenience projection: after unreduced fan-out
there is no principled map for `run()` to choose. Separating one shared run state
from branch inputs and terminal outputs solves that ambiguity without hiding
cardinality.

### Cookbook cross-examination

The public grammar was then applied, as a design simulation rather than an
executable port, to five demanding Python cookbooks: [nested batch
processing](../cookbook/python-nested-batch/README.md), [RAG
map/reduce](../cookbook/python-rag/README.md), an [agent
supervisor](../cookbook/python-supervisor/README.md), and [iterative
thinking](../cookbook/python-thinking/README.md), plus a [tool
crawler](../cookbook/python-tool-crawler/README.md) whose crawl fan-out publishes
per-page terminal outputs to a local combiner before one report continuation.
Three smaller ports isolate the
termination rules: [hello world](../cookbook/python-hello-world/README.md) shows
an ordinary zero-emission leaf, [the text
flow](../cookbook/python-flow/README.md) shows `end()` bypassing a loop, and [CSV
batching](../cookbook/python-batch-node/README.md) shows branch-level
`end(value)` plus `combine=`. A separate critic reviewed only the v2-to-v3 diffs
and initially rejected the proposal. That rejection was useful: small examples
had not exposed the interaction between nested fan-out, aggregation, concurrency
ceilings, sequential state handoff, retries, and cyclic safety limits.

The experiment changed six core decisions:

1. `Flow(concurrency=8)` must work without a second run-option opt-in. Omitted
   run concurrency now resolves to the maximum local Flow concurrency in the
   compiled topology; an explicit value remains the aggregate override.
2. `ScopeResult.outputs` is the ordinary aggregation view. Exact terminal kinds,
   actions, and provenance remain available through `terminals`, but map/reduce
   code does not filter `ends` and `exits` merely to collect values.
3. `Context` gains an optional local input type parameter. It improves ordinary
   node-handler checking without pretending links enforce a graph-wide payload
   contract or adding runtime concepts. A Flow combiner's input remains dynamic.
4. Retry delay accepts a fixed duration as well as a callback. A constant delay
   no longer requires a named function whose only job is to return an integer.
5. `end()` is a hard terminal with no output, while `end(value)` publishes one.
   Empty dispatchers can therefore produce zero values without adding a `drop`
   verb or fabricating an input-shaped output.
6. A Flow may declare an optional aggregate direct-activation cap, freshly owned
   by every scope invocation. It restores a reusable local cycle safeguard without
   restoring v2's hidden per-node visit counters.

A focused typing jury kept `ScopeResult.outputs` as `object` in Python and
`unknown` in TypeScript. Local `Context[State, Input]` typing is captured by the
existing generic `node(handler)` function and then erased from topology. A Flow
combiner summarizes an entire scope and may legitimately receive heterogeneous
End/Exit outputs, so its `context.input` is also `object` in Python and `unknown` in
TypeScript. TypeScript cannot capture a
constructor-local output generic without either propagating it through `Flow`,
weakening callback variance, or replacing the ordinary class surface.
Applications therefore narrow or validate both aggregate outputs and combiner
input at that boundary. This is an honest local dynamic boundary, not a claim
that links prove payload compatibility.

The court retained copy-in state after a focused ownership challenge. Borrowing
the caller's exact map restored v2's convenient sequential spelling, but allowed
two runs started from the same object to mutate each other's top-level state and
allowed caller aliases to mutate the run's top-level state. The accepted remedy
is to name the argument `initial_state`, copy it once into a persistent run-owned
carrier, and make assignment explicit across genuinely separate run boundaries.
The RAG simulation intentionally keeps its recognizable offline and online runs,
so the required `state = await offline.run(state)` handoff remains visible.

The first ports also revealed a review failure: production scaffolding had made
them harder to compare with v2. The readability pass restored original prompts,
data, run boundaries, and serial or parallel shape; removed validators,
cancellation plumbing, thread wrappers, and safety budgets unrelated to each
lesson; and moved project typing out of the control-flow examples. Hello world is
the one typed reference, with its static state type isolated in `models.py`. The
thinking example retains one material safety rule: because retries cover the
whole handler, accepted state is committed only after fallible model and parsing
work.

The following tempting repairs were rejected because they add control grammar or
weaken lossless behavior:

- no `emit_many`, `drop`, or separate empty-success primitive; an empty
  dispatcher uses the existing no-output `end()` arm;
- no `forward` or `collapse` combiner verb; an absent or zero-emission combiner
  forwards exactly, while a replacing combiner emits its replacement explicitly;
- no borrowed-state mode, copy-back mode, or state-reference wrapper;
- no hidden per-node `max_visits`; cycles use domain guards plus optional
  scope-local and run-wide activation, transition, attempt, and deadline limits;
- no new synonym for `end`; it appends one hard terminal arm and does not stop
  the callback, sibling arms, or the run.

These cookbook files remain proposal fixtures until v3 exists. Their purpose is
to expose the author model in readable programs that can be compared directly
with v2, not to claim an implementation or production template. Independent
readability review closed with no blocker or major. The remaining friction --
dynamic aggregate outputs, the explicit state handoff between separate runs,
whole-handler retry discipline, empty fan-out needing no-output `end()`, and
`end(value)` naming a branch terminal rather than whole-run termination -- is
design evidence rather than a reason by itself to add another core verb or state
mode. Executable conformance and cross-port runtime evidence remain release
gates.

## Features that remain above Caskada

The following proposals are useful, but they are not Caskada v3 core changes:

- standalone workflow, path, decision, input, and output contracts;
- YAML or JSON workflow authoring and a runtime-neutral intermediate model;
- schema validation, reference resolution, expressions, and input/output mapping;
- workflow manifests, versions, aliases, capabilities, costs, and requirements;
- plugin discovery and a workflow registry;
- semantic candidate retrieval and constrained selection;
- a lazy workflow dispatcher and capability handoffs;
- declarative multi-workflow plans;
- budgets, permissions, approvals, confidence, and route traces;
- agent profiles, sessions, and coding-agent drivers;
- process adapters, output codecs, and provider SDK integrations;
- standard domain actions such as `handoff`, `needs_input`, or `failed`.

Caskada v3 supplies arbitrary named actions, an unlabelled edge, one shared run
state, branch inputs, terminal outputs, nested flows, and lossless terminal
forwarding. The higher layer should define its protocol in data rather than
expanding Caskada's action vocabulary.

## Recommended boundary

```text
Caskada v3
  graph definition and inspection
  invocation-safe execution
  node(handler) / Flow / context.state / typed context.input
  buffered context.emit and context.end control with implicit default
  node.link topology, Flow output aggregation, and simple/advanced result surfaces

Jig Graph incubation
  workflow and path contracts
  runtime-neutral definition model
  SemanticRouterNode and route catalogue
  Caskada compiler/adapter

Jig incubation
  coding-agent drivers and profiles
  workflow registry and discovery
  planner and dispatcher
  permissions, budgets, persistence, and tracing
```

This boundary lets Jig author workflows without exposing Caskada plumbing while
Caskada gains only the general graph capabilities that its own tooling and
execution model need.

## Current v3 release gates

RFC 0001 is the sole normative authority for release readiness. Its
[release gates](rfcs/0001-caskada-v3-runtime.md#release-gates) apply as written;
this verdict intentionally does not maintain a second list that could drift.
The cookbook simulations and their independent diff reviews are supporting
design evidence, not substitutes for executable conformance.

No semantic-router package is a Caskada v3 release gate.

## Historical appendix: original court decision

The following was the controlling decision before the clean-sheet v3 brief. It
is retained as the Jig-origin review record, not as the current API specification.
Everything from this heading to the end of the document is non-normative.
Names and mechanisms below, including `prep`, `exec`, `post`, `trigger`, `on`,
`next`, `connect`, returned decisions, cloning, branch-state copies, and
terminal-state projections, are historical evidence and cannot override the
current ledger or RFC.

Caskada v3 should admit two architectural changes:

1. A read-only, cross-language view of outgoing graph connections.
2. A cross-language execution-isolation contract that makes reusable graph
   definitions safe across invocations and gives cloning the same observable
   semantics in Python and TypeScript.

Semantic routing, route contracts, workflow manifests, declarative workflow
documents, registries, planners, coding-agent drivers, and provider adapters do
not belong in Caskada core. They should incubate in Jig/Jig Graph. A Caskada-owned
semantic-router package is premature until that API has real users and shared
conformance fixtures.

This is intentionally not a decision about whether a feature makes Caskada a
better backend for Jig. The admission test is whether it makes Caskada a better
general-purpose, dependency-free graph runtime while preserving its small set of
abstractions.

## Record and method

There is no Jig implementation. The supplied design conversation is the complete
proposal considered by this review.

The review used separate clerk, defense, prosecution, rebuttal, and jury passes.
Each candidate had to pass these gates:

1. It has value outside Jig, semantic routing, and LLM applications.
2. It represents graph structure or execution semantics rather than an
   application pattern.
3. It preserves the `Node`, `Flow`, and `Memory` mental model.
4. It requires no provider or runtime dependency.
5. It has equivalent Python and TypeScript semantics, including browser-safe
   TypeScript.
6. It composes with fan-out, cycles, nested flows, and parallel flows.
7. It cannot already be implemented cleanly above the current public API.
8. Its maintenance and source-size costs are justified by broad utility.

The controlling principles come from Caskada's own documentation: modularity,
explicitness, separation of concerns, minimalism, and resilience
([core principles](core_abstraction/index.md#core-philosophy)). The repository
also explicitly positions application patterns and vendor integrations outside
the core ([README](../README.md#how-does-caskada-work),
[utility policy](utility_function/index.md#why-not-built-in)).

## Court docket

| ID  | Proposed change                                                               | Final call      | Placement                              |
| --- | ----------------------------------------------------------------------------- | --------------- | -------------------------------------- |
| C1  | Add read-only outgoing-connection inspection and one portable `Action` domain | Adopt           | Caskada v3 core                        |
| C2  | Store destination-level semantic route metadata on `BaseNode` or `Flow`       | Do not adopt    | Jig Graph incubation                   |
| C3  | Store semantic route metadata on Caskada edges or action groups               | Do not adopt    | Jig Graph incubation                   |
| C4  | Define a Caskada-owned serializable `RouteMetadata` or `RouteContract`        | Do not adopt    | Jig Graph protocol                     |
| C5  | Add a core `DecisionStrategy` callback                                        | Reject          | Extension-local interface              |
| C6  | Add `RouterNode` to Caskada                                                   | Incubate        | Jig Graph subclass                     |
| C7  | Add provider-neutral `SemanticRouterNode` behavior                            | Incubate        | Jig Graph extension                    |
| C8  | Add a special catalogue-router flow primitive                                 | No change       | Already expressible as a nested `Flow` |
| C9  | Add `router.route(...)` to Caskada                                            | Do not adopt    | Router-extension helper                |
| C10 | Standardize edge-over-destination metadata precedence                         | Do not adopt    | Router-contract policy                 |
| C11 | Add public graph or route-catalogue sealing                                   | Reject in core  | Extension may freeze its own catalogue |
| C12 | Ship an official Caskada semantic-router package in v3                        | Defer           | Incubate until promotion gates pass    |
| C13 | Isolate invocation state and define cross-language clone semantics            | Adopt invariant | Caskada v3 core                        |

### C1: Read-only topology inspection

#### Verdict

Adopt a narrow snapshot API on `BaseNode` in both implementations. As part of
that new public surface, export the TypeScript `Action` type.

Today Python exposes a mutable `successors` dictionary
([Python core](../python/caskada.py#L97)), while TypeScript keeps the equivalent
map private and only permits lookup when the action is already known
([TypeScript core](../typescript/caskada.ts#L97)). Official visualization
guidance nevertheless reaches into `node.successors`, and its TypeScript example
treats the private `Map` as an ordinary object
([visualization guide](guides/visualization_logging.md#1-visualizing-the-static-flow-definition)).

This is independently useful for:

- static visualization;
- reachability and cycle analysis;
- graph linting and validation;
- test assertions;
- documentation generators;
- policy and routing extensions.

#### Required shape

The API should expose grouped action-to-target snapshots because one Caskada
action may have several successors:

```python
def successor_entries(
    self,
) -> tuple[tuple[Action, tuple[AnyNode[M], ...]], ...]: ...
```

```typescript
export type Action = string

successorEntries(): ReadonlyArray<
  readonly [Action, readonly BaseNode<GS>[]]
>
```

Names may follow language conventions, but the semantics must match.

#### Action domain parity

C1 also makes `Action` a public cross-language type, which exposes an existing
parity defect: Python accepts `str | None`, while TypeScript accepts only strings.
V3 should normalize both implementations to string-only actions. It should not
add TypeScript `null`: `ExecutionTree` uses object keys, where JavaScript coerces
`null` to the string `"null"`, making it indistinguishable from a real `"null"`
action and unlike Python's `None` key.

Python's `None` action is currently used as an undocumented branch-termination
sentinel in several cookbooks. The migration is:

- omit `trigger()` for a genuine leaf with no default successor;
- use a descriptive string outcome such as `stop`, `skip`, `done`, or `failed`
  when termination is conditional or should propagate;
- connect that outcome to an explicit terminal node when it should be consumed
  inside a flow.

If another v2 release is made, `trigger(None)` and `on(None, ...)` should warn
there before v3 rejects them. C1 does not introduce a reserved null or stop
action.

The returned collections are snapshots. They must not expose the mutable
dictionary, `Map`, or target arrays used by execution. The target node references
themselves remain graph objects; this API is inspection, not serialization or a
deeply immutable graph representation.

`Flow.start` remains the entry relation for a nested flow. Successor inspection
does not flatten nested flows or claim to serialize complete topology.

#### Explicit exclusions

C1 does not include:

- route descriptions or schemas;
- arbitrary node or edge annotations;
- traversal, serialization, or graph compilation;
- mutable connection handles;
- execution-clone identities.

Official tools should migrate to the portable API. Whether Python's existing
direct `successors` access is retained, deprecated, or made private is a separate
compatibility decision; C1 does not decide it.

#### Conformance tests

Both languages must cover string-only action validation, empty nodes, insertion
order, several targets for one action, several actions, snapshot immutability,
cycles without recursive traversal, and nested-flow boundaries.

### C2-C4: Semantic metadata and route contracts

#### Verdict

Keep semantic metadata out of Caskada core.

Destination metadata is incomplete because the same flow can mean different
things on different paths. Edge metadata is more contextual, but Caskada routes
by action and one action may fan out to several physical edges. A semantic
contract can therefore describe an action group, a physical edge, or a target;
those meanings are not interchangeable.

More importantly, fields such as `useWhen`, `avoidWhen`, capabilities, JSON
Schema, eligibility, cost, risk, and input mapping are authoring and selection
policy. Caskada would store them without interpreting or validating them.

Jig Graph should keep these contracts as standalone, readable data and compile
them into an extension-owned route catalogue. That directly serves the proposal's
goal that contracts be easy to find, read, write, and edit rather than hidden in
Caskada object construction.

Even a narrowed, opaque annotation bag is deferred. It may later earn a general
graph API if independent visualization, policy, and documentation tools converge
on a real need. The Jig proposal alone is not sufficient evidence.

### C5: Core decision callback

#### Verdict

Reject a core `DecisionStrategy`.

A `Node` can already hold an injected dependency and use it in `exec()` to compute
a decision; `post()` already triggers one or more actions. A second one-method
abstraction does not add graph capability. It also risks imposing single-choice
semantics on a runtime that deliberately supports multiple triggers and action
fan-out.

A routing extension should define its own small structural protocol, such as
`choose(context, routes) -> decision`, and compose deterministic, human, API
model, or coding-agent implementations behind it.

### C6-C7: Router node classes

#### Verdict

Incubate `RouterNode` and `SemanticRouterNode` outside Caskada.

The inheritance direction remains sound: a one-decision router is a specialized
`Node`; a multi-step routing process is a specialized `Flow`. Intelligence is an
injected dependency, not a provider-specific node subclass.

That does not justify new core classes. Caskada already presents agents, RAG,
map-reduce, and supervisors as patterns made from ordinary nodes and flows. A
universal router still has unresolved policies for context rendering,
eligibility, zero/one/many choices, invalid decisions, argument validation,
fallback, confidence, retries, and tracing.

Jig Graph should prove the reusable lifecycle and contract through implementation.
Caskada can consume the result later without changing graph execution.

### C8: Catalogue router flow

#### Verdict

No Caskada change is needed.

Candidate extraction, retrieval, permission filtering, selection, and validation
are already ordinary nodes that can be composed into a nested `Flow`. Terminal
actions and branch-local data already propagate through nested flows
([Python flow execution](../python/caskada.py#L271),
[TypeScript flow execution](../typescript/caskada.ts#L271)).

Catalogue retrieval and dynamic registry behavior remain control-plane policy.

### C9-C10: Route declaration and metadata precedence

#### Verdict

Keep both in the router extension.

`router.route(action, target, contract)` is useful extension ergonomics: it can
atomically retain a contract and call inherited `on(action, target)`. The rule
that path-local metadata overrides destination defaults is likewise coherent
inside that contract system. Neither rule has meaning to Caskada when C2-C4 are
outside core.

### C11: Sealing and immutability

#### Verdict

Reject a public Caskada `seal()` protocol.

Sealing creates another graph-construction state and restricts incremental
composition. Shallow freezing also gives false safety: it does
not make nested schemas, `Map` values, callbacks, clients, locks, or agent drivers
immutable, and it does not isolate triggers or visit counters.

A router extension may make its own route catalogue immutable after compilation.
C13 must solve Caskada's actual execution-state problem without requiring users
to seal graphs.

### C12: Official semantic-router package

#### Verdict

Do not make the first router implementation an official v3 package.

Official ownership creates a two-language release and compatibility commitment
for behavior that has not yet been implemented. Promotion requires:

1. a working Jig Graph implementation;
2. a second consumer independent of Jig;
3. at least one public API revision driven by real use;
4. shared Python/TypeScript fixtures for invalid choices, fan-out, nested flows,
   fallback, cancellation, and concurrent execution;
5. a provider-neutral surface with no provider runtime dependency;
6. evidence that C1 plus an external route catalogue is insufficient.

Until those gates pass, Caskada may document the integration as a pattern without
owning the package contract.

### C13: Invocation state and clone semantics

#### Verdict

Adopt observable execution-isolation guarantees as a v3 release requirement. Do
not commit yet to a public `cloneAttribute`, `cloneForRun`, or `seal` API.

The current runtime stores framework execution state on reusable objects:

- triggers and the `post()` lock live on `BaseNode`;
- retry position lives on `Node`;
- visit counts live on `Flow`.

Those fields are reset and mutated during execution
([Python lifecycle](../python/caskada.py#L84),
[TypeScript lifecycle](../typescript/caskada.ts#L91)). Concurrent calls using one
flow definition can therefore interfere.

Clone behavior also differs by language. Python deep-copies only list, dictionary,
and set attributes while sharing other objects
([Python clone](../python/caskada.py#L103)). TypeScript shallow-copies every
ordinary custom field before separately cloning successors
([TypeScript clone](../typescript/caskada.ts#L103)). In TypeScript, a cloned nested
flow consequently shares its mutable `visitCounts` `Map`.

Finally, every node visit recursively clones its reachable successor subgraph,
and the next visit repeats that work. A chain can therefore cause quadratic graph
copying even though the graph definition has not changed.

#### V3 execution contract

V3 must guarantee:

1. The same graph definition can be invoked concurrently with independent
   execution state.
2. Framework-owned triggers, locks, retry counters, visit counters, and terminal
   propagation buffers are invocation-local.
3. Framework execution does not mutate its reusable definition topology.
   `link()` remains explicit definition construction, not a dynamic dispatch
   primitive.
4. Each run shallow-copies its caller's top-level input and never mutates that
   caller map through framework routing.
5. One emitted or implicit-default transition transfers its branch map; several
   emissions derive one shallow top-level copy per arm. Nested references remain
   borrowed.
6. Python and TypeScript follow the same documented policy for ordinary subclass
   state and opaque injected dependencies.
7. Configuration and service dependencies are shared by default and must be
   concurrency-safe; invocation data belongs in `Context.state` or private run
   state rather than mutable definition fields.
8. Preparing an invocation traverses topology at most once. A node visit must not
   recursively clone all reachable descendants. Ignoring application work and
   explicit fan-out state copying, runtime graph overhead should be proportional to
   topology plus executed visits, not the sum of every remaining subgraph.
9. Cycles preserve definition identity within one invocation.
10. Root flows, nested flows, serial scopes, and concurrent scopes obey the same
    contract.

#### Required conformance tests

The shared Python/TypeScript suite must include:

- concurrent runs of one compiled flow with different input states;
- concurrent nested and structured-parallel scope runs;
- retry and terminal-action isolation;
- single-transition state transfer and multi-emission branch separation;
- ordinary definition configuration shared by reference with matching
  cross-language behavior and an explicit no-concurrent-mutation precondition;
- a non-copyable or stateful injected client that is intentionally shared;
- compile/traversal instrumentation for chains, fan-out graphs, nested flows,
  and cycles.

#### Resolution in RFC 0001

The court left the mechanism open and, under its then-current compatibility
brief, asked the implementation RFC to compare a per-run execution context, one
definition clone per invocation, and a custom clone hook. It also assumed the v2
lifecycle and `Memory` surface would remain.

The clean-sheet summit removed that compatibility assumption. RFC 0001 selects
compiled placements plus a per-run iterative scheduler, replaces `Memory` with
one invocation-owned shared `Context.state` plus branch `Context.input`, and
removes manual clone behavior entirely.
Its final author layer wraps ordinary functions as nodes, records `emit()` and
`end()` calls in an invocation-local buffer, preserves zero-emission default
progression, and exposes `run()` as the successful-state projection over the
structured outcome available through `start()`. The current RFC independently
carries forward the useful observable goals: concurrent invocation isolation,
configuration and dependency sharing by reference, one shared run state,
branch-specific inputs and outputs, cycle identity, nested-scope parity, and
topology-plus-activation complexity.

## V2 capabilities considered by the original court

Several ideas in the proposal were already present when the original court met
and were not counted as additions under that compatibility-constrained brief:

| Idea                                                      | V2 mechanism at time of review             |
| --------------------------------------------------------- | ------------------------------------------ |
| Pass selected-route arguments locally                     | `trigger(action, forkingData)`             |
| Propagate an unhandled terminal action from a nested flow | Existing terminal-action propagation       |
| Route to either a node or a flow                          | Both are graph elements through `BaseNode` |
| Build a multi-stage routing process                       | Compose ordinary nodes in a nested `Flow`  |

The `Flow extends Node` premise was factually incorrect for v2. `Node` and `Flow`
were sibling subclasses of `BaseNode`; `ParallelFlow` extended `Flow`
([Python hierarchy](../python/caskada.py#L200),
[TypeScript hierarchy](../typescript/caskada.ts#L190)). Making `Flow` inherit the
retrying `Node` would have added irrelevant retry state and encouraged retrying a
partially completed flow whose global memory already contained side effects.
V3 resolves the question with sibling graph elements and structured Flow scope;
a Flow remains node-like at a parent boundary without becoming a `Node`.
