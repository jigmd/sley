# RFC 0001: Caskada v3 Structured Graph Runtime

- Status: accepted implementation baseline
- Revision: D10
- Target: Caskada v3.0
- Date: 2026-08-21
- Supersedes: the v2 execution API and the compatibility constraints preserved
  in the historical appendix of the
  [v3 architecture verdict](../v3-architecture-verdict.md)

## Decision

Caskada v3 will remain Caskada and remain an in-process, dependency-free graph
runtime. It will replace the stateful, recursively cloned v2 runner with a
compiled topology and an invocation-local structured scheduler.

The complete everyday model is:

1. `node(...)` turns an ordinary function into a graph node.
2. `context.state` holds workflow state; `context.input` is this branch's input.
3. A handler calls `emit` to continue, calls `end` to finish a branch, calls
   `emit` or `end` repeatedly to fan out, or makes no control call to follow its
   unlabelled link.
4. `source.link(...)` connects nodes and nested Flows.
5. A `Flow` runs the connected work, waits for every branch, and returns state.

Everything else is a consequence of those five ideas. Compilation, retries,
parallelism, limits, events, and results make execution reliable; they do not
create another authoring model.

The runtime's real distinctions remain visible: route versus terminal, scalar
continuation versus fan-out, shared workflow state versus branch input/output,
and definition versus invocation. They are expressed through one
invocation-local emission verb instead of exported control constructors.
Routine modules import `node` and `Flow`; they do not import `Go`, `NEXT`,
`End`, `Fork`, a decision class, or a patch class.

This is an intentionally breaking release. Caskada has no production adoption
that justifies preserving accidental v2 complexity. V3 optimizes for the API we
would choose from a clean sheet while retaining Caskada's essential idea:
ordinary code connected as an action-routed graph.

## Implementation baseline

D10 is closed for implementation. Its authoritative file hashes are recorded in
`internal/v3-implementation-baseline.json`, and the executable serial contract
lives in `conformance/`. Runtime work may reveal defects, but neither port may
silently reinterpret this document: a semantic change requires an RFC amendment
and an exact shared conformance-fixture diff first.

This acceptance is not a release claim. Phase 0 establishes the executable
serial contract before production runtime work, while the release gates below
remain criteria for shipping v3 after implementation.

## Quality bar

The design is acceptable only if it remains:

- **Approachable:** the complete everyday model fits in the five points above;
  a linear flow, branch, loop, fan-out, and nested flow are evident from code.
- **Architecturally rigorous:** branch cardinality, scope ownership, retries,
  failure, cancellation, parallelism, and complexity have one defined answer.
- **Actionable:** Python and TypeScript expose equivalent APIs and share
  behavioral fixtures before either implementation is released.

The core remains zero-dependency. TypeScript remains browser-safe. Persistence,
distributed execution, semantic routing, provider integrations, and workflow
authoring languages stay outside core.

## The one-page model

```text
definition                    invocation

Node --action--> Node         compile once
  \             /                  |
   \-> Flow ---/              schedule branch activations
                                   |
Context                           successful settlement
  state        this run             no emit -> unlabelled route
  input        this branch          emit(action?, input?)
  cancellation this callback        emit(action?) -> one route
  identity     this activation       emit(...) x N -> fan-out
                                    end() -> hard terminal, no output
                                    end(output) -> hard terminal output
                                   |
                              settle terminal outputs
```

A graph definition stores configuration and links. It stores no attempt,
trigger, visit, lock, or cancellation state. `compile()` snapshots topology.
Every run creates new scopes, activations, counters, cancellation sources, and
terminal records.

Execution is serial when every Flow keeps its default `concurrency=1`.
Parallelism is an explicit Flow policy; the omitted run-wide callback limit is
derived from the compiled topology. One mutable top-level state map belongs to
the run and is shared by every branch. Fan-out copies only control records and
branch input references. Nested values are ordinary host-language references.
Caskada does not pretend that concurrent mutation of arbitrary Python or
JavaScript objects is transactional, isolated, or race-free.

The everyday grammar fits on five lines:

```text
context.state                    read or change persistent workflow state
context.input                    read this branch's input
context.emit("review", x)        emit one named-action branch input
context.end()                    hard-end one branch without an output
context.end(y)                   emit one hard terminal output
no emission                      follow the unlabelled link, forwarding input
```

Emission records intent; it neither schedules work nor stops the callback.
Only a successful `None` / `undefined` return commits the complete buffer.
Any other callback return is invalid. A throw, timeout, or cancellation discards
the buffer. Control calls are ordinary statements; use a separate host-language
`return` only when the callback must stop evaluating more application code.

## Vocabulary and naming

| V2                          | V3                                     | Decision                                                                         |
| --------------------------- | -------------------------------------- | -------------------------------------------------------------------------------- |
| `prep`, `exec`, `post`      | `node(handler)`                        | Collapse three framework phases into one ordinary function callback.             |
| `exec_fallback`             | `recover`                              | Recovery is explicit and runs once after retry stops.                            |
| `trigger(...)`              | `context.emit(...)` or `context.end()` | Routing intent is explicit and invocation-local without public decision objects. |
| `on`, `next`                | `link`                                 | One full word covers unlabelled and named-action edges.                          |
| global/local `Memory` proxy | `context.state` plus `context.input`   | Persistent run state and branch messages have distinct, non-overlapping roles.   |
| `Flow.start` field          | `Flow.entry`                           | Frees `start()` for starting a run.                                              |
| `ParallelFlow`              | `Flow(concurrency=...)`                | Parallelism is policy, not another graph type.                                   |
| recursive `clone()`         | `compile()`                            | Topology is captured once; definitions are not copied per visit.                 |
| `ExecutionTree` result      | events plus `describe()`               | Tracing is opt-in and does not grow every result.                                |

`Node` and `Flow` remain sibling graph elements. A flow is node-like when placed
inside another flow, but it is not a retrying `Node` subclass.

The Python operator DSL (`>>` and `- "action" >>`) is removed. It has no natural
TypeScript equivalent and hides which object owns a connection. The portable
spelling is:

```text
classify.link(build, "build")
build.link(review)
```

```text
classify.link(build, "build");
build.link(review);
```

Terminology is exact throughout this RFC: an **action** is the optional string
selected by `emit`; a **link** is the definition-time action-to-target
relationship; a **route** is the runtime movement that resolves an emission
through a link or Flow exit; and an **arm** is one item in an internal atomic
fan-out batch. “Unlabelled” means the private absence of an action, not a
reserved string.

## First workflow

The ordinary runtime path needs only `node` and `Flow`; the optional `Context`
import below gives static state checking:

```python
from typing import NotRequired, TypedDict

from caskada import Context, Flow, node


class AnswerState(TypedDict):
    question: str
    answer: NotRequired[str]


async def answer_question(question: str) -> str:
    return question.upper()


async def review_answer(answer: str) -> None:
    assert answer


@node
async def answer(context: Context[AnswerState]) -> None:
    context.state["answer"] = await answer_question(
        context.state["question"],
    )
    # No control call follows the unlabelled link.


@node
async def review(context: Context[AnswerState]) -> None:
    answer_value = context.state.get("answer")
    if answer_value is None:
        raise ValueError("answer is missing")
    await review_answer(answer_value)
    # No control call exits the root Flow.


answer.link(review)


async def main() -> None:
    initial_state: AnswerState = {"question": "Why?"}
    state = await Flow(answer).run(initial_state)
    assert state.get("answer")
```

The same path in TypeScript has the same two framework imports:

```typescript
import { Flow, node } from 'caskada'

interface AnswerState {
  question: string
  answer?: string
}

async function answerQuestion(question: string): Promise<string> {
  return question.toUpperCase()
}

async function reviewAnswer(answer: string): Promise<void> {
  if (!answer) throw new Error('empty answer')
}

const answer = node<AnswerState>(async (context) => {
  context.state.answer = await answerQuestion(context.state.question)
  // No control call follows the unlabelled link.
})

const review = node<AnswerState>(async (context) => {
  const answerValue = context.state.answer
  if (answerValue === undefined) throw new Error('answer is missing')
  await reviewAnswer(answerValue)
  // No control call exits the root Flow.
})

answer.link(review)
const state = await new Flow<AnswerState>(answer).run({ question: 'Why?' })
```

`run()` waits for every branch and returns the run's one state. Authors add
`context.input` only when a branch carries its own value, call `emit("action")`
only when choosing a named path, and call `emit` repeatedly only when creating
fan-out.

The next two sections are the exhaustive cross-language implementation surface,
including advanced failure and observation types. They are normative for core
implementers and tooling, not an import list for ordinary workflows. The
author-focused narrative resumes at [Definition and compilation](#definition-and-compilation)
and [Examples](#examples).

## Normative Python surface

The following public shape, including its generic relationships and defaults,
is normative.

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import (
    Awaitable,
    Callable,
    Sequence,
)
from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    TypedDict,
    final,
    overload,
)


Action: TypeAlias = str
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_PORTABLE_COLLECTION_LENGTH = 4_294_967_295
RUN_EVENT_SCHEMA_VERSION = 1

T = TypeVar("T")
StateT = TypeVar("StateT", default=dict[str, Any])
InputT = TypeVar("InputT", default=object)
ContextStateT_co = TypeVar(
    "ContextStateT_co",
    covariant=True,
    default=dict[str, Any],
)
ContextInputT_co = TypeVar(
    "ContextInputT_co",
    covariant=True,
    default=object,
)
MaybeAwaitable: TypeAlias = T | Awaitable[T]


class CaskadaError(Exception):
    pass


class GraphDefinitionError(CaskadaError):
    pass


class DuplicateLinkError(GraphDefinitionError):
    pass


class OptionValidationError(CaskadaError):
    pass


class Cancellation(Protocol):
    @property
    def cancelled(self) -> bool: ...

    @property
    def reason(self) -> Any: ...

    async def wait(self) -> None: ...

    def raise_if_cancelled(self) -> None: ...


Phase: TypeAlias = Literal[
    "handle",
    "node_recover",
    "flow_combine",
    "flow_recover",
]


class Context(Protocol, Generic[ContextStateT_co, ContextInputT_co]):
    @property
    def state(self) -> ContextStateT_co: ...

    @property
    def input(self) -> ContextInputT_co: ...

    @property
    def run_id(self) -> str: ...

    @property
    def scope_id(self) -> int: ...

    @property
    def activation_id(self) -> int: ...

    @property
    def parent_activation_id(self) -> int | None: ...

    @property
    def attempt(self) -> int | None: ...

    @property
    def phase(self) -> Phase: ...

    @property
    def cancellation(self) -> Cancellation: ...

    def remaining_ms(self) -> int | None: ...

    @overload
    def emit(
        self,
    ) -> None: ...

    @overload
    def emit(
        self,
        *,
        input: object,
    ) -> None: ...

    @overload
    def emit(
        self,
        action: Action,
        /,
    ) -> None: ...

    @overload
    def emit(
        self,
        action: Action,
        /,
        input: object,
    ) -> None: ...

    @overload
    def end(
        self,
    ) -> None: ...

    @overload
    def end(self, output: object) -> None: ...

    @overload
    def report(self, name: str) -> None: ...

    @overload
    def report(self, name: str, data: object) -> None: ...


FailureKind: TypeAlias = Literal[
    "handler",
    "handler_timeout",
    "retry_policy",
    "node_recovery",
    "flow_combine",
    "flow_recovery",
    "invalid_outcome",
    "invalid_combination",
    "unknown_action",
    "limit",
    "internal",
]


InvalidOutcomeReason: TypeAlias = Literal[
    "wrong_return_type",
    "invalid_action",
    "invalid_control_arguments",
    "report_name",
]
InvalidCombinationReason: TypeAlias = Literal[
    "wrong_return_type",
    "invalid_action",
    "invalid_control_arguments",
    "report_name",
]
LimitName: TypeAlias = Literal[
    "max_activations",
    "scope_max_activations",
    "max_attempts",
    "max_transitions",
    "max_ready",
    "max_reports",
    "max_depth",
    "portable_collection",
    "safe_integer",
]
InternalReason: TypeAlias = Literal[
    "orphaned_live_token",
    "packet_registry",
    "counter_invariant",
    "scheduler_invariant",
]


@dataclass(frozen=True, slots=True)
class InvalidOutcomeDetail:
    reason: InvalidOutcomeReason
    type: Literal["invalid_outcome"] = field(
        default="invalid_outcome",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class InvalidCombinationDetail:
    reason: InvalidCombinationReason
    type: Literal["invalid_combination"] = field(
        default="invalid_combination",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class UnknownActionDetail:
    action: Action
    type: Literal["unknown_action"] = field(
        default="unknown_action",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class LimitDetail:
    limit: LimitName
    type: Literal["limit"] = field(default="limit", init=False)


@dataclass(frozen=True, slots=True)
class InternalDetail:
    reason: InternalReason
    type: Literal["internal"] = field(default="internal", init=False)


FailureDetail: TypeAlias = (
    InvalidOutcomeDetail
    | InvalidCombinationDetail
    | UnknownActionDetail
    | LimitDetail
    | InternalDetail
)


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Failure:
    failure_id: int
    kind: FailureKind
    message: str
    cause: BaseException | None
    scope_id: int
    activation_id: int | None
    element_id: int | None
    attempt: int | None
    detail: FailureDetail | None
    previous: Failure | None = None

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class EndTerminal:
    has_output: bool
    output: object
    sequence: int
    source_activation_id: int
    type: Literal["end"] = field(default="end", init=False)

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ExitTerminal:
    action: Action | None
    output: object
    sequence: int
    source_activation_id: int
    has_output: Literal[True] = field(default=True, init=False)
    type: Literal["exit"] = field(default="exit", init=False)

    def __repr__(self) -> str: ...


Terminal: TypeAlias = EndTerminal | ExitTerminal
NonEmptyTerminals: TypeAlias = tuple[
    Terminal,
    *tuple[Terminal, ...],
]


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ScopeResult:
    terminals: NonEmptyTerminals
    outputs: tuple[object, ...]

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ScopeFailure:
    primary: Failure
    suppressed: Sequence[Failure]
    settled_before_fence: tuple[Terminal, ...]
    result: ScopeResult | None
    failing_activation_id: int | None

    def __repr__(self) -> str: ...


NodeHandler: TypeAlias = Callable[
    [Context[StateT, InputT]],
    MaybeAwaitable[None],
]
NodeRecoveryHandler: TypeAlias = Callable[
    [Context[StateT, InputT], Failure],
    MaybeAwaitable[None],
]
FlowCombineHandler: TypeAlias = Callable[
    [Context[StateT, object], ScopeResult],
    MaybeAwaitable[None],
]
FlowRecoveryHandler: TypeAlias = Callable[
    [Context[StateT, object], ScopeFailure],
    MaybeAwaitable[None],
]


def _retry_all(_failure: Failure) -> bool:
    return True


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    should_retry: Callable[[Failure], bool] = _retry_all
    delay_ms: int | Callable[[int, Failure], int] = 0

    def __post_init__(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RunStartedPayload:
    root_element_id: int
    root_activation_id: int


@dataclass(frozen=True, slots=True)
class RunFinishedPayload:
    status: Literal["completed", "failed", "cancelled", "abandoned"]


@dataclass(frozen=True, slots=True)
class ScopeStartedPayload:
    scope_id: int
    parent_scope_id: int | None
    owner_activation_id: int
    entry_activation_id: int
    entry_element_id: int
    flow_element_id: int
    depth: int


@dataclass(frozen=True, slots=True)
class ScopeFinishedPayload:
    scope_id: int
    status: Literal["completed", "failed", "cancelled", "abandoned"]
    terminal_sequences: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CallbackStartedPayload:
    scope_id: int
    activation_id: int
    parent_activation_id: int | None
    element_id: int
    phase: Phase
    attempt: int | None


@dataclass(frozen=True, slots=True)
class CallbackOutcomeDisposition:
    kind: Literal["outcome"]
    outcome: Literal[
        "route",
        "fanout",
        "end",
        "forward",
        "unhandled",
    ]


@dataclass(frozen=True, slots=True)
class FailureDisposition:
    kind: Literal["failure"]
    failure: Failure


@dataclass(frozen=True, slots=True)
class DiscardedDisposition:
    kind: Literal["discarded"]


CallbackDisposition: TypeAlias = (
    CallbackOutcomeDisposition | FailureDisposition | DiscardedDisposition
)


@dataclass(frozen=True, slots=True)
class CallbackFinishedPayload:
    scope_id: int
    activation_id: int
    phase: Phase
    attempt: int | None
    disposition: CallbackDisposition


@dataclass(frozen=True, slots=True)
class RetryScheduledPayload:
    scope_id: int
    activation_id: int
    failure_id: int
    failed_attempt: int
    next_attempt: int
    delay_ms: int


@dataclass(frozen=True, slots=True)
class ActivationDestination:
    activation_id: int
    element_id: int
    type: Literal["activation"] = field(default="activation", init=False)


@dataclass(frozen=True, slots=True)
class TerminalDestination:
    sequence: int
    type: Literal["terminal"] = field(default="terminal", init=False)


@dataclass(frozen=True, slots=True)
class RoutedTransition:
    kind: Literal["route", "forward_exit"]
    action: Action | None
    destination: ActivationDestination | TerminalDestination


@dataclass(frozen=True, slots=True)
class EndTransition:
    kind: Literal["end", "forward_end"]
    destination: TerminalDestination


Transition: TypeAlias = RoutedTransition | EndTransition


@dataclass(frozen=True, slots=True)
class TransitionCommittedPayload:
    scope_id: int
    source_activation_id: int
    branch_index: int
    transition: Transition


@dataclass(frozen=True, slots=True)
class EndTerminalMetadata:
    has_output: bool
    kind: Literal["end"] = field(default="end", init=False)


@dataclass(frozen=True, slots=True)
class ExitTerminalMetadata:
    action: Action | None
    has_output: Literal[True] = field(default=True, init=False)
    kind: Literal["exit"] = field(default="exit", init=False)


TerminalMetadata: TypeAlias = EndTerminalMetadata | ExitTerminalMetadata


@dataclass(frozen=True, slots=True)
class TerminalCommittedPayload:
    scope_id: int
    terminal_sequence: int
    source_activation_id: int
    terminal: TerminalMetadata


@dataclass(frozen=True, slots=True)
class RunFenceTarget:
    kind: Literal["run"] = field(default="run", init=False)


@dataclass(frozen=True, slots=True)
class ScopeFenceTarget:
    scope_id: int
    kind: Literal["scope"] = field(default="scope", init=False)


@dataclass(frozen=True, slots=True)
class AttemptFenceTarget:
    scope_id: int
    activation_id: int
    attempt: int
    kind: Literal["attempt"] = field(default="attempt", init=False)


FailureFenceTarget: TypeAlias = RunFenceTarget | ScopeFenceTarget
CancellationFenceTarget: TypeAlias = (
    RunFenceTarget | ScopeFenceTarget | AttemptFenceTarget
)


@dataclass(frozen=True, slots=True)
class FailureFencedPayload:
    target: FailureFenceTarget
    failure: Failure


@dataclass(frozen=True, slots=True)
class FailureRecordedPayload:
    failure: Failure


@dataclass(frozen=True, slots=True)
class CancellationFencedPayload:
    target: CancellationFenceTarget
    reason: Any
    deadline: bool


@dataclass(frozen=True, slots=True)
class ReportWithoutDataPayload:
    scope_id: int
    activation_id: int
    name: str
    has_data: Literal[False] = field(default=False, init=False)
    data: None = field(default=None, init=False)


@dataclass(frozen=True, slots=True)
class ReportWithDataPayload:
    scope_id: int
    activation_id: int
    name: str
    data: object
    has_data: Literal[True] = field(default=True, init=False)


ReportPayload: TypeAlias = ReportWithoutDataPayload | ReportWithDataPayload


@dataclass(frozen=True, slots=True)
class RunStartedEvent:
    sequence: int
    run_id: str
    payload: RunStartedPayload
    kind: Literal["run_started"] = field(default="run_started", init=False)


@dataclass(frozen=True, slots=True)
class RunFinishedEvent:
    sequence: int
    run_id: str
    payload: RunFinishedPayload
    kind: Literal["run_finished"] = field(default="run_finished", init=False)


@dataclass(frozen=True, slots=True)
class ScopeStartedEvent:
    sequence: int
    run_id: str
    payload: ScopeStartedPayload
    kind: Literal["scope_started"] = field(default="scope_started", init=False)


@dataclass(frozen=True, slots=True)
class ScopeFinishedEvent:
    sequence: int
    run_id: str
    payload: ScopeFinishedPayload
    kind: Literal["scope_finished"] = field(default="scope_finished", init=False)


@dataclass(frozen=True, slots=True)
class CallbackStartedEvent:
    sequence: int
    run_id: str
    payload: CallbackStartedPayload
    kind: Literal["callback_started"] = field(
        default="callback_started",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class CallbackFinishedEvent:
    sequence: int
    run_id: str
    payload: CallbackFinishedPayload
    kind: Literal["callback_finished"] = field(
        default="callback_finished",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class RetryScheduledEvent:
    sequence: int
    run_id: str
    payload: RetryScheduledPayload
    kind: Literal["retry_scheduled"] = field(
        default="retry_scheduled",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class TransitionCommittedEvent:
    sequence: int
    run_id: str
    payload: TransitionCommittedPayload
    kind: Literal["transition_committed"] = field(
        default="transition_committed",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class TerminalCommittedEvent:
    sequence: int
    run_id: str
    payload: TerminalCommittedPayload
    kind: Literal["terminal_committed"] = field(
        default="terminal_committed",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class FailureFencedEvent:
    sequence: int
    run_id: str
    payload: FailureFencedPayload
    kind: Literal["failure_fenced"] = field(default="failure_fenced", init=False)


@dataclass(frozen=True, slots=True)
class FailureRecordedEvent:
    sequence: int
    run_id: str
    payload: FailureRecordedPayload
    kind: Literal["failure_recorded"] = field(
        default="failure_recorded",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class CancellationFencedEvent:
    sequence: int
    run_id: str
    payload: CancellationFencedPayload
    kind: Literal["cancellation_fenced"] = field(
        default="cancellation_fenced",
        init=False,
    )


@dataclass(frozen=True, slots=True)
class ReportEvent:
    sequence: int
    run_id: str
    payload: ReportPayload
    kind: Literal["report"] = field(default="report", init=False)


RunEvent: TypeAlias = (
    RunStartedEvent
    | RunFinishedEvent
    | ScopeStartedEvent
    | ScopeFinishedEvent
    | CallbackStartedEvent
    | CallbackFinishedEvent
    | RetryScheduledEvent
    | TransitionCommittedEvent
    | TerminalCommittedEvent
    | FailureRecordedEvent
    | FailureFencedEvent
    | CancellationFencedEvent
    | ReportEvent
)


Observer: TypeAlias = Callable[[RunEvent], None]


@dataclass(frozen=True, slots=True)
class RunOptions:
    max_concurrency: int | None = None
    max_activations: int = 100_000
    max_attempts: int = 200_000
    max_transitions: int = 200_000
    max_ready: int = 100_000
    max_reports: int = 100_000
    max_depth: int = 32
    deadline_ms: int | None = None
    cancel_grace_ms: int = 1_000
    observer: Observer | None = None
    run_id: str | None = None

    def __post_init__(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RunStats:
    activations: int
    attempts: int
    transitions: int
    retries: int
    reports: int
    scopes: int
    peak_ready: int
    peak_callbacks: int
    duration_ms: int


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ObserverDiagnostic:
    event_sequence: int
    message: str
    cause: BaseException | None

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class CancellationInfo:
    reason: Any
    deadline: bool

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Completed(Generic[StateT]):
    status: Literal["completed"]
    state: StateT
    terminals: NonEmptyTerminals
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Failed(Generic[StateT]):
    status: Literal["failed"]
    state: StateT
    terminals: tuple[Terminal, ...]
    failure: Failure
    suppressed: tuple[Failure, ...]
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Cancelled(Generic[StateT]):
    status: Literal["cancelled"]
    state: StateT
    terminals: tuple[Terminal, ...]
    cancellation: CancellationInfo
    suppressed: tuple[Failure, ...]
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Abandoned(Generic[StateT]):
    status: Literal["abandoned"]
    state: StateT
    terminals: tuple[Terminal, ...]
    cause: Failure | CancellationInfo
    suppressed: tuple[Failure, ...]
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str: ...


RunResult: TypeAlias = (
    Completed[StateT]
    | Failed[StateT]
    | Cancelled[StateT]
    | Abandoned[StateT]
)


class RunError(CaskadaError, Generic[StateT]):
    def __init__(
        self,
        result: Failed[StateT] | Cancelled[StateT] | Abandoned[StateT],
    ) -> None: ...

    @property
    def result(
        self,
    ) -> Failed[StateT] | Cancelled[StateT] | Abandoned[StateT]: ...


class RunHandle(Protocol, Generic[StateT]):
    def cancel(self, reason: Any = "cancelled") -> None: ...

    def done(self) -> bool: ...

    async def result(self) -> RunResult[StateT]: ...


class GraphElement(ABC, Generic[StateT]):
    @property
    def name(self) -> str: ...

    @property
    @abstractmethod
    def _caskada_kind(self) -> Literal["node", "flow"]: ...

    @overload
    def link(self, target: GraphElement[StateT], /) -> None: ...

    @overload
    def link(
        self,
        target: GraphElement[StateT],
        /,
        action: Action,
    ) -> None: ...

    def links(self) -> tuple[Link[StateT], ...]: ...


@dataclass(frozen=True, slots=True)
class Link(Generic[StateT]):
    action: Action | None
    target: GraphElement[StateT]


class _NodeConstructionToken:
    pass


_NODE_CONSTRUCTION_TOKEN = _NodeConstructionToken()


@final
class Node(GraphElement[StateT], Generic[StateT]):
    def __new__(
        cls,
        token: _NodeConstructionToken,
        /,
    ) -> Node[StateT]:
        if token is not _NODE_CONSTRUCTION_TOKEN:
            raise TypeError("Use node(handler) to create a Node")
        return super().__new__(cls)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("Node is final; wrap a handler with node(...)")

    @property
    def _caskada_kind(self) -> Literal["node"]: ...

    @property
    def retry(self) -> RetryPolicy: ...

    @property
    def timeout_ms(self) -> int | None: ...


class Flow(GraphElement[StateT], Generic[StateT]):
    @property
    def entry(self) -> GraphElement[StateT]: ...

    @property
    def exits(self) -> tuple[Action, ...]: ...

    @property
    def concurrency(self) -> int: ...

    @property
    def max_activations(self) -> int | None: ...

    @property
    def _caskada_kind(self) -> Literal["flow"]: ...

    def __init__(
        self,
        entry: GraphElement[StateT],
        *,
        name: str | None = None,
        exits: Sequence[Action] = (),
        concurrency: int = 1,
        max_activations: int | None = None,
        combine: FlowCombineHandler[StateT] | None = None,
        recover: FlowRecoveryHandler[StateT] | None = None,
    ) -> None: ...

    def compile(self) -> CompiledFlow[StateT]: ...

    def start(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> RunHandle[StateT]: ...

    async def run(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> StateT: ...



class CompiledLinkDescription(TypedDict):
    action: Action | None
    target_element_id: int


class CompiledRetryDescription(TypedDict):
    max_attempts: int


class CompiledNodeDescription(TypedDict):
    element_id: int
    kind: Literal["node"]
    name: str
    parent_scope_definition_id: int
    links: list[CompiledLinkDescription]
    retry: CompiledRetryDescription
    timeout_ms: int | None


class CompiledFlowElementDescription(TypedDict):
    element_id: int
    kind: Literal["flow"]
    name: str
    parent_scope_definition_id: int | None
    owned_scope_definition_id: int
    links: list[CompiledLinkDescription]


CompiledElementDescription: TypeAlias = (
    CompiledNodeDescription | CompiledFlowElementDescription
)


class CompiledScopeDescription(TypedDict):
    scope_definition_id: int
    owner_element_id: int
    parent_scope_definition_id: int | None
    entry_element_id: int
    exits: list[Action]
    concurrency: int
    max_activations: int | None


class CompiledRootDescription(TypedDict):
    element_id: int
    scope_definition_id: int


class CompiledDescription(TypedDict):
    schema_version: Literal[1]
    auto_max_concurrency: int
    root: CompiledRootDescription
    scope_definitions: list[CompiledScopeDescription]
    elements: list[CompiledElementDescription]


class _CompiledFlowConstructionToken:
    pass


_COMPILED_FLOW_CONSTRUCTION_TOKEN = _CompiledFlowConstructionToken()


@final
class CompiledFlow(Generic[StateT]):
    def __new__(
        cls,
        token: _CompiledFlowConstructionToken,
        /,
    ) -> CompiledFlow[StateT]:
        if token is not _COMPILED_FLOW_CONSTRUCTION_TOKEN:
            raise TypeError("Use Flow.compile() to create a CompiledFlow")
        return super().__new__(cls)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("CompiledFlow is final; use Flow.compile()")

    def start(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> RunHandle[StateT]: ...

    async def run(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> StateT: ...


    def describe(self) -> CompiledDescription: ...


@overload
def node(
    handler: NodeHandler[StateT, InputT],
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Node[StateT]: ...


@overload
def node(
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Callable[[NodeHandler[StateT, InputT]], Node[StateT]]: ...
```

`Node` is a graph occurrence, not a class authors subclass. `node(handler)`
wraps reusable behavior with occurrence identity, retry/timeout policy, an
optional recovery callback, and outgoing links. Each `@node` decoration creates
one topology-bearing occurrence; decorating a function does not define a
reusable occurrence factory. Reusable behavior stays undecorated and every graph
factory calls `node(handler)` to obtain a fresh occurrence and fresh links.
Python also supports `@node` and `@node(...)`; the undecorated function name is
the default node name.
The accepted handler and recovery callback references are internal definition
data, not callable Node introspection properties; exposing them after input-type
erasure would falsely claim they accept arbitrary branch inputs. Retry and
timeout configuration remains readable, and compiled metadata remains
available through `describe()`.
`Node` is final in both ports. Its constructor requires a private, unexported
runtime token, direct public construction fails, and Python's subclass hook
raises; `node(...)` is the only public constructor.
`GraphElement` is an abstract typing surface, not an extension point. Compilation
accepts only runtime `Node` and `Flow` instances and rejects every unknown
subclass in both ports; higher layers compose or wrap those two elements instead
of inventing a third kernel kind.
`Context`, `Cancellation`, and `RunHandle` are runtime-issued capability
protocols backed by private implementations; they expose no public constructor.
Callbacks and `start()` are their only issuers. `CompiledFlow` is final and
factory-only: `Flow.compile()` supplies its private construction token, while
direct construction and subclassing fail.
Synchronous and asynchronous callbacks are accepted. A synchronous callback
blocks the event loop and cannot be preempted.

Python's identity-bearing Failure, terminal, scoped-result, diagnostic,
cancellation, and run-result records have `eq=False`, matching TypeScript
reference identity. Their custom `repr` is bounded and never renders workflow
state, input/output values, causes/reasons, action/detail values, terminal or
output-projection/suppression collections, or the recursive `previous` chain. It
includes only framework discriminators, numeric IDs/counts, and canonical messages. Logging
any selected record is therefore O(1) and cannot recurse through application
data or failure ancestry.

`StateT` defaults to `dict[str, Any]` and `InputT` defaults to `object`, so
untyped everyday code needs only `@node` and imports `node`. Typed authors may
use a `TypedDict` and annotate `Context[ProjectState, WorkItem]`; `node()` infers
both callback types but returns `Node[ProjectState]`. The invariant state
parameter rejects incompatible links, Flow entries, initial state, results, and
projected state. The input parameter is deliberately erased from topology:
actions may carry different payload types, and core performs no action/link
payload compatibility proof. This is progressive disclosure for local callback
reads, not another runtime data role. `StateT` is deliberately unbounded because
current Python type checkers do not consistently treat `TypedDict` as a
`Mapping` bound; runtime still requires the initial value to satisfy the mapping
contract.

The runtime state carrier is an ordinary `dict`, so its behavior matches the
`TypedDict`/dictionary type authors see. `StateT` is a static record type with no
runtime schema effect:
supported typed forms are `TypedDict`, `dict[str, ...]`, and equivalent data-only
record types, not
preservation of an arbitrary source Mapping subclass or a method-bearing domain
class. Run capture always normalizes the top-level source container as specified
below.

The distinct covariant Context-only type variables make its read-only
`state`/`input` properties valid under strict mypy and Pyright. Topology,
links, Flow entry, results, and run arguments continue using invariant `StateT`;
Context covariance cannot weaken graph state compatibility.

## Normative TypeScript surface

```typescript
export const MAX_SAFE_INTEGER = 9_007_199_254_740_991
export const MAX_PORTABLE_COLLECTION_LENGTH = 4_294_967_295
export const RUN_EVENT_SCHEMA_VERSION = 1

export class CaskadaError extends Error {}
export class GraphDefinitionError extends CaskadaError {}
export class DuplicateLinkError extends GraphDefinitionError {}
export class OptionValidationError extends CaskadaError {}

export type Action = string
export type Phase = 'handle' | 'node_recover' | 'flow_combine' | 'flow_recover'

declare const stateInvariant: unique symbol
declare const nodeConstructionToken: unique symbol
declare const compiledFlowConstructionToken: unique symbol

export interface Cancellation {
  readonly cancelled: boolean
  readonly reason: unknown
  readonly signal: AbortSignal
  throwIfCancelled(): void
}

export interface Context<State extends object = Record<string, unknown>, Input = unknown> {
  readonly state: State
  readonly input: Input
  readonly runId: string
  readonly scopeId: number
  readonly activationId: number
  readonly parentActivationId: number | null
  readonly attempt: number | null
  readonly phase: Phase
  readonly cancellation: Cancellation
  remainingMs(): number | undefined
  emit(): void
  emit(unlabelled: { readonly input: unknown }): void
  emit(action: Action): void
  emit(action: Action, input: unknown): void
  end(): void
  end(output: unknown): void
  report(name: string, data?: unknown): void
}

export type FailureKind =
  | 'handler'
  | 'handler_timeout'
  | 'retry_policy'
  | 'node_recovery'
  | 'flow_combine'
  | 'flow_recovery'
  | 'invalid_outcome'
  | 'invalid_combination'
  | 'unknown_action'
  | 'limit'
  | 'internal'

export type InvalidOutcomeReason = 'wrong_return_type' | 'invalid_action' | 'invalid_control_arguments' | 'report_name'

export type InvalidCombinationReason = 'wrong_return_type' | 'invalid_action' | 'invalid_control_arguments' | 'report_name'

export type LimitName =
  | 'max_activations'
  | 'scope_max_activations'
  | 'max_attempts'
  | 'max_transitions'
  | 'max_ready'
  | 'max_reports'
  | 'max_depth'
  | 'portable_collection'
  | 'safe_integer'

export type InternalReason = 'orphaned_live_token' | 'packet_registry' | 'counter_invariant' | 'scheduler_invariant'

export type FailureDetail =
  | { readonly type: 'invalid_outcome'; readonly reason: InvalidOutcomeReason }
  | {
      readonly type: 'invalid_combination'
      readonly reason: InvalidCombinationReason
    }
  | { readonly type: 'unknown_action'; readonly action: Action }
  | { readonly type: 'limit'; readonly limit: LimitName }
  | { readonly type: 'internal'; readonly reason: InternalReason }

export interface Failure {
  readonly failureId: number
  readonly kind: FailureKind
  readonly message: string
  readonly cause: unknown | null
  readonly scopeId: number
  readonly activationId: number | null
  readonly elementId: number | null
  readonly attempt: number | null
  readonly detail: FailureDetail | null
  readonly previous: Failure | null
}

interface EndTerminalBase {
  readonly type: 'end'
  readonly sequence: number
  readonly sourceActivationId: number
}

export type EndTerminal = EndTerminalBase &
  ({ readonly hasOutput: false; readonly output: undefined } | { readonly hasOutput: true; readonly output: unknown })

export interface ExitTerminal {
  readonly type: 'exit'
  readonly action: Action | null
  readonly hasOutput: true
  readonly output: unknown
  readonly sequence: number
  readonly sourceActivationId: number
}

export type Terminal = EndTerminal | ExitTerminal
export type NonEmptyTerminals = readonly [Terminal, ...Terminal[]]

export interface ScopeResult {
  readonly terminals: NonEmptyTerminals
  readonly outputs: readonly unknown[]
}

export interface ScopeFailure {
  readonly primary: Failure
  readonly suppressed: readonly Failure[]
  readonly settledBeforeFence: readonly Terminal[]
  readonly result: ScopeResult | null
  readonly failingActivationId: number | null
}

export type NodeHandler<State extends object = Record<string, unknown>, Input = unknown> = (
  context: Context<State, Input>,
) => void | Promise<void>

export type NodeRecoveryHandler<State extends object = Record<string, unknown>, Input = unknown> = (
  context: Context<State, Input>,
  failure: Failure,
) => void | Promise<void>

export type FlowCombineHandler<State extends object = Record<string, unknown>> = (
  context: Context<State>,
  result: ScopeResult,
) => void | Promise<void>

export type FlowRecoveryHandler<State extends object = Record<string, unknown>> = (
  context: Context<State>,
  failure: ScopeFailure,
) => void | Promise<void>

export interface RetryOptions {
  readonly maxAttempts?: number | undefined
  readonly shouldRetry?: ((failure: Failure) => boolean) | undefined
  readonly delayMs?: number | ((failedAttempt: number, failure: Failure) => number) | undefined
}

export interface RetryPolicy {
  readonly maxAttempts: number
  readonly shouldRetry: (failure: Failure) => boolean
  readonly delayMs: number | ((failedAttempt: number, failure: Failure) => number)
}

export interface EventBase {
  readonly sequence: number
  readonly runId: string
}

export type ReportPayload = {
  readonly scopeId: number
  readonly activationId: number
  readonly name: string
} & ({ readonly hasData: false; readonly data: undefined } | { readonly hasData: true; readonly data: unknown })

export type RunEvent =
  | (EventBase & {
      readonly kind: 'run_started'
      readonly payload: {
        readonly rootElementId: number
        readonly rootActivationId: number
      }
    })
  | (EventBase & {
      readonly kind: 'run_finished'
      readonly payload: {
        readonly status: 'completed' | 'failed' | 'cancelled' | 'abandoned'
      }
    })
  | (EventBase & {
      readonly kind: 'scope_started'
      readonly payload: {
        readonly scopeId: number
        readonly parentScopeId: number | null
        readonly ownerActivationId: number
        readonly entryActivationId: number
        readonly entryElementId: number
        readonly flowElementId: number
        readonly depth: number
      }
    })
  | (EventBase & {
      readonly kind: 'scope_finished'
      readonly payload: {
        readonly scopeId: number
        readonly status: 'completed' | 'failed' | 'cancelled' | 'abandoned'
        readonly terminalSequences: readonly number[]
      }
    })
  | (EventBase & {
      readonly kind: 'callback_started'
      readonly payload: {
        readonly scopeId: number
        readonly activationId: number
        readonly parentActivationId: number | null
        readonly elementId: number
        readonly phase: Phase
        readonly attempt: number | null
      }
    })
  | (EventBase & {
      readonly kind: 'callback_finished'
      readonly payload: {
        readonly scopeId: number
        readonly activationId: number
        readonly phase: Phase
        readonly attempt: number | null
        readonly disposition:
          | {
              readonly kind: 'outcome'
              readonly outcome: 'route' | 'fanout' | 'end' | 'forward' | 'unhandled'
            }
          | { readonly kind: 'failure'; readonly failure: Failure }
          | { readonly kind: 'discarded' }
      }
    })
  | (EventBase & {
      readonly kind: 'retry_scheduled'
      readonly payload: {
        readonly scopeId: number
        readonly activationId: number
        readonly failureId: number
        readonly failedAttempt: number
        readonly nextAttempt: number
        readonly delayMs: number
      }
    })
  | (EventBase & {
      readonly kind: 'transition_committed'
      readonly payload: {
        readonly scopeId: number
        readonly sourceActivationId: number
        readonly branchIndex: number
        readonly transition:
          | {
              readonly kind: 'route' | 'forward_exit'
              readonly action: Action | null
              readonly destination:
                | {
                    readonly type: 'activation'
                    readonly activationId: number
                    readonly elementId: number
                  }
                | {
                    readonly type: 'terminal'
                    readonly sequence: number
                  }
            }
          | {
              readonly kind: 'end' | 'forward_end'
              readonly destination: {
                readonly type: 'terminal'
                readonly sequence: number
              }
            }
      }
    })
  | (EventBase & {
      readonly kind: 'terminal_committed'
      readonly payload: {
        readonly scopeId: number
        readonly terminalSequence: number
        readonly sourceActivationId: number
        readonly terminal:
          | { readonly kind: 'end'; readonly hasOutput: boolean }
          | { readonly kind: 'exit'; readonly action: Action | null; readonly hasOutput: true }
      }
    })
  | (EventBase & {
      readonly kind: 'failure_recorded'
      readonly payload: { readonly failure: Failure }
    })
  | (EventBase & {
      readonly kind: 'failure_fenced'
      readonly payload: {
        readonly target: { readonly kind: 'run' } | { readonly kind: 'scope'; readonly scopeId: number }
        readonly failure: Failure
      }
    })
  | (EventBase & {
      readonly kind: 'cancellation_fenced'
      readonly payload: {
        readonly target:
          | { readonly kind: 'run' }
          | { readonly kind: 'scope'; readonly scopeId: number }
          | {
              readonly kind: 'attempt'
              readonly scopeId: number
              readonly activationId: number
              readonly attempt: number
            }
        readonly reason: unknown
        readonly deadline: boolean
      }
    })
  | (EventBase & {
      readonly kind: 'report'
      readonly payload: ReportPayload
    })

export type Observer = (event: RunEvent) => undefined

export interface RunOptions {
  readonly maxConcurrency?: number | undefined
  readonly maxActivations?: number | undefined
  readonly maxAttempts?: number | undefined
  readonly maxTransitions?: number | undefined
  readonly maxReady?: number | undefined
  readonly maxReports?: number | undefined
  readonly maxDepth?: number | undefined
  readonly deadlineMs?: number | undefined
  readonly cancelGraceMs?: number | undefined
  readonly observer?: Observer | undefined
  readonly runId?: string | undefined
}

export interface RunStats {
  readonly activations: number
  readonly attempts: number
  readonly transitions: number
  readonly retries: number
  readonly reports: number
  readonly scopes: number
  readonly peakReady: number
  readonly peakCallbacks: number
  readonly durationMs: number
}

export interface ObserverDiagnostic {
  readonly eventSequence: number
  readonly message: string
  readonly cause: unknown | null
}

export interface CancellationInfo {
  readonly reason: unknown
  readonly deadline: boolean
}

export type RunResult<State extends object = Record<string, unknown>> =
  | {
      readonly status: 'completed'
      readonly state: State
      readonly terminals: NonEmptyTerminals
      readonly stats: RunStats
      readonly diagnostics: readonly ObserverDiagnostic[]
    }
  | {
      readonly status: 'failed'
      readonly state: State
      readonly terminals: readonly Terminal[]
      readonly failure: Failure
      readonly suppressed: readonly Failure[]
      readonly stats: RunStats
      readonly diagnostics: readonly ObserverDiagnostic[]
    }
  | {
      readonly status: 'cancelled'
      readonly state: State
      readonly terminals: readonly Terminal[]
      readonly cancellation: CancellationInfo
      readonly suppressed: readonly Failure[]
      readonly stats: RunStats
      readonly diagnostics: readonly ObserverDiagnostic[]
    }
  | {
      readonly status: 'abandoned'
      readonly state: State
      readonly terminals: readonly Terminal[]
      readonly cause: Failure | CancellationInfo
      readonly suppressed: readonly Failure[]
      readonly stats: RunStats
      readonly diagnostics: readonly ObserverDiagnostic[]
    }

export type CompletedResult<State extends object = Record<string, unknown>> = Extract<
  RunResult<State>,
  { readonly status: 'completed' }
>
export type FailedResult<State extends object = Record<string, unknown>> = Extract<RunResult<State>, { readonly status: 'failed' }>
export type CancelledResult<State extends object = Record<string, unknown>> = Extract<
  RunResult<State>,
  { readonly status: 'cancelled' }
>
export type AbandonedResult<State extends object = Record<string, unknown>> = Extract<
  RunResult<State>,
  { readonly status: 'abandoned' }
>

export class RunError<State extends object = Record<string, unknown>> extends CaskadaError {
  readonly result: FailedResult<State> | CancelledResult<State> | AbandonedResult<State>
  constructor(result: FailedResult<State> | CancelledResult<State> | AbandonedResult<State>)
}
export interface RunHandle<State extends object = Record<string, unknown>> {
  readonly done: boolean
  readonly result: Promise<RunResult<State>>
  cancel(reason?: unknown): void
}

export abstract class GraphElement<State extends object = Record<string, unknown>> {
  private readonly [stateInvariant]: (state: State) => State
  protected abstract readonly _caskadaKind: 'node' | 'flow'
  readonly name: string
  link(target: GraphElement<State>): void
  link(target: GraphElement<State>, action: Action): void
  links(): readonly Link<State>[]
}

export interface Link<State extends object = Record<string, unknown>> {
  readonly action: Action | null
  readonly target: GraphElement<State>
}

export interface NodeOptions<State extends object = Record<string, unknown>, Input = unknown> {
  readonly name?: string | undefined
  readonly retry?: RetryOptions | undefined
  readonly timeoutMs?: number | undefined
  readonly recover?: NodeRecoveryHandler<State, Input> | undefined
}

export class Node<State extends object = Record<string, unknown>> extends GraphElement<State> {
  constructor(token: typeof nodeConstructionToken)
  protected readonly _caskadaKind: 'node'
  readonly retry: RetryPolicy
  readonly timeoutMs: number | undefined
}

export interface FlowOptions<State extends object = Record<string, unknown>> {
  readonly name?: string | undefined
  readonly exits?: readonly Action[] | undefined
  readonly concurrency?: number | undefined
  readonly maxActivations?: number | undefined
  readonly combine?: FlowCombineHandler<State> | undefined
  readonly recover?: FlowRecoveryHandler<State> | undefined
}

export class Flow<State extends object = Record<string, unknown>> extends GraphElement<State> {
  protected readonly _caskadaKind: 'flow'
  readonly entry: GraphElement<State>
  readonly exits: readonly Action[]
  readonly concurrency: number
  readonly maxActivations: number | undefined

  constructor(entry: GraphElement<State>, options?: FlowOptions<State>)
  compile(): CompiledFlow<State>
  start(initialState: Readonly<State>, options?: RunOptions): RunHandle<State>
  run(initialState: Readonly<State>, options?: RunOptions): Promise<State>
}

export interface CompiledLinkDescription {
  readonly action: Action | null
  readonly target_element_id: number
}

export interface CompiledNodeDescription {
  readonly element_id: number
  readonly kind: 'node'
  readonly name: string
  readonly parent_scope_definition_id: number
  readonly links: readonly CompiledLinkDescription[]
  readonly retry: { readonly max_attempts: number }
  readonly timeout_ms: number | null
}

export interface CompiledFlowElementDescription {
  readonly element_id: number
  readonly kind: 'flow'
  readonly name: string
  readonly parent_scope_definition_id: number | null
  readonly owned_scope_definition_id: number
  readonly links: readonly CompiledLinkDescription[]
}

export type CompiledElementDescription = CompiledNodeDescription | CompiledFlowElementDescription

export interface CompiledScopeDescription {
  readonly scope_definition_id: number
  readonly owner_element_id: number
  readonly parent_scope_definition_id: number | null
  readonly entry_element_id: number
  readonly exits: readonly Action[]
  readonly concurrency: number
  readonly max_activations: number | null
}

export interface CompiledDescription {
  readonly schema_version: 1
  readonly auto_max_concurrency: number
  readonly root: {
    readonly element_id: number
    readonly scope_definition_id: number
  }
  readonly scope_definitions: readonly CompiledScopeDescription[]
  readonly elements: readonly CompiledElementDescription[]
}

export class CompiledFlow<State extends object = Record<string, unknown>> {
  constructor(token: typeof compiledFlowConstructionToken)
  start(initialState: Readonly<State>, options?: RunOptions): RunHandle<State>
  run(initialState: Readonly<State>, options?: RunOptions): Promise<State>
  describe(): CompiledDescription
}

export function node<State extends object = Record<string, unknown>, Input = unknown>(
  handler: NodeHandler<State, Input>,
  options?: NodeOptions<State, Input>,
): Node<State>
```

TypeScript defaults equal the Python `RunOptions` and `RetryPolicy` defaults.
Its author-facing partial `RetryOptions` is captured into the fully resolved
`RetryPolicy` exposed by a Node.
The invariant private state brand on `GraphElement<State>` prevents links or
Flow entries whose state types differ under
`tsc --strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess`. The optional `Input`
parameter on `Context<State, Input>` and `NodeHandler<State, Input>` provides
local input typing, and `node()` infers both parameters while still returning
`Node<State>`. Core does
not claim that an emitted payload matches a target handler: action-dependent
payload compatibility remains an application or higher-layer concern. Callback
authors normally rely on contextual inference and import no control-result type.
Authors who name reusable handlers import `Context` as a type. Terminal outputs
remain `unknown` application values; the one persistent workflow state retains
its generic type through Context, Flow, results, and run errors.
The generic is a static record type, not a runtime schema or preservation of an
input class or prototype; run capture always produces the plain record specified
below.
`GraphElement` is an abstract typing surface, not a custom-element protocol.
Compilation accepts only runtime-created `Node` and `Flow` instances and rejects
unknown subclasses in both ports. TypeScript's `Flow` constructor rejects a
derived `new.target` at runtime, so untyped JavaScript cannot introduce an
unsupported third element kind.
`Context`, `Cancellation`, and `RunHandle` are nonconstructible capability
interfaces issued by callbacks and `start()`. `Node` and `CompiledFlow` require
unexported construction-token values validated by identity at runtime; only
`node()` and `Flow.compile()` can construct them. External direct construction
and usable subclasses therefore fail without forcing their module-level
factories to bypass TypeScript's access rules.

All option containers have one portable capture rule. Python `start`/`run`
accepts only `None` or an exact, already-validated frozen `RunOptions` instance;
a different object raises `OptionValidationError`. `RunOptions.__post_init__`
validates every value, including a callable observer and a null-or-nonempty
string `run_id`. Python `RetryPolicy` is likewise exact, frozen, and validated when
constructed. `Node` and `Flow` validate and snapshot their definition arguments
synchronously: names are absent or nonempty strings, callbacks are callable,
timeouts/concurrency/scope activation limits are valid, and Flow exits are copied
once as unique nonempty strings. Invalid RetryPolicy/Node/Flow definition configuration raises
`GraphDefinitionError` before linking or compilation. TypeScript validates a
partial `RetryOptions` record with Node options, supplies omitted defaults, and
stores the resulting immutable resolved `RetryPolicy` on the Node. In both ports,
the resolved delay retains either its captured integer or its callable; the
runtime does not wrap a constant in a hidden no-delay/backoff function.

TypeScript accepts `undefined` or a plain Object-prototype/null-prototype option
record. It snapshots own keys once, rejects symbols, unknown/non-enumerable
properties, and `null`, then reads each known field exactly once in the public
declaration order rather than source-key order; explicit `undefined` means
omitted. `RunOptions` order is `maxConcurrency`, `maxActivations`, `maxAttempts`,
`maxTransitions`, `maxReady`, `maxReports`, `maxDepth`, `deadlineMs`,
`cancelGraceMs`, `observer`, `runId`. `RetryOptions`, `NodeOptions`, and
`FlowOptions` records use their interface order. Accessor/proxy errors retain
the exact cause. Run-option capture raises `OptionValidationError`; retry, Node,
or Flow construction raises `GraphDefinitionError`. Captured configuration is
runtime-owned and later source
record mutation has no effect. The observer must be callable, and `runId` must
be a nonempty string when present. These checks apply to `node()` and `Flow`
construction.

Every author-supplied control string in this RFC -- action, explicit or inferred
name, Flow exit, report name, and run ID -- follows the same primitive-string
rule above. Runtime lookup never invokes application-defined string-subclass
hashing, equality, or coercion. Inferred Python names that are not exact nonempty
strings fall back to `"anonymous"` rather than being coerced.

Every present numeric option must be an integer from zero through
`Number.MAX_SAFE_INTEGER`; Python requires `type(value) is int` and therefore
rejects booleans and `int` subclasses, while JavaScript requires a primitive
safe-integer `number`. JavaScript non-safe integers,
`NaN`, and infinities are not integers for this contract. Every accepted
JavaScript negative zero is normalized to positive zero before it is stored,
compared, reported, or used as a duration; this includes dynamic retry-delay
results. `max_concurrency`,
`max_activations`, `max_attempts`, `max_transitions`, `max_ready`, `max_reports`,
`max_depth`, `Flow.concurrency`, `Flow.max_activations`,
`RetryPolicy.max_attempts`, and `Node.timeout_ms` must be positive when present.
Python `Flow.max_activations=None` and an omitted or explicit `undefined`
TypeScript `FlowOptions.maxActivations` select no scope-local cap. Python
`max_concurrency=None` and an omitted or explicit
`undefined` TypeScript `maxConcurrency` select the compiled automatic value.
`deadline_ms`, `cancel_grace_ms`, and retry delays may be zero. A constant retry
delay is validated when its definition is captured; a delay callback's result is
validated when that callback runs.
Durations are relative milliseconds measured against a monotonic clock.

Timer arithmetic does not add a duration to a host `number`/float and assume the
sum remains exact. Each timer retains an origin plus its requested safe-integer
relative duration and uses an overflow-safe elapsed-time comparator, implemented
with arbitrary-precision integer accumulation or an equivalent quotient/remainder
pair. A host timer is only a wakeup hint; an implementation may split a delay
when its host timer has a smaller maximum.
Implementations never clamp, shorten, wrap, or round a requested long duration
into an earlier deadline. Mathematical `due_at` notation below refers to this
record and comparator, not necessarily one representable host timestamp.

Option validation also proves that
`16 + 16*max_activations + 8*max_attempts + 4*max_transitions + max_reports`
is at most `MAX_PORTABLE_COLLECTION_LENGTH` and therefore also fits in
`MAX_SAFE_INTEGER`. The smaller constant is JavaScript's maximum Array length and
is the portable bound for every materialized runtime collection in either port.
This deliberately conservative event-capacity bound ensures every framework and
application report event, including a final fence and `run_finished`, can receive
a portable sequence number; because every retained terminal, Failure, scope, and
publication record has a unique event charge, it also dominates each such
collection's cardinality.
The validation itself uses exact integer arithmetic (`int` / internal `bigint`)
or algebraically equivalent checked comparisons; it never multiplies these
inputs in a potentially imprecise JavaScript `number` and then trusts the result.

`RUN_EVENT_SCHEMA_VERSION = 1` names the first published v3 observer schema;
the unpublished D1-D4 design drafts do not consume versions. The bound is an
injective charge, not an estimate. Assign each event to the first applicable row
below; no event is charged twice:

| Charge               | Exact producers                                                                                                                                                                                                                                                                             |    Proven maximum |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------: |
| fixed run            | `run_started`, `run_finished`, at most one run `failure_fenced`, at most one run `cancellation_fenced`, and at most one initiating run-only `failure_recorded` not assigned below (scheduler invariant or admission/report overflow)                                                        |         5 per run |
| activation           | Flow `scope_started`/`scope_finished` (2); combine, Flow-recovery, and Node-recovery callback pairs (at most 6 total, though element kinds exclude some); one scope fence pair (2); callback/boundary/preflight/post-signal `failure_recorded` events not charged to an attempt (at most 3) | 13 per activation |
| admitted attempt     | handler callback pair (2); handler/timeout failure (1); retry-policy failure (1); attempt cancellation fence (1); retry schedule (1); unrelated post-signal failure (1)                                                                                                                     |     7 per attempt |
| committed transition | one `transition_committed` and at most one `terminal_committed`                                                                                                                                                                                                                             |  2 per transition |
| accepted report      | its one `report` event                                                                                                                                                                                                                                                                      |      1 per report |

The validated coefficients 16, 16, 8, 4, and 1 strictly dominate 5, 13, 7, 2,
and 1. A failure already assigned to a callback/attempt is not charged again
when a packet transfers, merges, or drains. A first run-only failure commits the
run fence, so no second fixed failure producer can occur. Packet operations, state
copying, and entry-ID fields add no event. Closed/fenced Context calls and every
report after the first overflow add none. Both implementations must enumerate
all producer sites against this assignment in a checked fixture; adding an event
without a unique charge requires a schema revision and a newly proved
coefficient before release.

Public exception classes have identical roles in both ports:

- `CaskadaError` is the common base for framework exceptions;
- `GraphDefinitionError` is thrown before a run for an invalid definition;
- `DuplicateLinkError` is its immediate `link()` specialization;
- `OptionValidationError` is thrown before start for an invalid run option or
  initial-state container/capture;
- `RunError` projects any already-settled failed, cancelled, or abandoned status
  through the simple run API and retains the exact result.

`RunError(result)` stores that exact result object. Python reports
`type(error).__name__ == "RunError"`; TypeScript reports
`error.name == "RunError"`. Its message is the framework-owned literal
`"Caskada run failed"`, `"Caskada run cancelled"`, or
`"Caskada run abandoned"` selected by `result.status`; neither port formats a
Failure cause or application value. When the controlling outcome is `Failed`,
or is `Abandoned` with a `Failure` cause, the error also exposes that controlling
Failure's exact non-null native cause through Python exception chaining
(`error.__cause__`) or the standard TypeScript `Error.cause`. It does not walk
`Failure.previous`. Framework-only Failures, `Cancelled`, and
cancellation-caused `Abandoned` outcomes have no synthetic native cause.

Failures encountered by scheduler-owned lifecycle execution after a handle
starts are data in `RunHandle.result`, not escaped framework exceptions.
`run()` deliberately projects that same settled data through the typed
exceptions above; each exception retains the exact result and projection never
reruns work. Every `Completed`, regardless of terminal kind or cardinality,
projects to its singular shared state. Synchronous misuse of a borrowed/closed
Context still raises at that API call; invalid
state-record operations raise at their operation. When either remains uncaught
inside a live lifecycle wrapper, the wrapper normalizes it into the specified
Failure.
Cancelling a Python task waiting on `RunHandle.result()` also remains native
waiter cancellation and does not cancel the run. User callbacks may throw
arbitrary language-native errors; `Failure.cause` retains them as opaque values.

Starting has one observable preflight order. In Python, `start()` first requires
a running `asyncio` event loop; absence raises native `RuntimeError` with the
literal `"Caskada start() requires a running asyncio event loop"` before options,
definition, or state are read and creates no handle, ID, or event. Both ports
then validate run options; compile the definition when the receiver is `Flow`;
validate and shallow-copy initial state; and atomically allocate the
invocation/handle, root Flow activation 1, root scope 1, counted entry activation
2, initial counters/ready item, and start timestamp. `run_started` and the root
`scope_started` are the contiguous opening publication bundle for that commit.
`CompiledFlow` skips only the compile step. Python `run()` is async and calls
`start()` while its running loop is active.
A failure in any preflight step creates no handle, callback, event, or partial
invocation. `run(initial_state, options)` performs the same `start` preflight, awaits
that handle once, and projects its frozen result envelope.

`run_started` is sequence 1 and root `scope_started` is sequence 2 even for
`deadline_ms=0`. A timer fact crossed by either observer commits and
signals immediately under the fence rule, but its public event follows the
complete opening bundle. The root entry is queued, not callback-admitted, by the
initial commit. Thus an immediate deadline still reports two activations, one
scope, `peak_ready=1`, zero attempts/transitions, and the two factual opening
events before its fence and closing events.

`start()` is synchronous through this boundary: it performs preflight and the
initial control commit, drains the complete opening publication bundle, then
drains any fence and terminal bundles caused while observing that opening. It
admits no lifecycle callback before returning. Consequently a zero deadline or
a slow opening observer that crosses that deadline can make `start()` return an
already-done handle; an ordinary start returns with the root entry still ready
and `done` false. The current run's handle is not yet public during this bundle,
so ordinary observer code cannot cancel that handle from an opening event.

Terminal status commit makes later `cancel()` calls no-ops, but it does not by
itself set `RunHandle.done`. After the final terminal-bundle observer returns,
the runtime appends any last diagnostic, freezes and installs the one
`RunResult` envelope, settles the handle's one Promise/Future with that same object,
and flips `done` exactly once as one settlement operation. Python `result()`
calls and TypeScript reads of `result` all await the same stored settlement; they
never reconstruct a result. During the interval between terminal commit and
handle settlement, status is immutable, `cancel()` is a no-op, and `done`
remains false.

The spelling difference is language-idiomatic, not semantic: Python uses
`handle.done()` and `await handle.result()`, while TypeScript exposes
`handle.done` and `await handle.result`. Both read the same one-shot settlement.

A malformed initial container, key/property shape, or exception while
enumerating or reading it is wrapped in `OptionValidationError`. Python preserves
the native exception through chaining; TypeScript preserves it as the error
`cause`. This is distinct from application state or control-argument capture
failures inside a lifecycle callback, which retain that callback's failure kind.

## Definition and compilation

### Links

Every `(source element, action)` pair has at most one target. The
unlabelled connection is a distinct internal sentinel, not the public string
`"default"`. Therefore these are different edges:

```text
source.link(next_node)
source.link(fallback, "default")
```

A second `link()` for the same action raises `DuplicateLinkError`
immediately. Outgoing edges form a switch, not an implicit broadcast table.
Fan-out emits repeatedly to the same one target:

```text
for item in items:
    context.emit("process", item)
```

`link(target)` selects the unlabelled edge. `link(target, action)` selects a
named-action edge. Python makes `target` positional-only and accepts `action`
positionally or by keyword; TypeScript accepts the same target-first order.
Omission is the only public spelling of an unlabelled link. Explicit Python
`None` and TypeScript `null` / `undefined` are invalid actions rather than
aliases for omission. Both overloads return `None` / `void`; graph construction
is always an explicit statement, never a second chaining grammar. Actions
must be nonempty primitive strings. Python requires `type(value) is str`, not a
`str` subclass; TypeScript requires `typeof value === "string"`. `None`,
`null`, `undefined`, symbols, and the private unlabelled
sentinel are not actions; no string, including `"done"` or `"default"`, has
special behavior. The qualifier remains named `action`, not `label`, because it
is the same value selected by `context.emit(action)` and exposed by
`Link.action`.

Explicit element names must also be non-empty strings. `node(handler)` uses a
nonempty handler name when available and otherwise `"anonymous"`; a Flow falls
back to `"Flow"`. Pass a name explicitly when traces must remain stable across
refactors, minification, or languages. Flow
exits are retained in declaration order, must be nonempty strings, and may not
repeat. Python rejects a bare `str`/`bytes` exits container before enumeration
and requires every member to be an exact `str`; TypeScript requires an actual
array of primitive strings. Duplicate exits are a `GraphDefinitionError`. Every Flow also has one
implicit unlabelled exit so a nested linear Flow can continue through its
parent's unlabelled connection without a public sentinel or configuration flag.

`links()` returns declaration-ordered `Link` records. `action` is
`None` / `null` only for the unlabelled edge. Mutating the returned collection
cannot change topology. Target references are definitions, not copies or
serialized nodes.

### Compiled placements

Compilation treats a nested `Flow` as an opaque element in its containing scope
and compiles its `entry` as a child scope definition. A non-flow target remains
in the current scope. Consequently, an edge never means "jump out of this
scope"; scope exits are outcomes, not cross-boundary pointers.

The same definition object may be reached in different flow scopes. It receives
a distinct compiled placement for each `(compiled scope definition, element
identity)` pair. Repeated visits inside one scope, including cycles, use the same
placement. Two placements may call the same user object, but their element IDs,
scope ownership, exit rules, and runtime activations are distinct.

The same child `Flow` definition may be placed more than once. Each runtime
entry creates a new scope ID. Compilation rejects containment recursion in which
a flow definition eventually contains itself. Ordinary cycles among elements in
one scope remain valid and are bounded by run limits.

`compile()` performs one iterative `O(V + E)` traversal and captures:

- compiled scope and placement IDs;
- each scope's entry placement, declared named exits, concurrency, and optional
  direct-activation cap;
- each placement's kind, name, definition reference, and action map;
- node retry and timeout policy values;
- `auto_max_concurrency`, the maximum `concurrency` among every compiled Flow
  scope placement, with a minimum of one;
- declaration order.

Compilation raises `GraphDefinitionError` before producing a partial
`CompiledFlow` if a placement, scope, connection, exit, ID domain, or description
collection would exceed `MAX_PORTABLE_COLLECTION_LENGTH` or
`MAX_SAFE_INTEGER`. Definition-time `links()` is subject to the same
portable collection bound. Thus compiled inspection is materializable with the
declared ordinary tuple/array surfaces in both languages.

ID assignment is normative. Reserve root Flow element ID 1 and root scope
definition ID 1. Process scope definitions through a FIFO worklist. Within each
scope, process a FIFO placement worklist starting with its entry and follow each
placement's links in declaration order; assign an element ID when an
identity is first enqueued in that scope. When a nested Flow placement is first
seen, allocate its owned scope-definition ID immediately and append that child
scope to the scope worklist; do not enqueue or assign the child entry placement
until that child scope is later dequeued for processing. Finish the current scope's placements before
processing the next scope. This iterative breadth-first rule gives both ports the
same description without constraining runtime scheduling.

It does not clone, serialize, or recursively freeze handler functions, clients,
closures, or values. Graph element fields are definition
configuration. They must not hold invocation state and must not be mutated while
compiled runs use them. Injected dependencies must support the concurrency with
which the definition is run.

Calling `link()` after compilation changes future compilations only. An
active run and an existing `CompiledFlow` retain their captured topology. Graph
construction concurrent with `compile()` is unsupported; build and compile on
one thread or event-loop turn.

`Flow.start()` and `Flow.run()` compile on every call so later
definition edits are visible. The corresponding `CompiledFlow` methods reuse a
topology snapshot. There is no public `clone()` or `seal()` contract in v3.

`CompiledFlow.describe()` is definition-only. Its `auto_max_concurrency` is a
captured topology fact, not a record of any invocation, run override, observed
parallelism, or live scheduler state.

## State, inputs, and emissions

### Three data roles

Caskada exposes three deliberately different roles:

- `context.state`: one mutable workflow state owned by the invocation and shared
  by every branch;
- `context.input`: the read-only binding delivered to this branch; the referenced
  application object is not frozen;
- terminal `output`: the value a completed branch publishes to its Flow.

They are not two memory scopes. State persists for the run. Input and output are
message values attached to control tokens. An ordinary linear workflow can
ignore input/output entirely and use only `context.state`.

The root entry input is `None` in Python and `undefined` in TypeScript.
Calling `emit()` or `emit(action)` forwards the current `context.input`; supplying
an input captures that value by argument presence, so explicit `None` /
`undefined` remains data. Calling `end()` hard-ends one branch with no output;
supplying an output publishes that exact value, including explicit `None` /
`undefined`.

### Application data contracts

Caskada treats state bindings, branch input, emitted replacement input, and
terminal output as opaque application data. It validates its own state-container
and control-protocol shapes, but it does not know which application fields are
required, what their values mean, or whether two linked handlers agree on a
payload shape. Capturing and routing a value does not enumerate, coerce, or
schema-validate it.

Missing-field behavior therefore remains ordinary host-language behavior. In
Python, `context.state["answer"]` raises `KeyError` when the key is absent, while
`context.state.get("answer")` returns its supplied default; mapping-shaped branch
inputs behave the same way when application code indexes them. If such an error
escapes a live callback, Caskada records the ordinary Failure for that phase and
applies its configured retry/recovery policy. It is not a framework schema
failure. In JavaScript, reading a missing state or input property
normally produces `undefined`; Caskada does not replace that language convention
with an implicit throw. TypeScript's `--noUncheckedIndexedAccess` and ordinary
optional-property checking keep potentially absent reads visible statically, but
runtime JavaScript still requires an application guard when absence is invalid.

`Context[State, Input]` and the corresponding TypeScript generics are local
static assertions by the callback author. They improve reads inside that
callback; they neither validate runtime data nor prove that a predecessor emits
the asserted `Input`. Dynamic Python input and output surfaces use `object`, and
TypeScript uses `unknown`, so application code must narrow before shape-specific
access instead of receiving an implicit escape hatch.

Validate at the first consumer or external trust boundary, before state writes
or effects that a whole-handler retry could repeat:

```python
def work(context: Context[WorkState, object]) -> None:
    job = parse_job(context.input)
    result = process(job)
    context.state["result"] = result
```

When validation must stay outside retried work, make that boundary an ordinary
node and pass the parsed value as branch input:

```python
def validate(context: Context[WorkState, object]) -> None:
    context.emit(input=parse_job(context.input))


async def do_work(context: Context[WorkState, Job]) -> None:
    context.state["result"] = await process(context.input)


validate_node = node(validate)
work_node = node(
    do_work,
    retry=RetryPolicy(max_attempts=3),
)
validate_node.link(work_node)
```

Applications and higher layers may standardize parsers or schema-bearing
wrappers around this pattern. Core does not add a validation lifecycle phase or
claim graph-wide payload typing.

### Buffered control

Every lifecycle callback receives a fresh `Context` with a private ordered
emission buffer. `context.emit(...)` appends route intent and its next-branch
input. `context.end(...)` appends one hard-terminal arm with optional output. It
hard-ends that emitted branch only: it does not terminate the host-language
function, cancel sibling branches, finish an enclosing callback, or stop the
run. Calls return `None` / `void`, schedule nothing, and do not stop the callback.
Mixed route and end emissions are legal and retain call order.

Only successful settlement with `None` / `undefined` can commit the buffer.
Any other return is invalid. Throw, timeout, cancellation, invalid return, or
failed preflight discards the complete buffer. State mutation and external
effects are ordinary application effects and are never rolled back.

Zero emissions have one phase-specific meaning:

| Phase         | Zero-emission settlement                             |
| ------------- | ---------------------------------------------------- |
| node handler  | insert one unlabelled route forwarding current input |
| Node recovery | propagate the exact current Failure packet           |
| Flow combine  | forward the exact current terminal set               |
| Flow recovery | propagate the exact current ScopeFailure packet      |

This preserves the zero-control-code linear path without losing failures or
outputs. A recovery that handles through the unlabelled link must call
`context.emit()`. A combiner that replaces its terminal set must emit at least
one branch; a combiner that only aggregates outputs into shared state may emit
nothing and forward the original terminals.

One emission is scalar continuation. Two or more emissions are atomic fan-out in
call order. Fan-out duplicates control and input references, never workflow
state. A zero-iteration emission loop takes the normal implicit link or Flow exit.
An author who needs that path to mean zero produced values calls `context.end()`
explicitly; it hard-stops the arm without adding an item to
`ScopeResult.outputs`.

`return context.emit(...)` remains valid because the call returns
`None` / `void`; the return statement is host-language style, not the control
protocol. It is accepted as migration convenience, but canonical code puts the
control call and any early `return` on separate lines so buffering remains
visible.

### Input and output capture

The public grammar is:

```text
context.emit()                         # unlabelled, forward current input
context.emit("review")                 # named action, forward current input
context.emit("work", item)             # named action, replace next input
context.emit(input=item)               # unlabelled, replace next input
context.end()                          # end without an output
context.end(result)                    # end with explicit output
```

```text
context.emit();
context.emit("review");
context.emit("work", item);
context.emit({ input: item });
context.end();
context.end(result);
```

An action is a nonempty string. The common labelled form takes application input
directly; `emit("work", value)` never interprets the value's shape as framework
options. The common terminal form likewise takes output directly. The supplied
value is retained by reference without inspection, cloning, serialization, or
ownership claims. Mutating it later follows ordinary host-language aliasing.

Only unlabelled input replacement needs disambiguation from an action. Python
uses the keyword-only `emit(input=value)` overload. TypeScript uses the exact
one-field record `emit({ input: value })`; this is the only public control wrapper.
Argument count, never value equality, distinguishes omission. Thus
`emit("work", undefined)`, `emit({ input: undefined })`, and `end(undefined)`
preserve explicit `undefined`; `emit("work")` and `emit()` forward the current
input, while `end()` records no output. A one-argument TypeScript
`emit(undefined)` is invalid, not
omission. Python has the corresponding distinction between omission and
`emit("work", None)`, `emit(input=None)`, or `end(None)`.

The persistent run-owned state carrier is an ordinary application reference and
may be used as an input or output, although doing so deliberately aliases the
workflow state into that branch/terminal. `dict(context.state)` or object spread
creates a separate shallow snapshot when that is the application's intent.

Each call first verifies the live Context epoch and controlling fence, performs a
timer checkpoint, and resolves its overload and argument count. It then validates
the action and any unlabelled-input wrapper, checks the callback-local emission
count against `max_transitions` and `MAX_PORTABLE_COLLECTION_LENGTH`, and appends
one immutable private intent.

Runtime overload resolution is exact. TypeScript `emit()` is unlabelled forward;
one string argument is a named forward; one non-null object argument is the
unlabelled-wrapper form; two arguments require a nonempty string action and treat
the second value as present input; every other arity is
`invalid_control_arguments`, while a one-argument primitive that is not a string
is `invalid_action`. Python accepts the four declared overloads, including either
positional or keyword `input` after a positional action; an unknown/duplicate
keyword or wrong arity is `invalid_control_arguments`, and an invalid supplied
action is `invalid_action`. In both ports `end` accepts exactly zero arguments or
one present output (`output=value` is also accepted in Python); every other call
is `invalid_control_arguments`.

TypeScript validates the unlabelled wrapper in this exact order, stopping without
touching any later property after the first rejection:

1. Require a non-null, non-array object.
2. Call `Object.getPrototypeOf` once and require `Object.prototype` or `null`.
3. Call `Reflect.ownKeys` once and require exactly the string key `"input"`.
4. Call `Reflect.getOwnPropertyDescriptor` once and require an own, enumerable
   data descriptor; accessors are invalid and their getter is never invoked.
5. Capture that descriptor's value by reference, check capacity, and append the
   intent.

Every proxy-observable operation is caught and followed by a timer/fence
checkpoint before the next operation. A trap throw retains the callback phase's
failure kind and exact cause. A fence committed by or crossed during a trap wins,
discards the call, and prevents later reflection or validation. Semantic shape
rejection uses `invalid_control_arguments`. Labelled input and terminal output
values are never shape-validated, enumerated, or property-read. Python keyword
binding supplies the equivalent unlabelled form without an application-container
capture step.

A caught rejected call appends nothing and leaves prior intents intact. An
uncaught semantic misuse becomes `invalid_outcome` in handler/Node recovery or
`invalid_combination` in Flow combine/recovery. Calls after callback settlement
fail and cannot alter the run.

Capacity rejection is deliberately stronger than catchable semantic misuse. The
first operation that would cross a hard runtime bound uses this table:

| Producing operation                                                        | `LimitDetail.limit`   | Atomic effect before the call raises                                                                                                             |
| -------------------------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `emit` / `end` would exceed the run's remaining transition capacity        | `max_transitions`     | Append nothing; create/replace the producing packet, drain it into a failed run fence, signal, and discard the complete callback buffer.         |
| an emission or forwarding collection would exceed the portable array bound | `portable_collection` | Publish no arm; create/replace the producing packet, drain it into a failed run fence, signal, and discard the complete callback/boundary batch. |

When more than one bound would reject the same emission, `max_transitions` wins
before `portable_collection`. Each case creates one unrecoverable
`Failure(kind="limit", cause=null)` with the producing callback's provenance and
uses the ordinary atomic `failure_recorded`, run `failure_fenced`, and run
`cancellation_fenced` publication bundle. The Context call then raises that
callback token's native run-failure cancellation. Catching it cannot restore the
run: later Context operations take the already-fenced path and allocate nothing.
Earlier direct state writes remain visible, but no earlier buffered intent from
that callback may commit. State width is application data rather than a run
budget and is not part of this hard-cap table.

### State ownership and visibility

`start(initial_state)` and `run(initial_state)` shallow-copy the caller's
top-level mapping once before a handle exists. Initial state is required; an
empty workflow state is
`{}`. Python accepts a `Mapping`, copies it with `dict(...)`, and requires the
copied keys to be exact strings. TypeScript accepts a non-null, non-array object,
copies its enumerable properties with ordinary object-spread semantics, and
rejects copied symbol keys. A failed shallow copy or invalid key raises
`OptionValidationError` before callbacks start.

That one run-owned map is shared by every activation and Flow. There is no
automatic branch copy, overlay, merge, last-writer rule, or hidden local memory.
Top-level writes are immediately visible to later reads in the same event-loop
execution order. Retried handlers and recovery see prior mutations. Nested
objects retain caller aliases.

Serial execution is deterministic when callbacks are deterministic. With
explicit concurrency, callbacks can interleave at suspension points; conflicting
writes to shared state are timing-dependent application behavior. Parallel code
must write disjoint locations, use an injected synchronization/service
abstraction, or publish isolated terminal outputs and aggregate them in a Flow
combiner. Caskada makes no transaction, rollback, exactly-once, data-race, or
deep-isolation claim.

Branch inputs and terminal outputs are borrowed references, not isolation
boundaries. Omitting `input` in several fan-out emissions deliberately gives
those siblings the same input identity; parallel mutation of that object is just
as timing-dependent as shared-state mutation. Treat payloads as immutable, or
construct/copy a distinct application value for each branch when isolation is
required.

Every callback receives the same persistent run-owned native `dict` or object.
After start-boundary capture, state reads and mutations follow ordinary Python or
JavaScript rules. There is no state-width budget, batch rollback, Proxy policy,
or framework scan on callback settlement. An application state operation that
throws becomes the ordinary callback failure with that exact cause.

The Context capability still closes at callback settlement, so a later
`context.state` property lookup fails with the other Context operations. A state
reference obtained while the Context was live does not close: it remains the same
carrier visible to later callbacks and final results. Application code may
retain it, pass it as input/output, or make an independent shallow snapshot with
`state.copy()`, `dict(state)`, or object spread. Such an alias can mutate
top-level state outside its originating callback; detached mutation during a run
is application-coordinated and outside scheduler ordering guarantees.

Every final `RunResult` contains that exact carrier reference. On completion,
the scheduler relinquishes access, but ordinary aliases remain aliases; the
result is not a state snapshot. On failure/cancellation it is explicitly partial.
On abandonment, Context control capabilities close, but uncooperative work or an
escaped state/nested reference may continue mutating application data. This is
the honest limit of an in-process mutable-state runtime.

One logical workflow should normally remain one root invocation. Link nested or
sequential phases, such as offline indexing followed by online answering, under
that root so every phase observes the same run-owned state. Passing a returned
state back as `initial_state` / `initialState` deliberately shallow-copies it
again and starts a new invocation with new IDs, limits, cancellation, events,
and ownership; use that rebinding only when the phases are genuinely separate
runs. Core exposes no borrow-mode exception to the copy-in rule.

### Atomic settlement

A callback settlement is atomic only over framework control:

1. capture its return tag, private buffer, current input, and timestamp, then
   close its Context;
2. discard without further normalization if an attempt/scope/run fence controls
   it;
3. require `None` / `undefined` and apply the phase-specific zero rule;
4. validate every captured action and resolve each route to one link or declared
   Flow exit;
5. reserve the complete transition, activation, terminal, ready, event,
   collection, and ID capacity that the batch itself allocates;
6. publish the callback-settlement event bundle;
7. perform the final timer/fence checkpoint;
8. linearize and publish the complete transition batch without yielding or
   invoking application code.

Failure before step 8 commits no transition and consumes no recovery packet.
There is no state derivation or state-map copy in this path. Once step 8
linearizes, a later timer cannot undo the batch. Direct shared-state writes and
external effects may already be visible and are not part of this transaction.

Step 4 visits buffered arms or forwarded terminals in their existing order and
completes action validation followed by route resolution for one arm before
touching the next; the first invalid or unknown arm is the only producer. If all
arms resolve, step 5 checks batch capacity in this exact priority:
`max_transitions`, `portable_collection`, run-wide `max_activations`, the
receiving scope's `scope_max_activations`, `max_ready`, then `safe_integer`. The
scope-local check charges only target activations allocated directly into that
scope; terminal/exit arms charge no local unit. A lower-priority bound is not inspected after
one rejects. The `safe_integer` check covers required activation, terminal, and
event sequence IDs in that order but exposes the same `LimitDetail` in every
case. Reservation remains all-or-nothing, so this precedence never publishes a
partial arm, ID, terminal, or queue entry.

Each buffered emission, each synthetic default route created by a zero-emission
handler, and each terminal forwarded across a Flow boundary consumes one
`max_transitions` unit when committed. This bounds implicit linear work,
terminal-only fan-out, and repeated scope propagation independently from
activations and attempts.

### Route resolution

Every route arm resolves through one deterministic table. A matching link wins
before an exit; an `end` arm bypasses this table and creates a hard terminal.

| Producing arm                                                                      | First lookup                                          | Fallback when absent                  |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------- |
| Node handler or Node recovery                                                      | that Node occurrence's link for the action            | its owning Flow scope's matching exit |
| nested Flow combine/recovery emission, or a child exit forwarded through that Flow | the nested Flow occurrence's link in the parent scope | the parent Flow scope's matching exit |
| root Flow combine/recovery emission                                                | no root-occurrence link is consulted                  | the root Flow scope's matching exit   |

For every scope, a missing unlabelled link matches its one implicit unlabelled
exit. A missing named link matches only an explicitly declared named exit.
Anything else is `unknown_action`; it never becomes an ad hoc exit. A forwarded
End remains End. A route that resolves to a successor passes the arm's input to
that activation; a route that resolves to an exit records that input as the
Exit terminal's output. This same rule governs root and nested execution, with
only the absence of a parent at root changing the first lookup.
Exact zero-combine forwarding at root makes its already-resolved child exits
final without a second lookup.

### Callback lifetime

A `Context`, its cancellation view, and emission buffer belong to one callback
epoch. Detached work must not retain the Context; spawned work must be joined
before settlement. Late Context property, emit, end, report, or cancellation
access raises and cannot alter scheduler control. A state carrier already
obtained from a live Context is an ordinary persistent alias governed by the
state-ownership rules above, not an epoch capability.

`remaining_ms()` / `remainingMs()` returns the ceiling of monotonic milliseconds
until the earliest applicable run, attempt, or controlling grace deadline. A due
timer reports zero; no applicable timer reports absent. It is advisory and
closed Context access raises.

Cancellation uses token signalling in Python and AbortSignal in TypeScript.
Application code should clean up and let cancellation escape. The scheduler
chooses final status from its already-committed fence.

## Flow scopes and completion

Every Flow owns a structured runtime scope with one FIFO of direct child
activations, a direct-child concurrency count, a live-token count,
an optional direct-activation budget/counter, settlement-ordered terminal records,
one cancellation source, and at most one failure fence.

Entering a nested Flow suspends one parent token and occupies one direct-child
slot in the parent, but holds no run-wide callback permit while waiting. The
child receives the parent token's input and the same run state.

Branch cardinality is exact:

| Settlement                    |  Current tokens |                   New tokens |
| ----------------------------- | --------------: | ---------------------------: |
| zero normal-handler emissions |              -1 | one unlabelled scalar effect |
| one route to a target         |              -1 |                           +1 |
| one route to a Flow exit      |              -1 |                           +0 |
| one end                       |              -1 |                           +0 |
| N emissions, N > 1            |              -1 |      sum of N scalar effects |
| enter nested Flow             | token suspended |              one child scope |

A scope reaches quiescence only when its live count is zero and every admitted
direct child has settled. Live tokens without a ready, running, waiting-Flow, or
retry-timer owner are an unrecoverable internal failure.

### Flow boundary behavior

At successful quiescence, the optional Flow combine callback runs exactly once.
Its `context.state` is the shared run state, `context.input` is the Flow
activation's incoming input, and `ScopeResult.terminals` contains ordered
immutable terminal records. Every Exit has an output; an End records whether an
output was supplied. `ScopeResult.outputs` is the ordered projection of only
output-bearing terminals, preserving their relative terminal order and exact
output references. Explicit `None` / `undefined` remains an output; `end()` adds
no item. Authors inspect `terminals` only when control kind, action, source, or
sequence is relevant.

For an omitted End output, Python exposes `has_output=False` and `output=None`;
TypeScript exposes `hasOutput: false` and `output: undefined`. A supplied output
sets the discriminator to true even when the value itself is `None` /
`undefined`. Every Exit sets the discriminator to true because its forwarded
branch input is always its output. `terminal_committed` metadata carries the same
presence discriminator but never the application value.

Flow combine and Flow recovery expose `context.input` as `object` in Python and
`unknown` in TypeScript. Unlike a handler passed through generic `node()`, a Flow
boundary can be entered from heterogeneous parent actions and constructor-local
input inference cannot be represented soundly in both languages. A combiner or
Flow recovery that relies on one application shape validates or narrows that
value locally; the runtime preserves its exact reference but asserts no type.

`ScopeResult` is deliberately unparameterized. Python exposes `outputs` as
`tuple[object, ...]`, while TypeScript exposes a read-only array of `unknown`; a
combiner validates or narrows those application values locally. A scope may
legitimately mix no-output Ends with output-bearing hard ends, named exits, and
unlabelled exits, so one output parameter would often be an unchecked falsehood.

This differs from local `Context<State, Input>` typing. The generic `node()`
factory can infer an input assertion from one handler and erase it when returning
`Node<State>` in both languages. A combine callback is installed through the
`Flow` class constructor. TypeScript constructors cannot declare a local type
parameter, and strict function variance correctly rejects a callback accepting
only `ScopeResult<Row>` where the Flow may supply `ScopeResult<unknown>`. Using
`any` or a bivariant callback would silently remove the current check; carrying
the parameter on `Flow` would turn local help into topology-wide output algebra.
Core chooses honest narrowing over either workaround and performs no output
coercion.

Missing combine, or zero combine emissions, forwards the exact terminal set.
One or more combine emissions replace it atomically. A non-null callback return
is `invalid_combination`. A combiner can therefore aggregate outputs into state
and return normally without manufacturing a new terminal:

```python
async def collect(context, result):
    context.state["results"] = list(result.outputs)
    # Zero emissions forward the original terminals.
```

For a nested Flow, each forwarded exit resolves through the nested Flow
occurrence's matching parent link or parent declared exit. Its output becomes the
successor's input or the parent exit's output. A forwarded end remains an end.
Kind, action, output presence/reference, order, and cardinality are preserved;
receiving activation and terminal IDs are new. The boundary batch preflights and commits
atomically and counts against `max_transitions`.

At the root, outgoing links have no parent. Exact forwarding makes its terminals
final. An undeclared named combine emission is `unknown_action`. Completion
always has one or more terminals and one shared state, regardless of terminal
cardinality.

Terminal and ScopeResult objects are immutable framework records, including the
single retained `outputs` projection, but their present output values are borrowed
application references. They may be retained after callbacks; the runtime
neither clones nor later mutates them. Failure suppression uses ordinary
immutable tuples/arrays that may likewise be retained after recovery.

Node recovery receives the failed activation's input. Flow recovery receives the
active packet's controlling input: a child failure contributes that child's
input, while a fresh Flow-combine failure contributes the Flow activation's
incoming input. Missing or zero-emission recovery propagates the active packet;
committed emissions handle it. Failure packets store the controlling input
reference alongside failure provenance, never workflow state; workflow state
remains the invocation's one shared map.

The root Flow placement is activation ID 1 and owns scope ID 1. Its entry is
activation ID 2 with root input `None` / `undefined`. Both count toward
run-wide `max_activations`; the entry is unit one of the root scope's optional
local cap and also counts toward `max_ready`. Every nested Flow owner counts in
its parent scope and atomically creates a child whose entry is unit one of that
fresh child cap. Root depth is 1, nested Flows add one,
all ID domains begin at 1, and `scope_started` exposes owner and entry IDs
without a fabricated transition.

Terminal order is settlement order. Serial deterministic callbacks therefore
produce deterministic order. Parallel scopes expose timing order; semantic
ordering belongs in output data such as an item index.

## Scheduler and concurrency

One invocation owns one iterative scheduler. Execution never recursively walks
successor graphs and never recursively clones definitions.

### Two limits, two meanings

- The effective run callback ceiling is an explicit
  `RunOptions.max_concurrency` / `maxConcurrency`, or the compiled
  `auto_max_concurrency` when omitted. It bounds admitted lifecycle wrappers
  (`handle`, `recover`, and `combine`) from permit reservation through release,
  including a `starting` wrapper not yet invoked and callbacks suspended on I/O.
  Synchronous retry-policy evaluation retains the failed handler's permit until
  selection finishes. Observer delivery is serialized scheduler work, not a
  separately admitted lifecycle callback.
- `Flow.concurrency` bounds direct graph element activations admitted in that
  particular runtime scope.

A node activation holds one scope slot from first attempt through retry delays,
recovery, and final routing. A nested flow holds one parent scope slot until its
child scope and combination settle. A nested flow does not hold a global
callback permit while waiting. Its own children consume its own scope slots and
global callback permits.

This makes local structured parallelism possible without deadlock. A serial
outer flow can admit one batch subflow; that child can run eight workers when its
own concurrency is eight: the compiled automatic ceiling is at least eight. The
outer flow will not admit another direct sibling until the child settles.
An explicit smaller run value throttles all scopes. An explicit larger value can
permit aggregate concurrency from several simultaneously active scopes; every
scope's own `Flow.concurrency` remains an independent local cap. The automatic
value is the maximum local cap, not a product or sum of nested caps, so topology
alone never silently enables multiplicative callback growth.

### Ready structure

Each scope owns a FIFO `pending` deque. Two run-wide round-robin deques index
eligible scopes by the kind of their FIFO head:

- `flow_scope_ready` contains scopes whose next activation is a nested Flow and
  therefore needs no global callback permit;
- `node_scope_ready` contains scopes whose next activation is a Node and needs a
  callback permit.

A scope with pending work and an available direct-child slot appears in exactly
one of those deques; otherwise it appears in neither. A membership tag makes
removal or recategorization `O(1)` whenever its head or capacity changes.

A separate run-wide FIFO `callback_ready` deque contains callbacks for
activations that already hold their scope slot: due retries, node recovery,
nested-flow combination, and flow recovery. These entries reacquire only a
global callback permit. They never pass through `pending` and never test or
reserve a second scope slot.

At each admission step, the scheduler chooses the oldest `callback_ready` item
when a permit exists, otherwise the oldest `flow_scope_ready` head, otherwise
the oldest `node_scope_ready` head when a permit exists. It repeats from the
first priority after every admission. If no choice is admissible it waits for a
callback, cancellation request, or runtime timer. It never pops and restores a
blocked activation or scans a queue for one that fits. Finite activation/depth
budgets bound the intentional resume-before-nested-Flow-before-new-Node
priority.

When a callback permit becomes available, `callback_ready` has priority over
admitting a new node. Starting a nested flow does not require a callback permit.
Starting a new node does. The Flow combine callback and both recovery callbacks
require a callback permit but no additional direct-child slot; the owning flow
activation already holds its parent slot.

One lifecycle callback never hands its permit directly to another. At ordinary
callback settlement the wrapper releases its permit before any successor
lifecycle work is admitted. The one temporary exception is inline retry-policy
evaluation, which retains the failed handler's permit while its synchronous
policy functions run. If node attempts are exhausted or policy declines retry,
the scheduler performs the final timer/fence checkpoint, atomically releases
that permit, and appends Node recovery to the tail of `callback_ready`; recovery
then competes under the normal priority and admission rules. A scheduled retry
likewise releases the permit before parking. Policy/limit failure releases it as
part of the atomic run-fence settlement. A failed Flow combination releases its
permit before the eventual Flow recovery is appended, and a failed recovery
never chains another callback inline. `callback_started` order therefore follows
the one FIFO rather than host call-stack timing, including when the effective
callback ceiling is one.

One run-wide, cancellable min-heap owns four timer kinds: run deadline, node
attempt timeout, cooperative-shutdown grace, and delayed retry. Its key is
`(due_at, priority, insertion_sequence)`. At the same due time, priority is run
deadline, attempt timeout, grace expiry, then retry readiness. Callback
settlements are processed after the first three and before retry readiness, so a
timer wins its documented tie while a just-settled failure can prevent a retry
from being admitted.

Every live timer has an indexed handle. Normal callback settlement removes its
attempt timer; scope/run settlement removes its grace timer; and a fence removes
affected retry timers. Removal is `O(log H)` and leaves no stale heap entries.
Implementations may use tombstones only if they compact eagerly enough to retain
the same `O(live timers)` space bound.

When a scope/run fence signals an **invoked** callback that has not timed out, it
removes that callback's attempt timer and protects it with the scope/run grace
timer. A `starting` wrapper is instead skipped by the admission-handoff rule and
never enters grace. If an attempt timeout already fired on invoked work, its
earlier grace timer remains live while the outer fence adds its own; the first
due grace controls and no later fence extends either deadline.

A delayed retry retains its activation, live token, and scope slot but holds no
callback permit. When its timer becomes ready it enters `callback_ready`, not its
scope's new-activation queue. A serial scope can therefore retry without waiting
for the slot that the retry itself already owns.

Each activation carries exactly one branch-input reference. Every activation in
the invocation sees the same run-owned state carrier. Every callback wrapper
creates one Context epoch and one private emission buffer, then closes both
before settlement is queued; closing that Context does not revoke a previously
obtained state reference.

The scheduler also owns an insertion-ordered registry of active failure packets.
Every packet has exactly one runtime owner. The first run-level fence atomically
drains that registry into the final cause and suppression order before signalling
callbacks; later observed failures append once. Packet ownership, not object
copying, prevents loss and double accounting across nested scopes.

### Scheduler outline

```text
compile topology
atomically create root Flow activation 1, scope 1, entry activation 2,
    counters, ready item, handle, and start timestamp
publish contiguous run_started + root scope_started opening bundle
enqueue semantics are already committed; process any deferred opening fence bundle

while the run is unsettled:
    harvest published callback settlements and their monotonic settled_at stamps
    apply any caller-cancellation fence already committed by RunHandle.cancel
    read the monotonic clock
    if no run fence exists and the run deadline is due:
        mark already-settled wrappers as preceding the new signal
        commit the deadline fence

    process every due attempt-timeout timer in heap order:
        if its wrapper has settled_at < attempt_due_at:
            remove the attempt timer and leave settlement queued
        elif its wrapper is starting:
            record handler_timeout, signal and skip it before invocation
            remove the attempt timer, arm no grace, and queue callback_finished
        else:
            record handler_timeout and signal that attempt
            replace timeout timer with grace timer while invoked work remains live

    process every due grace timer in heap order:
        if any protected wrapper lacks settled_at < grace_due:
            abandon the run
        else:
            remove the grace timer and leave settlements queued

    for each settled callback in settlement order:
        remove its live attempt or attempt-grace timer, if any
        consume its already-closed Context epoch and wrapper settlement tag
        if an ordinary return is controlled by an existing attempt/scope/run fence:
            inspect none of its value; release it with timeout/discarded disposition
            continue
        if it is a failed handler entering retry/recovery selection:
            retain its permit through any synchronous policy evaluation
            then release it before parking retry or enqueueing recovery
            continue through the failure-packet rules
        release the callback permit for every other settled lifecycle callback
        require a None/undefined return without inspecting application data
        apply the phase-specific zero-emission rule
        preflight its complete buffered-emission or Flow-forwarding batch
        retain each emitted input/output payload reference and run a final timer checkpoint
        linearize the complete transition, then materialize it without yielding
        release or retain the logical scope slot as specified
        test affected scopes for failure settlement or quiescence

    move due retry timers, in heap order, to callback_ready

    run a timer checkpoint; restart the loop if any fence or timeout fired

    repeat admission priority until no case is admissible:
        if callback_ready is not empty and a callback permit exists:
            pop its oldest admitted activation callback
            if it is a retry handle and no global attempt capacity remains:
                commit its unrecoverable admission-limit replacement without a
                    permit
                continue
            reserve callback permit and, for retry handle, its attempt atomically
            start retry, combine, or recovery callback
            continue

        if flow_scope_ready is not empty:
            pop its oldest scope and that scope's nested-Flow FIFO head
            preflight max_depth, max_activations, max_ready, then safe_integer
            reserve its parent scope slot, child scope, counted child entry
                activation, child direct-activation counter at one, ready item,
                and IDs as one control commit
            publish scope_started and enqueue that entry with the same shared
                state map and the Flow activation's input
            recategorize parent and child scopes from their current FIFO heads
            continue

        if node_scope_ready is not empty and a callback permit exists:
            pop its oldest scope and that scope's Node FIFO head
            if no global attempt capacity remains:
                commit its fresh unrecoverable admission-limit failure without a
                    scope slot, callback permit, or attempt
                continue
            reserve scope slot, callback permit, and attempt atomically
            start the Node callback
            recategorize the scope from its current FIFO head/capacity
            continue

        stop admission

    await one callback settlement, caller-cancellation wakeup, or next heap timer
```

### Callback admission handoff

Immediately before any callback admission reservation, the scheduler performs a
timer/fence checkpoint; a winning fence admits nothing and publishes no
`callback_started`. Admission then creates a private `starting` wrapper and
reserves its global callback permit. A new pending Node activation also reserves its direct
scope slot; retry, Node recovery, Flow combination, and Flow recovery reuse the
logical slot/token already retained by that activation or scope and do not
reserve a second one. A `handle` admission, initial or retry, additionally
reserves/increments its attempt. The runtime arms applicable timers and emits
`callback_started`, which means the lifecycle wrapper has been admitted and
intends to invoke user code. It does not claim that application code has already
run.

After that one-event bundle and its mandatory timer checkpoint, exactly one
handoff occurs:

- with no controlling attempt, scope, or run fence, atomically change
  `starting -> invoked` and call the user callback exactly once;
- if the attempt timeout won, atomically change `starting -> skipped`, close its
  Context, and release only the callback permit. The activation retains its
  scope slot/live token, its timeout packet proceeds through retry/recovery, and
  `callback_finished` carries the existing `handler_timeout` disposition;
- if a scope/run fence won, atomically change `starting -> skipped`, close its
  Context, and settle the activation without calling user code, releasing its
  permit, scope slot, and live token. `callback_finished` is `discarded`.

The already-committed fence bundle is published before the queued
`callback_finished`; terminal closure follows that finish. A skipped wrapper is
never grace-protected because no application callback began, so zero grace alone
cannot turn this case into false abandonment. Its admitted attempt and peak
callback facts remain counted. This pre-invocation decision is identical in both
ports and intentionally precedes calling a TypeScript async function, whose body
could otherwise run synchronously while the equivalent Python coroutine body
had not begun.

An activation ID, scope ID, failure ID, terminal sequence, and event sequence is
a positive safe integer unique within its own ID domain for that run. Each
activation stores one bounded parent activation ID, not a growing causal-path
string. `run_id` is an opaque string;
the default is process-local and callers may supply a globally meaningful one.

Activation ancestry and transition/terminal sources use this exact table:

| Fact allocated or committed                                | `parent_activation_id` of the new activation | `source_activation_id` on its transition/terminal                     |
| ---------------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------------------- |
| root Flow owner, activation 1                              | `null`                                       | none                                                                  |
| root Flow entry, activation 2                              | root Flow owner                              | none; entry allocation is not a transition                            |
| target of a Node emission or synthetic default             | emitting Node activation                     | emitting Node activation                                              |
| nested Flow owner targeted by a parent-scope arm           | emitting Node or parent Flow activation      | that same emitting activation                                         |
| nested Flow entry                                          | nested Flow owner                            | none; `scope_started` identifies the owner and entry                  |
| target produced by Flow combine, recovery, or forwarding   | owning Flow activation                       | owning Flow activation                                                |
| direct `end` terminal                                      | no new activation                            | producing Node or Flow activation                                     |
| terminal recommitted across a nested or root Flow boundary | no new activation                            | owning Flow activation; the child terminal remains separately visible |

Every arm of one fan-out applies the same row independently in buffer order.
Retry, retry delay/readmission, and Node recovery retain the original Node
activation and its original parent; they never allocate a replacement activation
or rewrite ancestry. Flow combination and Flow recovery likewise reuse their
owning Flow activation. No implementation may infer a different parent from the
scope that happens to admit work.

Deadlines use `now >= due_at`. A caller cancellation that committed before a
scheduler turn remains the first run-level fence; otherwise a due run deadline
precedes attempt timeout, grace expiry, and callback settlement. Attempt timeout
precedes grace expiry; both precede a callback settled at the same observed
instant. The clock check on every callback settlement path also catches a finite
synchronous handler or inline report observer that blocked beyond its timer.

The callback wrapper stamps `settled_at` with the same monotonic clock before
notifying the scheduler. A callback beats its attempt or grace timer only when
`settled_at < due_at`; equality belongs to the timer. This prevents unrelated
scheduler or observer delay after user code returned from inventing an attempt
timeout. The run deadline is different: it bounds the complete run and is tested
at the final emission-linearization checkpoint. A callback settled before the
deadline still loses if observation, preflight, input capture, or scheduler
work prevents reaching that checkpoint strictly before `due_at`; once the
checkpoint succeeds, the ensuing non-yielding internal materialization belongs
to the committed batch even if the clock passes `due_at` during it.

Before any caller, scope, or run signal is delivered, the fence commit atomically
marks wrappers that already published a settlement. `RunHandle.cancel()` performs
that mark itself; a scheduler-created scope/deadline fence does it immediately
before signalling. A pre-signal ordinary return may still be discarded because
its transition had not committed. A pre-signal exception keeps its real callback
failure classification and becomes packet/final suppression rather than being
mistaken for cooperative cancellation. Attempt deadlines are stricter in the
other direction: a wrapper stamped before `attempt_due_at` prevents that attempt
timeout entirely, even when the scheduler observes both later.

A **timer checkpoint** refreshes the monotonic clock and applies that same
priority order. It runs before entering user code, before publishing a settled
callback outcome, before every atomic emission/forwarding commit, and immediately
after a synchronous observer returns. If a `Context.report()` observer crosses a
run or attempt deadline, `report()` commits/signals the applicable fence and
raises native cancellation before returning to the handler. No callback is
admitted and no emission is committed using a stale clock reading. The checkpoint
rule ends once terminal status is committed; the final `run_finished` observer
remains outside duration and deadline accounting as specified below.

Synchronous retry-policy calls use the same monotonic clock but run inline with
their retained permit. Their dedicated pre-call/completion/pre-commit
checkpoints and strict timestamp rule are specified in Node attempts below; they
never hide between two scheduler checkpoints.

### Run limits

| Limit             | Default | Counts                                                                          |
| ----------------- | ------: | ------------------------------------------------------------------------------- |
| `max_concurrency` |    auto | admitted lifecycle wrappers holding callback permits                            |
| `max_activations` | 100,000 | Flow owners, entries, and other graph element entries                           |
| `max_attempts`    | 200,000 | admitted node-handler attempts                                                  |
| `max_transitions` | 200,000 | committed buffered emissions, synthetic default routes, and forwarded terminals |
| `max_ready`       | 100,000 | queued, not-yet-admitted activations                                            |
| `max_reports`     | 100,000 | accepted application `Context.report()` calls                                   |
| `max_depth`       |      32 | simultaneously nested flow scopes                                               |
| `deadline_ms`     |    none | total monotonic wall time                                                       |
| `cancel_grace_ms` |   1,000 | cooperative shutdown after a fence                                              |

`RunOptions` limits are run-wide and include nested flows. There is no default
per-node visit or per-edge traversal count. Ordinary loops and cycles are bounded
by activation, transition, attempt, and deadline budgets rather than hidden
topology-dependent heuristics.

Each Flow may additionally declare `max_activations` / `maxActivations`, absent by
default. Every runtime invocation of that Flow owns a fresh counter. It counts
graph-element activations allocated directly into that scope: the scope entry is
unit one, a nested Flow owner is one unit in its parent, and that nested Flow's
entry is separately unit one in its fresh child scope. Descendants, retries,
handler attempts, combine/recovery callbacks, transitions, and terminals do not
count. A one-node self-loop with a cap of `N` therefore admits at most `N` visits;
multi-node and fan-out scopes deliberately use one aggregate component budget
rather than a per-placement counter map.

An emission/forwarding batch reserves all of its required direct-activation units
atomically after the run-wide activation check and before `max_ready`. If the
scope has insufficient units, no arm commits and the runtime creates the existing
unrecoverable `Failure(kind="limit", cause=None)` with
`detail.limit="scope_max_activations"`. Its `scope_id` is the exhausted receiving
scope; `activation_id` and `element_id` identify the source attempting the
allocation. It bypasses recovery like the other framework capacity failures. No
new run statistic is added; compiled inspection exposes the configured cap and
the scheduler stores one counter per live scope.

`auto` is `CompiledDescription.auto_max_concurrency`: the maximum local
`Flow.concurrency` across compiled scope placements, never less than one. Thus a
definition whose Flows all keep `concurrency=1` has a formal serial proof: its
effective ceiling is one unless the caller explicitly raises it, and local caps
still prevent parallel direct children. Raising only the run ceiling does not
make a serial Flow parallel.

Because every run creates a root Flow activation and a distinct entry
activation, `max_activations` must be at least 2; `max_ready` and `max_depth` must
be at least 1. Nested-scope creation reserves its entry activation, ready item,
depth, and IDs before publishing `scope_started`, so budget failure never exposes
a half-created scope. This admission preflight occurs only when the nested Flow's
`flow_scope_ready` head is selected, not when the earlier route merely queues its
owner activation. Its exact priority is `max_depth`, `max_activations`,
`max_ready`, then `safe_integer`; the first rejection creates the existing
unrecoverable limit Failure with the queued Flow activation's provenance and
commits no child scope, entry activation, ready item, or partial ID.

## Retry, failure, and recovery

### Node attempts

`RetryPolicy.max_attempts` is at least one and its default delay is the constant
zero. `Context.attempt` is the one-based attempt ordinal for that Node activation
during its handler and is absent in all
other phases; `RunStats.attempts` is the separate run-wide admitted count.

For an ordinary handler failure:

1. Capture a `Failure(kind="handler")`.
2. If the node's `RetryPolicy.max_attempts` is exhausted, skip the predicate and
   any configured delay callback and either enqueue its configured recovery once
   with a fresh Context or propagate when no recovery exists.
3. Otherwise call synchronous `should_retry(failure)`.
4. If it returns false, enqueue configured recovery, or propagate, without
   evaluating the retry delay.
5. If it returns true but the run-wide `max_attempts` capacity is already zero,
   create an unrecoverable admission `Failure(kind="limit")` immediately. Do not
   evaluate the retry delay, publish `retry_scheduled`, or admit recovery.
6. Otherwise select the captured constant `delay_ms`, or synchronously call its
   callback form with `(failed_attempt, failure)`. Validate a callback result as
   a non-negative safe integer under the same exact Python-`int` / primitive
   JavaScript-`number` rule and park the activation in the retry heap. This
   availability check does not reserve the future attempt.
7. A recovery with one or more emissions handles the packet only when that batch
   commits; zero emissions preserve and propagate the exact handler packet.

Retry-policy callback errors are unrecoverable policy failures. They bypass all
node and flow recovery, normalize to `Failure(kind="retry_policy")`, and fence
the run. Recovery is never retried.

The run-wide `max_attempts` budget is separate from the node policy. It is
checked and reserved atomically immediately before every initial or retry
node-handler admission and before `callback_started`. Exhaustion creates one
unrecoverable `Failure(kind="limit")` for that activation without incrementing
`attempts`, changing `peak_callbacks`, reserving a callback permit, or emitting
either callback event. The Failure carries its scope, activation, and element
IDs but `attempt=None` / `null` because no attempt was admitted. On an initial
activation it creates a fresh packet; on a delayed retry it replaces that
activation's existing packet with `previous` pointing to its current primary,
then follows the atomic run-fence rule.

The early zero-capacity check after an affirmative `should_retry` uses the same
null-attempt, activation-owned limit provenance and replaces the failed
activation's packet immediately. It is an optimization of impossible future
admission, not an admitted attempt.

The pre-schedule global-capacity check is an observation, not a reservation.
Another concurrent node may therefore consume the final run-wide slot after
delay selection and `retry_scheduled` but before this retry timer is readmitted.
Such a schedule remains counted in `retries`; the later admission-limit failure is
the observable result. A single-threaded scheduler resolves simultaneous
last-slot admissions in the established callback-ready/FIFO/round-robin order.

`should_retry` must return an actual boolean and must not return an asynchronous
value (a Python awaitable/async generator or TypeScript thenable). A `delay_ms`
callback must return a non-boolean, non-negative safe integer and likewise must
not return an asynchronous value. Any violation is the same
unrecoverable `retry_policy` failure as a thrown policy callback. A constant
delay has already passed the identical numeric validation during definition
capture and invokes no user code at retry time.

Forbidden asynchronous results from scheduler-owned synchronous extension
points receive one shared **best-effort native cleanup**. Cleanup never awaits,
cancels, admits, counts, or turns that value into workflow work. It guarantees
warning/rejection consumption only for the native cases listed below; arbitrary
custom awaitables and thenables cannot be drained portably without executing
application code:

- Python closes a native coroutine exactly once. For an `asyncio.Future` or Task
  it calls `exception()` immediately when done, or installs one guarded done
  callback that retrieves `exception()` later. For another awaitable it obtains
  `__await__()` once and, without advancing the iterator, calls the iterator's
  `close()` when present. A native async generator is recognized as invalid but
  left undriven because `aclose()` is itself asynchronous; native async
  generators do not produce coroutine-never-awaited warnings merely because
  they were not iterated. Every inspection, callback, retrieval, and close
  catches `BaseException`.
- TypeScript reads `then` once under the extension point's ordinary caught
  result-inspection boundary. For a callable-`then` value it invokes captured
  intrinsic `Promise.prototype.then` with both a no-op fulfillment handler and a
  no-op rejection handler. Returning `undefined` from both prevents the ignored
  child promise from assimilating a fulfilled application's thenable value. That
  call also performs the native Promise brand check; a brand failure means the
  arbitrary thenable is left undriven. Species/constructor access and every
  cleanup throw are caught. The runtime never calls an application-overridden
  `.then` or `.catch` property.

A cleanup failure is discarded and cannot replace the already-selected
`retry_policy` Failure or `ObserverDiagnostic`, append another public record, or
change event ordering. A throwing awaitable/thenable inspection remains the one
ordinary policy-result-inspection failure or observer diagnostic, with that
exact thrown object as cause. Later resolution or rejection of a native value
whose rejection was consumed has no workflow effect. Host warnings and external
effects from hostile/custom asynchronous objects are outside Caskada's cleanup
guarantee; the value is still rejected immediately as an invalid synchronous
extension result and is never awaited or admitted by the scheduler.

Each configured policy function is scheduler-owned synchronous user work that
retains the failed handler's callback permit. The runtime checkpoints
timers/fences before calling `should_retry`, again before calling a delay
callback when configured, and again before committing a retry schedule or
recovery admission. It stamps each function's ordinary return or throw with the
monotonic clock immediately when the call
finishes. A result precedes the run deadline only when `settled_at < due_at`;
the deadline wins equality.

If a run fence already controls the policy call, or the run deadline wins at its
completion, an ordinary return is discarded without validating it, the active
packet is drained by that run fence, and no later policy function/retry/recovery
is started. A thrown policy error stamped before an as-yet-uncommitted deadline
is the unrecoverable `retry_policy` replacement and commits the failure fence. A
throw stamped at/after the deadline, or after a reentrant caller fence committed,
is eligible only for post-fence `retry_policy` suppression whose `previous` is
that invocation's drained packet primary. At policy completion the runtime first
stamps settlement, then checkpoints the earliest controlling grace before
classifying the throw. It records the suppression only when
`settled_at < grace_due` and no terminal status has committed; equality or a
later settlement is discarded without a Failure/event because abandonment has
priority and is immutable. Such suppression cannot replace the cancellation
cause. The final pre-commit checkpoint can likewise cancel an otherwise valid
retry schedule without incrementing retry stats or publishing its event.

When that checkpoint succeeds, its monotonic timestamp is the retry schedule's
linearization instant and timer origin. Installing the retry timer, incrementing
`RunStats.retries`, and committing the `retry_scheduled` fact are one control
commit; the failed handler's permit is then released as specified above. Event
observation does not move the origin, so a slow `retry_scheduled` observer
consumes the requested delay. A zero delay becomes due at the first mandatory
timer checkpoint after that event bundle drains, never before the committed
event is published.

Missing recovery callbacks and successful zero-emission recoveries preserve the
active packet by identity inside the runtime. Authors return no sentinel or
Failure object. When a configured recovery throws, the runtime creates
`node_recovery` or `flow_recovery` and applies the universal replacement rule.

A retry repeats the whole node-handler callback with the same branch input and
shared run state. Shared-state mutations, nested mutations, and external effects
from prior attempts remain. Buffered emissions are discarded unless their
callback settles and commits successfully. Caskada promises at-least-once
attempts, not rollback or exactly-once effects. Retried handlers must be
idempotent or implement application-level idempotency.

The first failed attempt creates one activation-owned failure packet. It remains
active through retry delay and later attempts. A later attempt failure replaces
its primary under the universal rule; a successfully committed handler emission
consumes it as handled. If cancellation or another run fence wins during retry,
the still-active packet participates in the mandatory run-fence drain.

There is no framework cleanup hook. A handler owns resources with ordinary
language constructs such as `try/finally`, async context managers, or `using`.
Those constructs run for each attempt and make the lifetime visible in the code
that acquired the resource.

### Failure classes

`FailureKind` has one exact producer contract:

| Kind                  | Produced by                                                                                                       |
| --------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `handler`             | A node handler throws before its attempt timeout wins, or produces a pre-signal application error.                |
| `handler_timeout`     | A node attempt deadline wins.                                                                                     |
| `retry_policy`        | `should_retry` or a `delay_ms` callback throws or returns an invalid value.                                       |
| `node_recovery`       | A configured Node recovery callback throws.                                                                       |
| `flow_combine`        | A configured Flow combine callback throws.                                                                        |
| `flow_recovery`       | A configured Flow recovery callback throws.                                                                       |
| `invalid_outcome`     | A handler/Node-recovery return is non-null, or Context/emission/report use is semantically invalid.               |
| `invalid_combination` | A Flow combine/recovery return is non-null, or Context/emission/report use is semantically invalid in that phase. |
| `unknown_action`      | A buffered emission cannot resolve to a matching link or declared scope exit during preflight.                    |
| `limit`               | A run/scope budget, depth, portable collection, or safe-integer bound would be exceeded.                          |
| `internal`            | A scheduler invariant fails after a valid run has started.                                                        |

Every `Failure` carries a nullable structured `detail`. Invalid outcome detail
uses one of these exhaustive reasons:

| Reason                      | Meaning                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| `wrong_return_type`         | A lifecycle callback returned anything other than `None` / `undefined`.                     |
| `invalid_action`            | An emission action is empty or not a string.                                                |
| `invalid_control_arguments` | A control overload, unlabelled-input wrapper, argument count, or captured bound is invalid. |
| `report_name`               | A report name is empty or not a string.                                                     |

`invalid_combination` uses the same reason vocabulary for a Flow callback.
Emission or report misuse inside a Flow callback is
`invalid_combination`; the same misuse inside a handler or Node recovery is
`invalid_outcome`.

The remaining kind/detail relationships are exact:

| Failure kind          | Detail                                                |
| --------------------- | ----------------------------------------------------- |
| `invalid_outcome`     | `InvalidOutcomeDetail`                                |
| `invalid_combination` | `InvalidCombinationDetail`                            |
| `unknown_action`      | `UnknownActionDetail` containing the validated action |
| `limit`               | `LimitDetail` naming the exhausted bound              |
| `internal`            | `InternalDetail` naming the invariant family          |
| all other kinds       | null                                                  |

`Failure.message` is a framework-owned literal and is never derived by
formatting `cause`:

| Kind                  | Exact message                      |
| --------------------- | ---------------------------------- |
| `handler`             | `Node handler raised`              |
| `handler_timeout`     | `Node handler timed out`           |
| `retry_policy`        | `Retry policy failed`              |
| `node_recovery`       | `Node recovery raised`             |
| `flow_combine`        | `Flow combine raised`              |
| `flow_recovery`       | `Flow recovery raised`             |
| `invalid_outcome`     | `Invalid callback outcome`         |
| `invalid_combination` | `Invalid Flow callback outcome`    |
| `unknown_action`      | `Unknown action`                   |
| `limit`               | `Run limit exceeded`               |
| `internal`            | `Caskada runtime invariant failed` |

The runtime never invokes Python `str` / `repr` or JavaScript
`message` / `toString` on a caught value. `cause` retains the exact caught
application object. Framework-detected timeout, wrong value/shape, unknown
action, limit, and invariant facts use null cause. Private Context misuse also
uses null cause.

Observer diagnostics follow the same no-coercion rule. Their exact messages are
`Observer raised`, `Observer must return synchronously`, `Observer result
inspection failed`, or `Observer reentrancy disabled`; a caught object is
retained only as opaque `cause`.
`LimitName` identifies `max_activations`, `scope_max_activations`,
`max_attempts`, `max_transitions`, `max_ready`, `max_reports`, `max_depth`,
`portable_collection`, or `safe_integer`. `InternalReason` identifies
`orphaned_live_token`, `packet_registry`, `counter_invariant`, or
`scheduler_invariant`. A new failure producer cannot reuse a catch-all reason;
adding a public reason or bound name requires the same schema-version and
cross-port fixture review as adding an event variant. The detail retains only
framework-owned enums or already-validated strings, so it never formats a cause
or introduces unbounded diagnostic work.

`attempt` has one matching provenance rule. `Context.attempt` and callback event
attempt fields are the one-based attempt number only for `phase="handle"`; they
are null for node recovery, Flow combination, and Flow recovery. A `Failure`
retains the originating handle attempt whenever its producing operation belongs
to that attempt. This includes handle/state/Context-method misuse, report-budget
overflow, `handler`, `handler_timeout`, `retry_policy`, result normalization or
preflight such as `invalid_outcome`, `unknown_action`, or `limit`, and an
unrelated post-signal handler error. It is null for failures produced by
recovery, combination, Flow-boundary work, an unowned scheduler operation, or
the handler-admission limit that prevented any attempt from existing.
Replacement does not copy the previous Failure's attempt into a newly produced
lifecycle phase; each Failure records its own producer.

The other provenance fields follow that same producer rule:

| Producing operation                                                                                         | `scope_id`                             | `activation_id` / `element_id`                                          |
| ----------------------------------------------------------------------------------------------------------- | -------------------------------------- | ----------------------------------------------------------------------- |
| scope-local direct-activation budget preflight                                                              | the exhausted receiving scope          | the producing Node or Flow activation and element                       |
| callback throw, timeout, policy, Context/state misuse, return normalization, or emission/boundary preflight | the producing callback Context's scope | the producing callback Context's activation and element                 |
| initial or retry handler-admission limit                                                                    | the receiving scope                    | the existing Node activation and element; no synthetic attempt          |
| nested-Flow entry, depth, ready, or activation allocation before the child exists                           | the parent/receiving scope             | the existing nested-Flow activation and element; no synthetic child IDs |
| scheduler operation with one concrete owner                                                                 | that owner's scope                     | that owner's activation and element                                     |
| genuinely unowned runtime invariant                                                                         | root scope `1`                         | null / null                                                             |

A combine or Flow-recovery callback therefore keeps its child callback
provenance when its buffered action fails ordinary boundary preflight, even
though a successful boundary result would have been committed into the parent
scope. The one deliberate exception is a parent scope's local activation budget:
that Failure names the exhausted receiving scope while retaining the producing
callback activation/element.
Packet transfer and replacement never rewrite producer provenance. Fence target
scope is a separate event/control fact and need not equal `Failure.scope_id`.

The originating failure kind is never inferred from exception class names. The
runtime assigns it at the boundary above, identically in both ports.

Only ordinary user-work failures enter recovery:

- a settled node-handler exception or cooperative attempt timeout may enter
  node retry and node recovery;
- a failed child element, Node recovery, or configured Flow combine callback may
  enter the smallest containing Flow recovery boundary;
- a failed nested-flow recovery appears as exactly one failed flow activation in
  its parent, which may then recover at the parent boundary.

The following are unrecoverable framework or definition failures and bypass
every node and flow recovery hook:

- invalid emission, retry policy, or Flow callback return;
- undeclared/unlinked action;
- activation, attempt, transition, ready, depth, or safe-integer limit;
- internal scheduler invariant failure.

They fence the complete run as `failed`. User cancellation and run deadline fence
the complete run as `cancelled`, not as recoverable failures. Observer failures
are nonfatal diagnostics.

### Scope failure

The first recoverable child failure changes its smallest containing scope from
`running` to `failing`:

1. Fence new admission and remember the primary failure.
2. Cancel ready activations and retry timers in that scope and all descendants.
   Any cancelled non-running activation that owns a packet merges that packet
   into the scope primary before it settles.
3. Signal every running callback through its scope/attempt cancellation. A
   packet-owning running activation keeps ownership until it settles.
4. Discard successful outcomes that settle after the fence; retain their user
   side effects, record later errors as suppressed failures, and merge any
   remaining sibling packet into the scope primary.
5. Wait for all running siblings and descendant packet transfers to settle
   within `cancel_grace_ms`.
6. If all settle and only the primary packet remains active, invoke configured
   Flow recovery once, or propagate immediately when none exists.
7. If any fail to settle, abandon the entire run and do not call recovery.

Non-running sibling packets merge in registry creation order during the scope
fence; running sibling packets merge in callback settlement/boundary-arrival
order. Each merge appends the sibling primary then inherited suppression, marks
that sibling packet `Merged`, and removes it from the registry. This includes a
failed sibling parked in a retry timer or queued for Node/nested-Flow recovery.
A run-level fence instead drains all still-active packets immediately. Therefore
a successful Flow recovery can never leave a sibling packet in the registry.
The packet that first fences the scope keeps its controlling input. Adopting or
passing that packet through a Flow boundary also preserves the same reference.
A sibling merge contributes only failure and suppression records; its input is
discarded and never replaces the scope primary's input. Only universal
replacement by newer work on the controlling packet may change that input under
the rule below. Flow recovery therefore receives one causally defined input even
when several differently-input branches fail concurrently.

`ScopeFailure` gives recovery the primary failure, later suppressed failures,
terminals committed before the fence, the failing activation, and
guarantees that all siblings settled. When a custom combiner fails after
successful quiescence, `ScopeFailure.result` contains its complete `ScopeResult`.
`failing_activation_id` is the direct child activation that failed at this scope
boundary; `Failure.activation_id` remains the callback activation where that
failure originated, so the IDs intentionally differ for an unhandled nested
failure. It is null when the Flow's own combine callback fails because no direct
child failed. Otherwise it remains the original direct child Node or nested-Flow
activation whose failure entered this scope, including when Flow recovery later
replaces the packet primary.

Suppression is transitive across Flow boundaries. Internally, a failed Flow
activation carries its primary plus the ordered suppressed failures from its
child scope:

- missing or zero-emission recovery carries that packet unchanged into the
  parent;
- if custom Flow recovery throws, the new `flow_recovery` failure becomes the
  packet primary, its `previous` points to the old primary, and the inherited
  suppressed list remains attached;
- if the parent is still running, the arriving packet primary becomes its scope
  primary and the packet's suppressed failures initialize its suppressed list;
- if the parent is already failing, it appends the arriving packet primary and
  then its inherited suppressed failures;
- later failures observed directly in that scope append in observation order.

Thus no descendant sibling failure disappears when a child failure is unhandled
or recovery throws. Ordering is boundary-arrival order, preserving each packet's
internal order. A successful custom recovery deliberately consumes its packet;
those handled failures remain observable in events and the recovery input but do
not appear in a successful final result. If run cancellation interrupts
settlement/recovery, the pending packet's primary followed by its suppressed list
is appended to `Cancelled.suppressed` or `Abandoned.suppressed`.

Flow recovery receives the active packet's controlling input and a fresh
cancellation token linked to the parent scope and run, not to the already-fenced
child scope. A successful recovery emission replaces the failed nested-flow
activation only after atomic commit. Zero emissions forward the packet without
changing identity. A thrown custom recovery follows the
replacement rule below. At the
root, unhandled or failed recovery produces `Failed` with inherited suppressed
failures intact.

A recoverable scope-failure fence is local, not yet a run-level failure fence.
If caller cancellation or the run deadline arrives while siblings are settling
or recovery is queued/running, it cancels or skips recovery and the run settles
as `Cancelled` (or `Abandoned` after grace). The earlier work failure is retained
in that result's `suppressed` failures.

A run-level failure fence is committed when an unrecoverable failure occurs, an
ordinary failure reaches the root after root recovery fails, or a locally
failure-controlled attempt/scope grace expires and is promoted to abandonment.
Once that fence commits, later cancellation only assists shutdown and cannot
replace its Failure cause. A run-level cancellation fence committed first
instead remains cancellation and later callback exceptions are retained in
`suppressed`.

Committing a run-level failure stops admission, signals every live callback, and
starts one non-resetting `cancel_grace_ms` interval at the fence timestamp. If
all callbacks settle before it expires, the result is `Failed` with later errors
in `suppressed`. If any callback remains live at expiry, the result is
`Abandoned(cause=primary_failure)` with every observed later error in
`suppressed`. A second error or a later `cancel()` call never restarts grace.

### Universal failure replacement

One internal `FailurePacket` owns a primary failure, inherited suppressed
failures in observation order, the controlling branch input, and exactly one
active runtime owner. It stores private `Failure` and input references only;
the run state is singular and remains invocation-owned independently of packet
movement.

Suppression is stored in observation-order immutable tuples/arrays. Replacing or
merging a packet copies that normally short sequence. `ScopeFailure.suppressed`
may be retained after recovery, and the final `RunResult.suppressed` uses the
same ordinary immutable representation. A persistent rope is not justified
without evidence of real workflows producing deep suppression chains.

Every packet follows this closed state machine:

| State                    | Registry membership                 | Permitted next state                                     |
| ------------------------ | ----------------------------------- | -------------------------------------------------------- |
| `Active(activation_id)`  | exactly once                        | another active owner, `Merged`, `Consumed`, or `Drained` |
| `Active(scope_id)`       | exactly once                        | another active owner, `Merged`, `Consumed`, or `Drained` |
| `Active(run)`            | exactly once until the fence commit | `Drained`                                                |
| `Merged(into_packet_id)` | absent                              | none                                                     |
| `Consumed`               | absent                              | none                                                     |
| `Drained`                | absent                              | none                                                     |

An activation owner covers its attempt, retry-policy evaluation, retry timer,
retry readmission, Node recovery, and emission preflight. None of those queue or
timer moves changes ownership. A scope owner covers sibling settlement, Flow
recovery, and its boundary preflight. Passing an unhandled child failure changes
the owner from child scope to its one parent Flow activation; the parent then
either adopts it as its scope primary, merges it into an already-failing scope,
or transfers it to the root run fence. No operation copies a packet.

Every new work failure is placed before its `failure_recorded` event. A handler
exception or attempt timeout creates `Active(node_activation)` with that
activation's input. A fresh combiner exception creates `Active(scope)` with the
Flow activation's input. A fresh unrecoverable callback/emission/boundary
failure first uses its producing activation or scope and transfers to
`Active(run)` in the same run-fence commit. An unowned scheduler invariant
failure creates `Active(run)` with the root input. Each new packet starts with
empty inherited suppression and is inserted once in registry creation order.
Caller cancellation and run deadline create no Failure packet.

A later attempt failure, retry-policy failure, Node/Flow recovery failure,
invalid recovery or combination, unknown action, limit, or internal failure
**while advancing an existing packet** replaces its primary:

1. construct the complete immutable new `Failure` with `previous` set to the old
   primary;
2. retain inherited suppression unchanged;
3. use the producing callback's input, or retain the old input when no newer
   callback input exists;
4. atomically update the packet and registry owner;
5. if the replacement is recoverable, only then publish `failure_recorded` and
   continue its retry or scope-failure path;
6. if the replacement is unrecoverable, in that same control commit transfer
   the packet to `Active(run)`, drain every active packet, and commit the run
   failure fence before delivering any observer event; then publish
   `failure_recorded`, run-target `failure_fenced`, and run-target
   `cancellation_fenced` in that order.

The same atomic run-fence sequence applies to a fresh unrecoverable failure.
Consequently an observer that calls `cancel()` while handling any of those three
events observes an already committed failed run; it may assist shutdown but
cannot change the result to `Cancelled`.

A successfully preflighted handler-after-retry, Node recovery, or Flow recovery
emission consumes its packet in the same atomic commit that publishes the
replacement transition. If preflight or commit fails, replacement happens
instead and the packet remains active. Missing or zero-emission recovery
transfers packet ownership; it does not consume or duplicate the packet.
Run-level cancellation during a retry timer or queued/running recovery
leaves the packet active for the run-fence drain. A recoverable scope fence
instead merges non-running packet owners immediately and running packet owners
when they settle, before Flow recovery can start.

An independent sibling failure initially creates its own active packet. When it
reaches an already-failing scope, one atomic commit appends its primary followed
by inherited suppression to that scope's primary packet, marks the arriving
packet `Merged`, removes it from the registry, and prevents any later drain or
transfer of it. These transitions preserve every descendant failure exactly
once.

Post-signal callback errors are not packet advancement. An unrelated error from
a callback after its attempt, scope, or run cancellation was signalled creates
one complete `Failure`. Its target is selected only from that callback wrapper:

1. if the wrapper owns an active packet, append to that packet and set
   `previous` to its current primary;
2. otherwise, if the wrapper is locally controlled by an active attempt/scope
   packet, append there and use that packet's primary;
3. otherwise, after a run drain, append to final suppression and use the
   wrapper's recorded drained-packet primary when present;
4. otherwise append to final suppression with `previous=None` / `null`.

An unrelated registry packet and the final run cause are never selected merely
because they exist. If an owning sibling packet later merges into a failing
scope, its primary and inherited suppression, including this appended error,
move together in their existing order. The append and all references commit
before `failure_recorded`. It creates no independent active packet and never
replaces an attempt's `handler_timeout` primary. Cooperative cancellation and a
returned value create no failure.

Because every `failure_recorded` observer runs only after Failure construction,
packet/registry replacement, merge, or suppression append has committed,
observer-triggered cancellation can never drain a half-updated packet.

### Run-fence drain

The first run-level fence atomically drains every active packet before signalling
callbacks. Active packets are registered in creation order. A failure fence
first transfers its controlling packet to `Active(run)`; that packet contributes
its primary as the result cause and its inherited suppression first. Every other
packet contributes its primary followed by inherited suppression in packet
creation order. Cancellation has no controlling failure packet, so every active
packet contributes to suppression in creation order. The commit marks every
packet `Drained` and removes every one from the registry before fence events or
signals are delivered. Before removal it records, on each live callback wrapper,
the primary of a packet that callback owned or that already controlled its local
attempt/failing scope. A healthy callback cancelled only by the new run fence
gets no such reference.

After the drain, each failure observed after the fence appends once in observation
order and never creates an active packet. Only that per-wrapper causal reference
may become `previous`; an unrelated final run cause may not. Only the newly
observed failure is appended.
Repeated cancellation cannot redrain or reorder packets. No `RunResult`,
including `Completed`, may settle while an active packet remains: every packet
must first be transferred, consumed, merged, or drained.

## Cancellation, timeout, and abandonment

Cancellation sources form a hierarchy:

```text
run source
  -> scope source
       -> fresh callback/attempt source
```

Cancelling a parent signals its existing children. It does not reuse a cancelled
child source for later recovery or retry.

Every fence uses one control/event order. First construct any Failure and commit
the complete control fact atomically: reason and timestamps, already-published
wrapper marks, admission stop, timer cancellation, packet transfer/merge/drain,
and final-status precedence. Next signal every affected cancellation token.
Only then deliver the public events in their documented order, and only after
those observers return may the scheduler process callback settlements published
by signalling. Thus observers always inspect committed, already-signalled state.
A synchronous TypeScript abort listener may run during signalling, but it sees
that committed fence; any settlement it publishes is merely queued, and a
reentrant cancellation cannot change precedence. Observer time still
backpressures the scheduler and counts toward applicable run/grace time.

All public events caused by one fence control commit form a contiguous
publication bundle. If an observer in that bundle calls `cancel()`, or the
mandatory post-observer timer checkpoint crosses another fence/grace, the nested
control fact commits and signals immediately but its event bundle is deferred
until the current bundle drains. Callback settlements are likewise not
processed between events in a bundle. Event sequence therefore never interleaves
a run fence between an attempt/scope fence's `failure_recorded` and cancellation
event. Pending publication uses the fixed four-slot state machine specified in
the observer section, not recursive delivery or an unbounded event buffer.

An attempt timeout follows the same rule locally: create/register its timeout
Failure, commit the attempt fence and grace timestamp, signal
`"attempt_timeout"`, then publish `failure_recorded` and the attempt-target
`cancellation_fenced` event. An observer cancellation cannot replace that
attempt token's first reason.

Every attempt, scope, or run fence records immutable `fenced_at` and
`grace_due = fenced_at + cancel_grace_ms` timestamps once. No sibling
settlement, additional failure, retry selection, parent fence, or cancellation
rewrites them. A callback protected by several fences uses the earliest due
grace. Settling all protected callbacks removes a timer; it does not reset one.
A recovery callback created only after failed children settle is new work and
receives a fresh parent-linked token, not an extension of child shutdown grace.

Cancellation is token-only in both ports. Caskada signals Python's
`Cancellation` object and aborts TypeScript's associated `AbortSignal`; it does
not inject `Task.cancel()` into Python callbacks and cannot cancel a JavaScript
Promise. A callback cooperates by checking/awaiting the token or by passing the
signal to work that honors it. A callback that ignores the token remains live in
both ports. This strict symmetry is less magical than Python task injection and
keeps grace/abandonment behavior portable. Synchronous code cannot be interrupted
in either port.

Settlement after a framework signal is normalized across the two ports:

- a node attempt whose own timeout fired always has a `callback_finished`
  disposition carrying the already-recorded `handler_timeout`, regardless of
  whether user code returns or exits through cancellation during grace;
- for a scope or run fence, a callback that returns is `discarded`;
- Python `asyncio.CancelledError` from user code that observed a signalled token
  is a cooperative `discarded` settlement;
- TypeScript rejection with the exact `AbortSignal.reason`, or with a
  `DOMException` named `AbortError` while that signal is aborted, is the same
  cooperative `discarded` settlement;
- any other callback exception becomes a suppressed `Failure` using that
  callback phase's kind. For an attempt timeout, its `failure_recorded` precedes
  `callback_finished`, but the disposition still carries the timeout primary.

The Python callback wrapper catches `BaseException`, not only `Exception`.
`asyncio.CancelledError` is cooperative only when the callback's associated
Caskada token had already been signalled before settlement; an unsignalled
`CancelledError` is the ordinary failure for that lifecycle phase. The same
ordinary normalization applies to `KeyboardInterrupt`, `SystemExit`, and
`GeneratorExit`. No Python exception escapes and invalidates the exactly-one
`RunResult` guarantee. Process or host shutdown belongs in an adapter that calls
`RunHandle.cancel()`, not in an exception escape from user work. TypeScript
likewise treats an uncorrelated `AbortError` or abort-like thrown value as the
ordinary lifecycle failure.

That catch domain applies at every Python runtime boundary that invokes or reads
application-controlled code, not only lifecycle callbacks. Before a handle
exists, option and initial-state mapping/sequence operations catch
`BaseException` and wrap `OptionValidationError` with the exact native cause.
After allocation, retry-policy calls and application-controlled state/mapping
operations catch it and use their already-defined lifecycle Failure kind and
provenance. Python control payloads themselves are retained directly and require
no application-container capture.
Observer invocation and return inspection catch it into the one nonfatal
`ObserverDiagnostic`. Only a lifecycle callback wrapper applies the
token-correlated `CancelledError` exception above; policy, observer, preflight,
and container-access boundaries never reinterpret a process-control exception
as cooperative cancellation. No user-controlled Python `BaseException` escapes
the scheduler after a handle exists.

The last rule applies only when the exception wrapper stamped
`settled_at < earliest_grace_due` and terminal status has not committed. Grace
expiry wins equality and later settlements; abandonment then discards the late
exception without allocating a Failure or publishing any event. The scheduler's
timer-before-settlement order enforces this for async callbacks, and synchronous
retry-policy work performs the same explicit completion checkpoint.

The scheduler marks callbacks already settled before it sends a signal. Their
exceptions are processed in settlement order and are not reclassified as
cancellation; an ordinary successful return may still have its buffered
emissions discarded because their transitions had not committed. This makes
explicit Python cancellation
and native TypeScript abort handling observably equivalent without hiding an
unrelated post-signal error.

Every node-handler attempt receives a fresh attempt source linked to the run
and scope. `Node.timeout_ms`, when configured, cancels only that attempt source.
The timed-out callback continues holding its scope slot and global callback
permit during the grace period, so a retry can never overlap the timed-out
attempt.

When the attempt timer wins, the runtime immediately records
`Failure(kind="handler_timeout")`, signals that attempt, and starts its grace
deadline. If the callback settles before grace, its buffered emissions are
discarded and that recorded failure enters retry policy or Node recovery. If it
does not settle before grace, no retry or recovery starts and the run becomes
`Abandoned(cause=timeout_failure)`.

An attempt-timeout fence is local while grace remains; it is not itself a
run-level cancellation or failure fence. If caller cancellation, the run
deadline, or an unrecoverable failure commits a run-level fence during that
grace, the run-level cause controls the eventual result and the timeout failure
is retained in `suppressed`. The already-running attempt grace is not extended:
the earliest applicable grace deadline controls shutdown. At a timestamp where
run deadline and grace expiry are both due, the run deadline fence commits first,
so an uncooperative result is `Abandoned(cause=deadline_cancellation)`. Grace
expiry uses `now >= grace_due`; expiry wins a tie with callback settlement.

If an attempt-timeout or recoverable-scope grace expires while no run fence
exists, that local failure becomes the run's abandonment cause in one atomic
promotion. The scheduler transfers the locally controlling packet to
`Active(run)`, drains every active packet, commits the run failure/cancellation
fence, signals affected run tokens, publishes the run-target `failure_fenced` and
`cancellation_fenced("run_failed")` events, and only then commits
`Abandoned(cause=that_packet.primary)`. No new Failure is allocated merely for
promotion. When several local grace timers are due together, heap
`(due_at, priority, insertion_sequence)` order selects the first timer; its
locally controlling packet is primary and all others enter suppression through
the drain. Later due timers observe the existing run fence and cannot replace
it.

Node recovery, flow combination, and flow recovery each receive a fresh callback
source. They are bounded by the run deadline and caller cancellation. If one is
signalled and fails to settle within grace, the run is abandoned.

Cancellation stops new callback admission, signals live callbacks, cancels
ready work and retry timers, and waits for grace. Settlement within grace returns
`Cancelled`. Grace expiry returns `Abandoned`. `Abandoned` is immutable:
late outcomes cannot add routes, terminals, events, or change status; all
surviving Context control capabilities are closed at the abandonment commit.
Escaped state/nested references and external effects remain outside that
boundary.

`Cancelled.suppressed` and cancellation-caused `Abandoned.suppressed` begin with
the active packets drained when their run fence committed, in registry order,
then append callback failures observed after that fence. Failure-caused
`Failed.suppressed` / `Abandoned.suppressed` begin with the controlling packet's
inherited suppression, then the other drained packets, then later observed
failures, exactly as the run-drain rule defines. Observer problems remain
separate `ObserverDiagnostic` records.

Python waiter cancellation has two explicit layers:

- cancelling a task awaiting `RunHandle.result()` re-raises
  `asyncio.CancelledError` in that waiter but does not cancel the underlying run;
  the handle remains independently settleable;
- cancelling a task inside `Flow.run()` or `CompiledFlow.run()` calls
  `handle.cancel("caller_cancelled")` and re-raises `CancelledError`; the handle
  settles later even though that convenience call does not return it.

TypeScript promises have no caller-task cancellation. Call `RunHandle.cancel()`
or pass an application `AbortSignal` through a future adapter; cancellation of a
started run resolves `RunHandle.result` with `Cancelled` or `Abandoned`.

Calling `RunHandle.cancel()` without a reason uses the string `"cancelled"` in
both languages. Every `CancellationInfo` therefore contains a present `reason`
field; `deadline=True` distinguishes the run deadline from caller cancellation.
In TypeScript, passing `undefined` is the same as omitting the argument.

The first `RunHandle.cancel()` call atomically commits the run cancellation fence
and wakes the scheduler; in the same event-loop critical section it snapshots
wrappers that already published settlement. It is not merely a queued
suggestion. Later calls are idempotent. A run-level failure fence already
committed is not replaced. Calling the handle from another OS thread is outside
the core contract; adapters must marshal such calls onto the owning event loop.

When `cancel()` is called while no public event bundle is being delivered, it
commits and signals first, then synchronously drains its cancellation publication
bundle and any fence or terminal bundle caused by the mandatory observer
checkpoints before returning. It does not admit work or harvest an unrelated
callback settlement inside that call. Observer time therefore consumes grace,
and zero or already-expired grace may make the handle done before `cancel()`
returns. When `cancel()` is called reentrantly from an observer or token listener,
the control commit and signal still happen immediately, but its public bundle is
placed in the bounded pending-fact state machine; `cancel()` returns to that
callback without recursive observer delivery, and publication resumes only
after the current bundle drains.

Framework-created cancellation reasons are portable literal strings:

| Source                                                         | `Context.cancellation.reason` | Final `CancellationInfo`, if any                               |
| -------------------------------------------------------------- | ----------------------------- | -------------------------------------------------------------- |
| omitted `RunHandle.cancel()`                                   | `"cancelled"`                 | reason `"cancelled"`, deadline false                           |
| explicit `RunHandle.cancel(value)`                             | the borrowed value            | the same value, deadline false                                 |
| Python `Flow.run()` / `CompiledFlow.run()` waiter cancellation | `"caller_cancelled"`          | reason `"caller_cancelled"`, deadline false                    |
| run deadline                                                   | `"deadline_exceeded"`         | reason `"deadline_exceeded"`, deadline true                    |
| node attempt timeout                                           | `"attempt_timeout"`           | none; timeout may become a suppressed or abandonment `Failure` |
| recoverable scope failure signalling siblings                  | `"scope_failed"`              | none; grace exhaustion uses the primary `Failure` as cause     |
| unrecoverable or root-level failure shutdown                   | `"run_failed"`                | no `CancellationInfo`; result cause is `Failure`               |

The first committed run-level fence fixes the final reason. Parent cancellation
propagates that same reason into existing descendants; a later signal does not
overwrite an already-cancelled token. Before cancellation, `reason` has no
portable value and user code must first test `cancelled`.

Framework fencing cannot stop an uncooperative synchronous callback, a JavaScript
promise that ignores its signal, a retained shared reference, or an external
side effect. The status describes what Caskada controls, not process isolation.

There is one unavoidable liveness precondition: the host event loop must regain
control. A synchronous callback, or async callback that never yields, can block
the scheduler thread indefinitely. While blocked, Caskada cannot observe timers,
deliver cancellation, publish events, or settle the handle. Finite blocking is
caught by the monotonic post-callback check when control returns; infinite
blocking requires process or worker isolation outside this in-process runtime.
Synchronous callbacks are not moved to threads because that would break browser
parity and silently change application-state semantics.

## Results and observation

After a run starts, its underlying `RunHandle.result` settles at most once and,
under the host-liveness precondition above, exactly once with `Completed`,
`Failed`, `Cancelled`, or `Abandoned`. Graph compilation and option validation
happen before a handle is returned and raise or throw
`GraphDefinitionError` or `OptionValidationError` directly.

Every `RunResult` exposes the run's one shared `state` and ordered root
`terminals`. `Completed.terminals` is nonempty and contains the root Flow's
combined terminal set. A non-completed result may have no terminals; when some
root branches committed before the controlling fence, it retains those records
in commit order without running a new combiner after the fence. Each terminal
contains its control kind and output-presence metadata; output-bearing terminals
also contain the exact application reference. Terminals never contain competing
workflow states. Default forwarding preserves kind, action, output presence and
reference, cardinality, and order. A custom combiner may deliberately replace
them before completion.

`start(initial_state)` is the complete interface: its handle resolves to the exact
`RunResult`, including terminals, failures, cancellation, statistics, and
diagnostics. `run(initial_state)` is the ordinary state projection over that same one
execution:

| Settled result                                              | `run(initial_state)`                            |
| ----------------------------------------------------------- | ----------------------------------------------- |
| any `Completed`, with any nonzero mix of end/exit terminals | return the exact shared state                   |
| `Failed`, `Cancelled`, or `Abandoned`                       | raise one `RunError` carrying that exact result |

`run()` never chooses a terminal, merges states, reruns work, or changes graph
semantics. It intentionally projects away terminal outputs and exit actions.
Use `start()` when terminal kind, action, or output matters. Ordinary stateful
workflows write their application result to `context.state` and receive it
directly.
Terminal plurality is therefore a graph-control fact, not a different shape for
the workflow state.

TypeScript `run()` must be a hand-written non-`async` function that creates the
final returned native Promise capability; it must not return state through an
intermediate `.then` chain. Before resolving a Completed run, it directly
installs an own configurable data property `then: undefined` on the state
object, retaining any prior own descriptor. It synchronously calls that final
Promise's native resolver with the exact state object, then restores the
prior descriptor or deletes the temporary property in `finally`, before any
reaction can run. The Promise resolution algorithm performs its `Get("then")`
synchronously, so callable state data named `then` is never invoked or awaited,
the exact carrier becomes the fulfillment value, and the exact descriptor is
visible again when user code resumes. Always masking also defeats an inherited
`Object.prototype.then`. `Promise.resolve(state)`, `async return state`, or
`return state` from another Promise reaction are explicitly nonconforming
implementations because they can assimilate the restored application value.

The returned successful map is the exact run-owned carrier with no additional
copy. The scheduler relinquishes it to application aliases after settlement;
the contract does not pretend those aliases are exclusive. Failure and
cancellation exceptions expose their partial shared map through
`error.result.state`.
Abandonment closes every Context control capability before exposing the state,
but an escaped state or nested reference and external work may still mutate
application data.

`RunStats` counters have one portable meaning:

| Field            | Meaning                                                                                                                                                                                                                                                                   |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `activations`    | Root Flow owner, every Flow entry, and every other atomically committed graph-element entry.                                                                                                                                                                              |
| `attempts`       | Node handler attempts admitted, including the first.                                                                                                                                                                                                                      |
| `transitions`    | Atomically committed buffered emissions, synthetic default routes, and forwarded terminals.                                                                                                                                                                               |
| `retries`        | Retry schedules committed, even if a later fence cancels the timer.                                                                                                                                                                                                       |
| `reports`        | Accepted `Context.report()` calls.                                                                                                                                                                                                                                        |
| `scopes`         | Runtime Flow scopes created, including root.                                                                                                                                                                                                                              |
| `peak_ready`     | Maximum total new activations in scope `pending` queues; admitted callback/resume/timer work is excluded.                                                                                                                                                                 |
| `peak_callbacks` | Maximum lifecycle callbacks simultaneously holding global permits, never above the invocation's effective explicit/automatic ceiling; synchronous retry policy retains its handler permit.                                                                                |
| `duration_ms`    | `min(MAX_SAFE_INTEGER, floor(elapsed_ms))` from the `run_started` commit through terminal status commit. Every observer and framework action before that commit is included; everything after it is excluded. `MAX_SAFE_INTEGER` therefore means that duration or longer. |

All counters describe committed facts. A rejected atomic batch contributes
nothing except any failure/event work needed to reject it.

Duration saturation affects only the public statistic. Deadline, retry, timeout,
and grace comparisons retain their full overflow-safe relative ordering and are
never shortened to the saturated value.

### Synchronous observer

Core accepts at most one synchronous observer. It has no asynchronous or
user-visible queue, task, stream, or persistence policy. The bounded internal
publication mechanism only prevents causal event interleaving; it is drained
synchronously before scheduler work resumes.

Every event list produced by one atomically committed framework fact is one
**contiguous publication bundle**. This includes the opening pair, lifecycle
callback settlement, an atomic emission or forwarding batch, a fence, and final
scope/run closure. A one-event fact is a one-event bundle. The runtime determines
the complete ordered list for the fact before invoking its first observer and
does not process a callback settlement or publish another fact between its
events. A fact committed reentrantly by an observer or token listener takes
effect and signals immediately, but its public bundle waits until the current
bundle drains.

There is no recursively delivered event stack. Pending publication is a fixed
state machine with four ordered slots:

```text
current bundle
optional one local attempt/scope-fence fact
optional one run-fence fact
optional one terminal fact
```

Slots are delivered in control-commit order. A slot is never overwritten or
duplicated. While one local-fence fact is pending, later observer checkpoints do
not commit another local timer fact; they may still commit the first run fence
and the one immutable terminal fact. A run fence prevents later local facts, and
a terminal commit prevents every later control fact. The checkpoint after an
observer otherwise commits only the next highest-priority timer fact. A
synchronous token listener may therefore produce the bounded chain local fence
to run fence to zero-grace terminal, but never a fifth publication fact.
Callback settlements published by signalling remain in their separately bounded
settlement structures and are processed only after the applicable bundles drain.
This is a constant-size control queue, not a user-visible/asynchronous observer
queue or retained event history.

For every framework event:

1. Commit the framework transition.
2. Increment the event sequence and construct the event.
3. Invoke the observer synchronously before the next scheduler transition.

Observer-triggered cancellation therefore affects only work after the event's
already-committed fact. Observer wall time counts toward the run deadline. An
observer invoked through `Context.report()` runs inside the callback and also
counts toward that node attempt's timeout.

The timer checkpoint after an observer still commits and signals the next newly
due fence immediately. Only that fact's public bundle waits until the current
bundle finishes; its control effect is not delayed.

`Context.report()` first checks its callback epoch, applicable cancellation
fences, and timers. A closed Context raises a framework error with no allocation,
event, or budget use. After an attempt, scope, or run fence, it creates nothing
and raises that callback's existing native cancellation. It then requires `name`
to be a nonempty string before checking report capacity. A wrong-type or empty
name is private semantic Context misuse; if uncaught by the application it is
`invalid_outcome`, and it consumes no report unit or event. Thus a fence wins
without inspecting the name, an invalid name wins over an otherwise exhausted
report budget, and only then can overflow win. An accepted call increments
`RunStats.reports` and consumes one `max_reports` unit whether or not an observer
is attached.

The first over-budget call records one unrecoverable `Failure(kind="limit")`,
commits the run fence, seals reporting for that Context, and raises native
cancellation. Every later caught call takes the already-fenced path and creates
no additional failure, event, diagnostic, ID, or budget use.

Calling `report("progress")` sets `has_data=False` / `hasData=false`; explicitly
passing `None`, `null`, or `undefined` sets it to true and retains that value.
Python uses a private missing-data sentinel internally but exposes public
`payload.data=None` when `has_data` is false; explicit `None` therefore has the
same field value with `has_data=true`. TypeScript inspects argument presence and
exposes a present `data=undefined` field when `hasData` is false; explicit
`undefined` has the same field value with `hasData=true`. Consumers branch on
the presence flag before reading application data; the private sentinel never
escapes.

Observer invocation is non-reentrant. If observer code calls `Context.report()`
through a captured live context, the nested call publishes nothing, consumes no
report budget, disables the observer, appends one diagnostic against the outer
event sequence, and returns normally. The outer observer may finish, but it will
not be called again. If it subsequently throws, that same disablement produces
no second diagnostic. `RunHandle.cancel()` remains valid inside an observer.

An observer-triggered `cancel()` commits and signals immediately but never calls
the observer recursively. Its pending fence bundle drains after the complete
current publication bundle. A `Context.report()` call whose observer cancels
therefore does not let the application callback resume between the report event
and pending cancellation events; after they drain, `report()` observes the fence
and raises the existing native cancellation.

An observer must return normally and synchronously. Python rejects an awaitable
or async-generator return; TypeScript rejects a returned thenable. Throwing or
returning one of those asynchronous values disables the observer and appends one
`ObserverDiagnostic`; it never changes workflow status. The failed observer is
not invoked to report its own failure. Forbidden asynchronous values use the
shared disposal algorithm above before scheduler publication resumes.

The runtime runs one final timer/fence checkpoint before a terminal status that
has not already been determined by a fence. A successful checkpoint is the
terminal control linearization instant: it fixes status, duration and other
`RunStats`, closes scopes, reserves final collection capacity, and makes later
cancellation a no-op. It then, without yielding or calling application code,
flattens final suppression once, materializes terminal/result records, and
constructs the terminal publication bundle of any still-open `scope_finished`
events and final `run_finished`. Crossing a due time during that internal work
does not undo the already-linearized result.

The run deadline, callback timeouts, and cancellation no longer apply after
terminal linearization. The runtime invokes the observer for each bundle event,
appends any diagnostics, freezes the result envelope after the final observer, and settles
`RunHandle.result`. All work after terminal control commit is excluded from
`duration_ms`, including the unobserved tail of an enclosing publication bundle,
previously committed pending fence bundles, and the terminal bundle itself. None
can reopen status. `run_finished` does not recursively include a diagnostic
caused while observing that same event.

Event and `report()` payloads are borrowed, read-only-by-contract references for
the duration of the observer call. An observer that retains or asynchronously
exports them must make its own copy. Slow or blocking observers deliberately
backpressure the scheduler. An extension can adapt this one hook to a bounded
queue, OpenTelemetry, an execution tree, or durable storage.

The event discriminator and payload pairing is normative in both ports:

| `kind`                 | Payload type / required content                                                                                                |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `run_started`          | root compiled element ID and root activation ID                                                                                |
| `run_finished`         | final status                                                                                                                   |
| `scope_started`        | scope/parent IDs, owner and entry activations, entry and Flow elements, depth                                                  |
| `scope_finished`       | scope ID, status, committed terminal sequences                                                                                 |
| `callback_started`     | scope, activation/parent IDs, element, phase, attempt; wrapper admission intent before the guarded user-code handoff           |
| `callback_finished`    | scope/activation, phase/attempt, discriminated route/fan-out/end/forward/unhandled, complete-failure, or discarded disposition |
| `retry_scheduled`      | scope/activation/failure IDs, failed and next attempts, delay                                                                  |
| `transition_committed` | source, branch ordinal, exact transition destination                                                                           |
| `terminal_committed`   | terminal/source IDs and end/exit metadata                                                                                      |
| `failure_recorded`     | one complete newly allocated `Failure`                                                                                         |
| `failure_fenced`       | discriminated run/scope target and existing complete `Failure`                                                                 |
| `cancellation_fenced`  | discriminated run/scope/attempt target, reason, deadline flag                                                                  |
| `report`               | scope/activation, name, data-presence flag, and borrowed application data when present                                         |

Callback disposition and transition kind describe different layers and are
assigned by this table; implementations do not infer one from terminal count or
destination after the fact:

| Settled callback control                                                  | `callback_finished` outcome | Per-arm `transition_committed.kind`                         |
| ------------------------------------------------------------------------- | --------------------------- | ----------------------------------------------------------- |
| zero-emission normal handler, after synthesizing its unlabelled route     | `route`                     | `route`                                                     |
| exactly one buffered `emit`, whether it reaches an activation or an Exit  | `route`                     | `route`                                                     |
| exactly one buffered `end`                                                | `end`                       | `end`                                                       |
| two or more buffered arms, including a mixed emit/end batch               | `fanout`                    | `route` for each emit; `end` for each end                   |
| absent/zero-emission Flow combine forwarding one or more child terminals  | `forward`                   | `forward_exit` or `forward_end` from each original terminal |
| zero-emission Node recovery or Flow recovery propagating its exact packet | `unhandled`                 | none                                                        |
| one or more recovery/combine emissions                                    | `route`, `end`, or `fanout` | the same buffered-arm rules above                           |

A callback rejected before control commit uses `failure`; an ordinary result
discarded under a pre-existing scope/run fence uses `discarded`. An
attempt-timeout-controlled callback keeps the timeout Failure disposition as
specified by the timeout rules. Forwarded Exit and End arms retain their source
kind even when the destination is another terminal.

Cross-language fixtures normalize ordinary casing differences but not field
presence. Every framework identifier or attempt that does not apply is still a
required field with `None` in Python and `null` in TypeScript. Every
`Failure.cause`, `Failure.detail`, `Failure.previous`, `ScopeFailure.result`, and
observer diagnostic `cause` all follow the same required-nullable rule. Report
`data` and its presence flag are always fields in both ports. This rule makes
event snapshots compare without interpreting language-specific omission habits.

`run_started` is sequence 1, root `scope_started` is sequence 2 in the contiguous
opening bundle, and `run_finished` is the final framework event. Every later
`scope_started` is emitted after creating a scope and before admitting its entry.
Every emitted `scope_started` has exactly one later `scope_finished`; an
already-finished scope is never closed or emitted again.

Natural/cooperative closure is structured: a scope closes only after its live
protected work and child scopes settle, so children precede their parent. After
each scheduler control step, compute the maximal set made closable by that step
and emit it in postorder `(depth descending, scope_id ascending)`. A scope made
closable only by a later observer-triggered control commit belongs to that later
publication bundle. Successful combination or recovery closes that scope `completed`;
unhandled/failed local recovery closes it `failed`; a descendant scope cancelled
as sibling work by an ancestor's recoverable failure closes `cancelled`. A
run-level failure closes every remaining cooperative scope `failed`; caller or
deadline cancellation closes them `cancelled`.

When the run can terminate, one terminal control commit fixes its `RunResult`
status, captures stats/duration, and closes every still-open scope atomically.
Successful root completion normally closes only root as `completed`; cooperative
run failure/cancellation closes remaining scopes `failed` / `cancelled`; grace
expiry closes every remaining scope `abandoned`. The terminal publication bundle
emits those `scope_finished` events in deterministic postorder
`(depth descending, scope_id ascending)`, followed by final `run_finished`.
Like every fact delivered after terminal commit, observer time for this bundle
is excluded from duration and cannot change status, though observer diagnostics
are still added before the result envelope freezes. Earlier naturally closed nested
scopes retain their prior event positions and are not re-emitted.

For every status, `scope_finished.terminal_sequences` is exactly that scope's
already-committed internal terminal sequence IDs in commit order. It includes
terminals committed before a failure/cancellation fence and excludes the new
boundary terminals produced by combine/recovery forwarding into the parent.
Internal quiescence creates `ScopeResult` but does not finish the scope. The Flow
first combines or recovers and commits its boundary result; `scope_finished`
then reports the complete Flow activation. Its status is `completed` after a
successful combine or recovery result, `failed` after unhandled/failed recovery,
or the corresponding cancellation/abandonment status. A callback-start event is
emitted after admission reservation and before the guarded handoff. It records
admission intent; its post-observer checkpoint may skip user invocation. After
settlement and timer classification, any newly created failure emits
`failure_recorded`, then the matching callback-finish event carries that complete
`Failure`; retry, transition, or fence events caused by the result follow. The
one exception is an unrelated post-timeout error: its suppression Failure is
recorded first, while callback-finish continues to carry the attempt's existing
`handler_timeout` primary. The `failure_recorded` and matching
`callback_finished` events are one callback-settlement publication bundle;
observer cancellation at the first event commits and signals immediately but
cannot insert its public event between them. Retry-policy work and any later
retry commit occur only after that bundle. Boundary propagation likewise begins
only after this bundle and its final checkpoint.

When a nested Flow recovery settles successfully with zero emissions and thereby
propagates its exact failure packet, or instead throws a recoverable
`flow_recovery` failure, first publish the callback-settlement bundle:

```text
optional failure_recorded for a thrown recovery
callback_finished(flow_recover, unhandled or complete failure)
```

Then run the final timer/fence checkpoint. If a controlling fence won during
that observer, do not propagate the boundary; its packet follows that fence and
the child later closes with the corresponding cancellation/failure status. If
the checkpoint passes, one atomic boundary commit transfers the packet to the
parent activation, marks the child scope failed, and, when this is the parent's
first failure, commits and signals the parent scope fence. Its second contiguous
publication bundle is:

```text
scope_finished(child, failed)
optional failure_fenced(parent scope)
optional cancellation_fenced(parent scope, "scope_failed")
```

The optional parent pair is absent when that parent was already fenced; packet
merge still commits before the child closure event. Parent recovery cannot be
admitted until the second bundle drains. Because the parent fence control and
signals precede the child `scope_finished` observer, observer cancellation cannot
overtake a boundary that passed its checkpoint. Cancellation from the earlier
callback-settlement observer can still win, because no boundary had linearized.

At the root there is no parent scope suffix. An exact unhandled root recovery,
or recoverable root-recovery throw, uses the same callback bundle and checkpoint.
If it passes, atomically transfer the packet to the run, drain the registry, and
commit/signal the run failure fence; publish the run
`failure_fenced`/`cancellation_fenced` bundle next. The later terminal bundle
closes the root `failed` and publishes `run_finished`. A chain of nested unhandled
recoveries repeats the two child-before-parent bundles at each boundary, then
uses this root sequence exactly once.

After the preceding callback-settlement bundle and final checkpoint, an atomic
emission or forwarding batch commits completely before its transition observers
run.
The runtime then publishes `transition_committed` in branch order and publishes each
corresponding `terminal_committed` immediately after a terminal-producing
transition. That entire ordered event list is one publication bundle. Observer
cancellation at its first transition commits and signals immediately, but its
public fence bundle and callback settlements wait until every transition and
terminal event for the already-committed batch has been delivered.

For a successful nested Flow boundary, that same atomic commit marks the child
scope completed and appends its `scope_finished(child, completed)` event after
the batch's last transition/terminal event in this same bundle. It therefore
cannot require another pending publication slot or be overtaken by an observer
of the committed transition. A root boundary instead linearizes `Completed` with
its final batch and leaves root `scope_finished` to the terminal bundle.

For `transition_committed`, a routed transition names its action and has exactly
one discriminated destination: an activation with activation/element IDs, or a
terminal with its sequence. `end` and `forward_end` always have a terminal
destination and no action. `branch_index` is zero-based within the committed
emission or forwarded terminal batch. `terminal_committed.terminal` is itself
discriminated: an end reports its kind and output-presence, while an exit reports
its kind, possibly-null action, and true output-presence.

The `scope_id` on transition and terminal events is the scope that receives the
committed result, not necessarily the scope in which its callback ran. A node
result commits in its current scope. A nested Flow's combine or recovery callback
runs in the child scope, but its result replaces the suspended token and commits
in the parent scope. A root combine/recovery boundary has no parent and uses root
scope ID 1. Boundary transition/terminal events are emitted before that child or
root `scope_finished` event. The scope-finished payload lists only its internal,
pre-combine terminal sequences; `Completed.terminals` contains the separately
allocated combined root boundary terminals.

Fence events have exactly these producers and orders:

The complete fence control commit and token signalling precede every event in
the corresponding row; the table orders public delivery, not internal signal
delivery. Every row's events are one contiguous publication bundle. When the
same control step creates a new Failure, its leading `failure_recorded` is in
that bundle; when it consumes a settled lifecycle callback, the matching
`callback_finished` remains in its already specified position in the same
bundle. A nested run fence may commit during an observer but its events follow
the complete current row.

| Fact                                    | Events                                                                                                                                                                 |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Any new `Failure`                       | One `failure_recorded` before any callback, retry, fence, or result references its `failure_id`.                                                                       |
| Node attempt timeout                    | `failure_recorded`, then one attempt-target `cancellation_fenced("attempt_timeout")`; no failure fence unless the failure later fences a scope/run.                    |
| Recoverable scope failure               | One scope-target `failure_fenced`, then one scope-target `cancellation_fenced("scope_failed")`; inherited descendant signals publish no additional cancellation event. |
| Unrecoverable or root-unhandled failure | One run-target `failure_fenced`, then one run-target `cancellation_fenced("run_failed")`. The same failure may previously have fenced one or more scopes.              |
| Caller cancellation or deadline         | One run-target `cancellation_fenced`; there is no failure event.                                                                                                       |
| Failure-caused grace abandonment        | The applicable run-target `failure_fenced`/`cancellation_fenced` pair is committed before `run_finished("abandoned")` if no run fence existed already.                 |

Each scope target and the run target can fence at most once. Later causes are
suppressed data and do not emit another fence event for that same target. An
attempt target emits at most once. `failure_recorded` still exposes every later
suppressed failure. `cancellation_fenced.deadline` is true only for the run
deadline; an attempt-target event is identified by its target and has
`deadline=false`. The event-capacity bound includes all of these records.

Every target transition records its new activation ID and source activation ID.
Each callback-start event adds the target's element, scope, and bounded parent;
each scope-start event identifies its owning Flow activation. Those records plus
`CompiledFlow.describe()` are sufficient to reconstruct execution causality
without a growing path stored in the scheduler. Framework event discriminators
and field shapes are fixed by this RFC. Several fields deliberately retain
borrowed application values: Failure and diagnostic `cause`, cancellation
`reason`, report `name` and optional `data`, action labels, and caller-supplied
`run_id`. Observers and adapters must not assume those values are serializable,
immutable, or safe to format.

### Inspection

`CompiledFlow.describe()` returns a fresh value with this exact, language-neutral
JSON shape (snake-case field names in both ports):

```json
{
  "schema_version": 1,
  "auto_max_concurrency": 1,
  "root": {
    "element_id": 1,
    "scope_definition_id": 1
  },
  "scope_definitions": [
    {
      "scope_definition_id": 1,
      "owner_element_id": 1,
      "parent_scope_definition_id": null,
      "entry_element_id": 2,
      "exits": [],
      "concurrency": 1,
      "max_activations": null
    }
  ],
  "elements": [
    {
      "element_id": 1,
      "kind": "flow",
      "name": "Flow",
      "parent_scope_definition_id": null,
      "owned_scope_definition_id": 1,
      "links": []
    },
    {
      "element_id": 2,
      "kind": "node",
      "name": "draft",
      "parent_scope_definition_id": 1,
      "links": [{ "action": null, "target_element_id": 3 }],
      "retry": { "max_attempts": 1 },
      "timeout_ms": null
    },
    {
      "element_id": 3,
      "kind": "node",
      "name": "deliver",
      "parent_scope_definition_id": 1,
      "links": [],
      "retry": { "max_attempts": 1 },
      "timeout_ms": null
    }
  ]
}
```

`auto_max_concurrency` is the maximum `concurrency` in
`scope_definitions`, with a minimum of one. It is computed from the definition
only and never reflects a run option or observed callback count. The arrays and
link lists use deterministic compilation/declaration order. IDs start at one and
are assigned by the iterative first-discovery traversal.
Every nested Flow element owns one compiled scope definition; every runtime entry
of it gets a fresh runtime scope ID reported by events and a fresh
direct-activation counter used by scheduling. `max_activations` is null when that scope definition
has no local cap. Root Flow links are
empty in this compiled view because direct-root outgoing links are ignored;
the mutable definition's `links()` still reports what the author declared.

Flow elements omit `retry` and `timeout_ms`; Node elements omit
`owned_scope_definition_id`. Nested Flow elements have both a non-null parent
scope definition and an owned child definition. No other field is optional.
`describe()` does not serialize callbacks, retry predicates/delay policies,
arbitrary configuration, dependencies, or invocation state. Mutating any returned
array/object cannot change the compiled topology or a later description.

`links()` supports definition-time local inspection. `describe()` supports
compiled scope-aware inspection. Events support runtime inspection. These three
surfaces replace raw successor access and the mandatory `ExecutionTree`.

## Complexity

Let:

- `V` be compiled placements;
- `E` be links;
- `A` be activations;
- `M` be admitted Node attempts;
- `T` be committed buffered emissions, synthetic default routes, and forwarded
  terminals;
- `O` be every control arm examined by normalization or preflight, committed or
  rejected: buffered `emit`/`end` arms, phase-default synthetic arms, and
  terminals forwarded across Flow boundaries;
- `S0` be initial top-level state bindings copied before start;
- `S` be peak top-level bindings in the one shared run state;
- `X` be every Context API operation attempted, including caught/rejected state,
  emit, end, report, deadline, and cancellation calls;
- `K` be all keys/properties visited by framework validation, capture,
  enumeration, spread, or mapping operations, including rejected operations;
- `C` be peak retained emission-buffer slots plus live activation/terminal input
  and present-output references and one `ScopeResult.outputs` projection slot per
  output-bearing retained terminal;
- `F` be the peak retained `Failure` records plus packet, registry, previous, and
  suppression-reference slots;
- `L` be total Failure-record allocations and suppression references copied;
- `H` be all timer-heap operations (deadline, attempt, grace, and retry);
- `Q` be accepted application report events;

The required bounds are:

```text
compile time:    O(V + E)
compile space:   O(V + E)
run time:        O(V + E + A + M + T + O + S0 + X + K + L + Q + H log H)
scheduler space: O(V + E + ready + live activations + live scopes
                   + live timers + retained terminals + S + F + C
                   + publication records)
```

Each pending activation enters and leaves one scope deque a constant number of
times. Each eligible scope enters, leaves, or changes ready-scope category a
constant number of times per FIFO-head/capacity change. No reachable suffix is
cloned per visit, no call stack grows with graph depth, and no queue-wide
eligibility scan is used.
Computing `auto_max_concurrency` folds one maximum through the existing
compilation traversal with one constant-size accumulator, so it adds no
asymptotic term.
Timer storage removes expired entries and may lazily discard cancelled entries.
Publication control retains exactly the current,
optional local-fence, optional run-fence, and optional terminal fact slots. Their
event records are bounded by the current atomic emission/forwarding batch plus
the scopes closed by one terminal commit and a constant number of callback/fence
events; no delivered event history is retained.

Packet replacement and pass-through copy ordinary suppression tuples/arrays.
`L` already counts those copied references; no separate asymptotic promise is
needed for failure chains that normal workflows keep short.

A scalar emission, Flow entry, and individual terminal commit are `O(1)` in
state width. A fan-out of `N` emissions costs `Theta(N)` framework time and
space for control and input references; it never copies or scans the shared
state. Forwarding `N` terminals across a Flow boundary likewise costs
`Theta(N)` metadata/reference work. Materializing one `ScopeResult` and its sole
ordered output projection costs `Theta(N)` time and `Theta(N)` retained output
references; there are no separate end/exit projections. Initial state capture
costs `Theta(S0)`; successful `run()` publishes the same carrier in `O(1)`. There is no
`O(A*S)`, `O(N*S)`, branch merge, or final-state copy term.

The persistent native state map requires no settlement rescan. State width
contributes to `S` but is deliberately not a run budget. A rejected Context call
is still charged to `X`. An
oversized emission buffer is rejected before an append exceeds its portable or
run budget. Each accepted `emit`/`end` stores
only a fixed-size intent plus one borrowed input/output reference, even if the
buffer is later discarded. Conformance instrumentation must prove that wide
state does not change fan-out cost.

User callback work, observer work, the reachable size of borrowed input/output
values, arbitrary state/nested-object mutation, and application copying are
outside these bounds except for the explicit `S`/framework-operation terms.
State width and nested object size are not byte-budgeted; hostile code memory
containment requires a process boundary.
`max_transitions` bounds terminal storage and terminal-only fan-out;
`max_reports` bounds application-created event traffic and the validated
event-capacity formula keeps event IDs portable. A
100,000-node linear graph must compile and run without language call-stack growth
when the fixture sets `max_activations=100_001` for its root Flow activation plus
its nodes.

## Examples

The first examples use the complete everyday grammar: wrap functions with
`node`, read and write `context.state`, optionally move a branch value through
`context.input`, choose control with `emit` or `end`, connect occurrences with
`link`, and run a `Flow`.

### Linear work

```python
from typing import NotRequired, TypedDict

from caskada import Context, Flow, node


class ProjectState(TypedDict):
    question: str
    draft: NotRequired[str]


async def write_draft(question: str) -> str:
    return question.upper()


def publish(draft: str) -> None:
    assert draft


@node
async def draft(context: Context[ProjectState]) -> None:
    context.state["draft"] = await write_draft(
        context.state["question"],
    )
    # No emission means the unlabelled link with the current input.


@node
def deliver(context: Context[ProjectState]) -> None:
    draft_value = context.state.get("draft")
    if draft_value is None:
        raise ValueError("draft is missing")
    publish(draft_value)
    # No emission exits the root Flow.


draft.link(deliver)


async def run_project() -> None:
    state = await Flow(draft).run(
        {"question": "Why does rain fall?"},
    )
    assert state.get("draft")
```

`run()` returns the invocation's one shared state after every root branch ends.
There is no result wrapper or terminal selection in this ordinary case. The
caller input is shallow-copied once, so `state` is the run-owned top-level
mapping rather than the object passed to `run()`.

### Branching and declared exits

```python
from caskada import Context, Flow, node


@node
def triage(context: Context[dict[str, object]]) -> None:
    if context.state.get("requirements_complete"):
        context.emit("build")
    else:
        context.emit("needs_input")


@node
def build(context: Context[dict[str, object]]) -> None:
    context.state["built"] = True
    # No emission exits the current Flow.


triage.link(build, "build")

orchestrator = Flow(
    triage,
    exits=("needs_input",),
)


async def inspect_exit() -> None:
    handle = orchestrator.start({"requirements_complete": False})
    result = await handle.result()
    assert result.status == "completed"
    terminal = result.terminals[0]
    assert terminal.type == "exit"
    assert terminal.action == "needs_input"
```

A declared exit is successful graph completion. `run()` would return the shared
state and deliberately discard its terminal metadata; use `start()` when an exit
is part of the application protocol. Emitting `"need_input"` fails because it is
neither linked nor declared.

### The same linear model in TypeScript

```typescript
import { Flow, node } from 'caskada'

import type { Context } from 'caskada'

interface ProjectState {
  question: string
  draft?: string
}

declare function writeDraft(question: string): Promise<string>
declare function publish(draft: string): void

const draft = node<ProjectState>(
  async (context: Context<ProjectState>) => {
    context.state.draft = await writeDraft(context.state.question)
    // No emission means the unlabelled link with the current input.
  },
  { name: 'draft' },
)

const deliver = node<ProjectState>(
  (context) => {
    publish(context.state.draft!)
    // No emission exits the root Flow.
  },
  { name: 'deliver' },
)

draft.link(deliver)

const state = await new Flow<ProjectState>(draft).run({
  question: 'Why does rain fall?',
})
console.log(state.draft)
```

The two ports expose the same graph and control model. TypeScript uses the
`node(handler, options)` function because decorators would add a language-specific
authoring concept.

### Dynamic fan-out and structured combine

Branch input carries per-item work. Shared state remains singular:

```python
from typing import TypedDict, cast

from caskada import Context, Flow, ScopeResult, node


class MapState(TypedDict):
    items: list[str]
    results: list[str]


class Job(TypedDict):
    index: int
    item: str


class Row(TypedDict):
    index: int
    value: str


inputs = ["alpha", "beta"]


async def process(item: str) -> str:
    return item.upper()


@node
def dispatch(context: Context[MapState]) -> None:
    if not context.state["items"]:
        # Hard-end this control arm without producing a worker output.
        context.end()
        return

    for index, item in enumerate(context.state["items"]):
        context.emit(
            "work",
            {"index": index, "item": item},
        )


async def worker_handler(context: Context[MapState, Job]) -> None:
    job = context.input
    value = await process(job["item"])
    context.end(
        {"index": job["index"], "value": value},
    )


def require_row(output: object) -> Row:
    if type(output) is not dict:
        raise TypeError("worker output must be a row")
    record = cast(dict[object, object], output)
    index = record.get("index")
    value = record.get("value")
    if type(index) is not int or not isinstance(value, str):
        raise TypeError("worker output must be a row")
    return {"index": index, "value": value}


async def collect(
    context: Context[MapState],
    result: ScopeResult,
) -> None:
    if len(result.outputs) != len(context.state["items"]):
        raise ValueError("worker output count mismatch")
    rows = [require_row(output) for output in result.outputs]
    context.state["results"] = [
        row["value"]
        for row in sorted(rows, key=lambda row: row["index"])
    ]
    # Zero emissions forward the exact worker terminals.


worker = node(worker_handler, name="worker")
dispatch.link(worker, "work")

mapping = Flow(
    dispatch,
    concurrency=8,
    combine=collect,
)


async def run_mapping() -> None:
    initial_state: MapState = {"items": inputs, "results": []}
    state = await mapping.run(initial_state)
    assert len(state["results"]) == len(inputs)
```

The `Flow` waits for all worker tokens, then calls `collect` once. Its compiled
automatic callback ceiling is eight, matching the largest local Flow cap, so no
duplicate run option is needed. `worker_handler` is reusable behavior; another
graph factory would call `node(worker_handler)` again for a distinct occurrence
and distinct links. Each worker intentionally calls `end(row)`
because its branch must publish a transformed worker output; zero emissions would
instead exit with the unchanged `Job` input. The combiner validates and orders
the `unknown` / `object` application outputs, then writes the aggregate into the one
shared state. Zero combiner emissions preserve the original terminals, so
`run()` still returns the shared state even when there are many end terminals.

For an empty source, `dispatch` calls no-output `end()`. The Flow still receives
one hard-terminal control record, but `ScopeResult.outputs` is empty, so the same
cardinality check and aggregation code handles zero, one, and many items. Explicit
`end(value)` is the output-producing form; no extra `drop` verb is needed.

The equivalent TypeScript is intentionally the same shape:

```typescript
import { Flow, node } from 'caskada'

import type { Context, NodeHandler, ScopeResult } from 'caskada'

interface MapState {
  items: readonly string[]
  results: string[]
}

interface Job {
  index: number
  item: string
}

interface Row {
  index: number
  value: string
}

declare const inputs: readonly string[]
declare function processItem(item: string): Promise<string>

const dispatch = node<MapState>(
  (context) => {
    if (context.state.items.length === 0) {
      // Hard-end this control arm without producing a worker output.
      context.end()
      return
    }

    context.state.items.forEach((item, index) => {
      context.emit('work', { index, item } satisfies Job)
    })
  },
  { name: 'dispatch' },
)

const workerHandler: NodeHandler<MapState, Job> = async (context) => {
  const job = context.input
  context.end({
    index: job.index,
    value: await processItem(job.item),
  } satisfies Row)
}

const worker = node(workerHandler, { name: 'worker' })

function isRow(output: unknown): output is Row {
  if (typeof output !== 'object' || output === null) return false
  const candidate = output as Record<string, unknown>
  return typeof candidate.index === 'number' && typeof candidate.value === 'string'
}

const collect = (context: Context<MapState>, result: ScopeResult): void => {
  const outputs = result.outputs
  if (outputs.length !== context.state.items.length || !outputs.every(isRow)) {
    throw new Error('worker output mismatch')
  }
  const rows = [...outputs].sort((left, right) => left.index - right.index)
  context.state.results = rows.map((row) => row.value)
}

dispatch.link(worker, 'work')

const mapping = new Flow<MapState>(dispatch, {
  concurrency: 8,
  combine: collect,
})

const initialState: MapState = { items: inputs, results: [] }
const state = await mapping.run(initialState)
console.log(state.results)
```

Parallel callbacks share `context.state`. Their suspension-order writes are
therefore timing-dependent. The example avoids that race by publishing one
output per worker and mutating shared state only in the combiner. Parallel
workflows may instead write disjoint locations or coordinate through an injected
synchronization service.

### Input and output forwarding

Omitting an `emit` input forwards the current input. Supplying a nullish value is
different from omission. For `end`, omission means no output and a supplied
nullish value remains a real output:

```python
from typing import Any

from caskada import Context, node


@node
def relay(context: Context[dict[str, Any], object]) -> None:
    context.emit("same")                  # forwards context.input
    context.emit("empty", None)           # next input is explicitly None
    context.end()                         # no output
    context.end(None)                     # output is explicitly None
```

Each call appends one private intent. Calls schedule nothing immediately, return
`None` / `void`, and retain source order. If the callback throws, times out, is
cancelled, or returns a non-null value, the whole emission buffer is discarded.
Direct state writes and external effects are not rolled back.

### Loop

```python
from typing import TypedDict

from caskada import Context, Flow, node


class ImproveState(TypedDict):
    iteration: int
    budget: int


async def improve_artifact(state: ImproveState) -> None:
    assert state["iteration"] <= state["budget"]


@node
async def improve(context: Context[ImproveState]) -> None:
    context.state["iteration"] += 1
    await improve_artifact(context.state)

    if context.state["iteration"] < context.state["budget"]:
        context.emit("again")
    # Otherwise zero emissions exit this Flow through its unlabelled boundary.


improve.link(improve, "again")


async def run_improvement() -> None:
    state = await Flow(improve).run(
        {"iteration": 0, "budget": 5},
    )
    assert state["iteration"] == state["budget"]
```

The loop is ordinary topology. `max_activations`, `max_attempts`,
`max_transitions`, and an optional deadline provide run-wide bounds.

### Recovery, cancellation, and advanced results

```typescript
import { Flow, node } from 'caskada'

import type { NodeRecoveryHandler } from 'caskada'

interface FetchState {
  url: string
  body?: string
}

declare const shutdownSignal: AbortSignal
declare const url: string
declare function cachedBody(url: string): string

const cached = node<FetchState>((context) => {
  context.state.body = cachedBody(context.state.url)
  // Zero emissions exit this Flow through its unlabelled boundary.
})

const recoverFetch: NodeRecoveryHandler<FetchState> = (context, failure) => {
  if (failure.kind === 'handler') {
    context.emit('cached')
  }
  // Zero emissions for every other failure propagate its exact packet.
}

const fetchNode = node<FetchState>(
  async (context) => {
    const response = await fetch(context.state.url, {
      signal: context.cancellation.signal,
    })
    context.state.body = await response.text()
    // Zero emissions exit this Flow through its unlabelled boundary.
  },
  {
    name: 'fetch',
    retry: { maxAttempts: 3, delayMs: 250 },
    timeoutMs: 5_000,
    recover: recoverFetch,
  },
)

fetchNode.link(cached, 'cached')

const handle = new Flow<FetchState>(fetchNode).start(
  { url },
  {
    observer(event) {
      if (event.kind === 'failure_recorded') {
        console.error(event.payload.failure.message)
      }
      if (event.kind === 'retry_scheduled') {
        console.info(event.payload.nextAttempt)
      }
    },
  },
)

shutdownSignal.addEventListener('abort', () => {
  handle.cancel('shutdown')
})

const result = await handle.result
if (result.status === 'completed') {
  console.log(result.state.body, result.terminals)
}
```

`start()` is the lossless advanced API: it exposes terminals, failures,
suppression, cancellation, abandonment, stats, and observer diagnostics. Every
result variant also contains the same shared state; it may be partial after
failure or cancellation and may contain nested references still changed by
uncooperative work after abandonment.

### Semantic router extension

```python
from dataclasses import dataclass
from typing import Protocol

from caskada import Cancellation, Context, Node, node


@dataclass(frozen=True)
class RouteDecision:
    action: str
    input: object


class DecisionEngine(Protocol):
    async def choose(
        self,
        *,
        request: str,
        routes: object,
        cancellation: Cancellation,
    ) -> RouteDecision: ...


def semantic_router(
    decision_engine: DecisionEngine,
    routes: object,
) -> Node[dict[str, object]]:
    async def choose(context: Context[dict[str, object]]) -> None:
        request = context.state.get("request")
        if not isinstance(request, str):
            raise ValueError("request must be a string")
        decision = await decision_engine.choose(
            request=request,
            routes=routes,
            cancellation=context.cancellation,
        )
        context.emit(decision.action, decision.input)

    return node(choose, name="semantic_router")
```

The router is a function-backed ordinary node occurrence. Route descriptions,
schemas, selection policy, coding-agent drivers, and dynamically authored
workflow contracts remain in the proposed Jig Graph layer or another extension.
Caskada contributes
links, declared exits, compiled inspection, cancellation, and execution. The
extension's `RouteDecision` is its own domain object; Caskada core exports no
decision object.

## Cookbook design validation

Before API freeze, the proposed grammar was applied to eight existing Python
cookbook projects. They remain readability-first teaching programs rather than
production templates, and now execute against the Python v3 runtime.

| Experimental port     | Authoring question exercised                                                         |
| --------------------- | ------------------------------------------------------------------------------------ |
| `python-hello-world`  | typed state and ordinary zero-emission leaf exit                                     |
| `python-flow`         | `end()` bypassing an otherwise automatic unlabelled loop                             |
| `python-batch-node`   | fan-out workers, `end(value)`, `ScopeResult.outputs`, and one `combine=`             |
| `python-nested-batch` | two nested aggregation levels with the original serial shape                         |
| `python-rag`          | reusable map/combine and state handoff across two intentional run boundaries         |
| `python-supervisor`   | nested Flow continuation, named retry loop, and ordinary accepted leaves             |
| `python-thinking`     | a self-loop, local activation cap, whole-handler retry, and ordinary exit            |
| `python-tool-crawler` | crawl fan-out, per-page terminal outputs, local combine, and one report continuation |

The first design-pressure pass was useful but overbuilt. It made individual
lifecycle methods smaller while burying the author model under type models,
casts, validators, cancellation checkpoints, thread wrappers, and production
caveats. A pedagogy pass then compared every port directly with its v2 source,
restored its recognizable prompts, data, serial or parallel shape, and run
boundaries, and removed machinery unrelated to the lesson. Three small ports
were added so zero-emission exit, hard `end`, and combining can be learned
separately before they appear together in nested examples.

The exercise still exposed real API pressure. Repeating a local Flow concurrency
cap in `RunOptions` was misleading; collectors should not filter terminal kinds
merely to obtain values; literal retry waits should not require a callback; and
`end()` needed an output-less form so an empty dispatcher would not manufacture a
value. RAG also makes copy-in ownership visible: two intentional runs require the
state returned by the offline run to become the online run's input.

Those reviews produced the binding D7/D8 corrections in this RFC:

- public call-site input is named `initial_state` / `initialState`, and one
  logical workflow may compose phases beneath one root invocation while
  intentional run boundaries explicitly pass the returned state onward;
- an omitted run callback limit uses the maximum local concurrency in compiled
  Flow scope placements, while explicit smaller/larger values remain available;
- `ScopeResult.outputs` is the sole ordinary ordered projection, with
  `terminals` retained for control-sensitive code;
- `Context<State, Input>` provides optional local branch-input typing without
  pretending links are payload-typed;
- Flow combine/recovery input stays the honest dynamic `object` / `unknown`
  boundary;
- one persistent run-owned state carrier replaces the earlier callback-revocable
  facade, so `TypedDict`/record typing and retained aliases match runtime truth;
- retry delay accepts a validated integer constant as well as a callback;
- `end()` records a hard terminal without an output, while `end(value)` publishes
  one, so an empty dispatcher no longer fabricates a value; and
- an optional Flow-local direct-activation cap gives every runtime scope
  invocation an independent aggregate component budget without restoring a
  hidden per-node default.

The review rejected adding a borrow-mode run, `emit_many`, `drop`, `forward`,
`collapse`, exact per-node `max_visits`, or an output generic. A local output
parameter cannot be captured symmetrically through TypeScript's `Flow` class
constructor without `any`, a variance hack, a second Flow type parameter, or a
new constructor abstraction. The review also rejected removing `@node`, `end`,
zero-handler default routing, or exact zero-combine forwarding. Applications may
narrow or validate collected outputs when their own trust boundary requires it;
the cookbook does not add that ceremony to examples whose lesson is control flow.

The final set deliberately mixes one small typed example, whose project types
live in `models.py`, with seven examples that omit project type models. It preserves
the important retry rule by committing thinking state only after fallible model
and parsing work, but otherwise avoids production hardening that obscures the
graph. Independent diff review found no blocker or major in the author surface or
the readability-focused simulations.

The eight projects first ran as one deterministic smoke suite against the real
Python v3 kernel. The implementation pass then migrated the complete official
cookbook: all 36 Python projects and both TypeScript projects now use the v3
authoring surface. Repository cookbook verification executes every Python graph
with test-owned service fakes; the two TypeScript projects pass strict type
checking and deterministic execution with the workspace package and test-owned
fakes. The suite covers documented state, routing, fan-out, terminals, combine,
nested exits, retry topology, state handoff, interaction adapters, and provider
boundaries. This is authoring and integration evidence, but not a substitute for
shared kernel conformance, browser parity, live-provider integration, or the
fresh reviews required by the release gates.

## Alternatives considered

### Return control objects

Exported `Go`, `NEXT`, `End`, `Fork`, and `LocalPatch` made control explicit by
turning runtime lowering terms into author vocabulary. Returning Context-created
decision objects removed some imports but retained two competing protocols:
imperative state mutation and returned control values. It also made accidental
missing returns a hidden control bug and required special handling for list
fan-out.

The accepted model keeps the real distinctions while reducing concepts:
`context.emit` buffers a route, `context.end` buffers a terminal, call count is
cardinality, and successful callbacks return nothing. The buffer commits
atomically only after callback settlement. No public decision constructor,
constant, patch, or result list exists.

### Put routing mutation on the node

V2's `self.trigger` / `self.emit` reads fluently inside a subclass, but it stores
invocation control on a reusable graph definition. That complicates concurrent
runs, callback lifetime, retries, and function-first nodes. Invocation-local
`context.emit` keeps the same imperative clarity without putting mutable
execution state on the occurrence.

### Keep the v2 verb `trigger`

`trigger` suggests that scheduling has started. A v3 control call only appends an
intent to the current callback's private buffer; a later throw, timeout,
cancellation, invalid return, or failed batch preflight discards it. `emit`
describes that staged operation and makes several calls read naturally as
fan-out. The migration receiver changes from reusable `self` to invocation-local
`context` for concurrency correctness; the direct `emit(action, input)` payload
shape remains as concise as v2's `trigger(action, data)`.

### Use `go` or `route` instead of `emit`

`route` can be read as a noun and describes only graph traversal, while one call
may terminate as a declared Flow exit. `go` is terse but suggests immediate
movement and does not naturally describe multiple buffered signals.
`emit` states what happens: the callback emits an ordered control token, and the
runtime routes it after successful settlement. `end` remains distinct because it
is a hard terminal rather than a named-action or unlabelled route.

### Use `connect`, `on`, `next`, or operators instead of `link`

`on` and `next` hide whether the call declares topology, and operator overloads
make search, typing, and error location worse. `connect` is correct but reads as
a larger operation than the graph edge being declared. `node.link(target)` and
`node.link(target, action)` are short, noun/verb unambiguous in context, and map
directly to the inspectable `Link` record. V2's `on(action, target)` put the
condition first because it read as “on this action, use this target.” In v3,
`link` describes topology: the target is the stable first argument and the
optional action only qualifies that edge. Both overloads therefore keep the
target in one predictable position.

### Subclass `Node`

A behavior is ordinarily one function, while a graph occurrence also needs
identity, links, name, retry, timeout, and recovery configuration. A raw function
cannot own those per-placement properties, and a subclass forces inheritance
and `self` onto every one-step behavior. `node(handler, ...)` separates them:
the handler is reusable behavior; the returned `Node` is a lightweight graph
occurrence. Python's `@node` is only sugar for that wrapper.

Specialized higher layers may create their own wrapper factories. Core does not
make subclassing part of the author contract.

### Require explicit control from every handler

Explicitness is valuable at real decisions and terminals, but requiring
`context.emit()` on every linear node adds a control concept where topology
already says exactly one thing. Zero normal-handler emissions mean one unlabelled
route with the current input. Named decisions, fan-out, and hard ends remain
explicit. Zero emissions in recovery and combination deliberately have different
pass-through meanings so an omitted recovery cannot swallow a failure or an
omitted combiner erase outputs.

### Keep `prepare` / `execute` / `complete`

Expanded names would improve v2 spelling but retain three hooks, implicit
cross-hook values, inheritance, and a retry-safety impression the runtime cannot
enforce. Arbitrary state and external effects can occur in any hook. One handler
function plus honest at-least-once retry semantics is easier to read and test.

An application that values phase separation can call ordinary helper functions
from its handler. That policy does not belong in every graph node.

### Add runtime schemas or strict missing-field reads to core

A strict TypeScript state Proxy would turn normal `undefined`, optional chaining,
nullish fallback, and destructuring-default behavior into framework exceptions.
It would still cover only missing top-level state properties, not wrong types,
nested fields, branch input, or terminal output, so the apparent Python parity
would provide false confidence. Python itself preserves both strict indexing and
defaulting `.get(...)`; core should not override either host language.

A `validate=` node option, schema hook, or restored preparation lifecycle would
duplicate an ordinary parser while implying graph-wide safety that dynamic
emissions and payload-untyped links cannot prove. Applications parse before
effects or use an explicit validation node before retried work. Higher layers may
standardize schema-bearing nodes and action contracts without adding that policy
to the runtime kernel.

### Branch-owned or copied state

A state map per branch makes parallel writes isolated, but fan-out produces
several equally legitimate final states. A supposedly simple `run()` must then
choose a terminal, require a reducer, return many values, or expose different
return types by cardinality. It also introduces copy/overlay/merge semantics into
every transition.

Caskada instead owns one shared state for the invocation and puts branch-specific
data in `context.input` and terminal `output`. Fan-out never makes another state.
This yields one direct final state for linear and fan-out runs. The cost is
explicit and honest: parallel conflicting state writes are application races.
Use terminal outputs plus a Flow combiner when isolation and deterministic
aggregation matter.

### Pure value passing

A pure `Node(input) -> output` runner makes branch data elegant but leaves
workflow-wide configuration, accumulated results, services, and progress without
a simple persistent home. Covering common workflows then requires tuples,
closures, environment objects, reducers, or another state abstraction.
Caskada's three roles are smaller in aggregate: shared `state` persists, `input`
moves with one token, and `output` closes one token.

A pure dataflow adapter can sit above core and restrict itself to input/output.

### Omit terminal output and use only state

Without terminal output, parallel workers must coordinate writes into shared
state or invent branch-local state merely to hand values to a combiner. An
optional output is not a second persistent store: it is the branch message at
the Flow boundary. Omission produces no output, while explicit nullish output is
preserved. `run()` still returns state; advanced `start()` exposes outputs.

### Deep-copy state or branch values

Deep copying would reject or corrupt common in-process objects, obscure cost, and
still not define ownership for external services. Caskada shallow-copies the
initial top-level state exactly once and borrows nested state, input, and output
references. Authors explicitly copy values when their domain requires it.

### Transactions or deterministic parallel commits

Correct optimistic transactions require read/write sets, versions, tombstones,
snapshot epochs, conflicts, deterministic publication, and retry policy for
opaque references. That is a database protocol. Caskada instead defaults to
serial scheduling and documents parallel shared writes as timing-dependent.
Disjoint writes, synchronization services, or output-and-combine provide explicit
solutions without putting a database in the core.

### A first-class `Group`, `Join`, or batch class

Several `emit` calls already create fan-out. A nested `Flow` already owns the
structured wait, cancellation boundary, concurrency limit, failure scope, and
one combine callback. Another scheduling primitive would duplicate those
semantics and increase the everyday grammar.

### Dynamic topology or dynamic Flow calls

Runtime-selected graph definitions defeat complete topology inspection and add
call-stack, permission, budget, and recursion policy. A catalogue can compile
known candidates, dispatch through an ordinary node, or own a higher-level
runner. Dynamic calls can be reconsidered after an independent general-purpose
use case and a bounded contract exist.

### Asynchronous event streams in core

A stream requires capacity, overflow, terminal delivery, detachment, consumer
failure, and reentrancy policy. One synchronous nonfatal observer is sufficient
to build competing adapters without forcing one policy into the graph runner.

## Explicit non-goals

Caskada v3 core does not provide:

- LLMs, semantic routing, route metadata, or agent drivers;
- workflow registries, manifests, plugins, YAML, JSON Schema, or expression
  languages;
- persistence, checkpoints, replay, durable timers, or crash recovery;
- transactions, rollback, exactly-once effects, or value ownership enforcement;
- a distributed scheduler, worker protocol, or process sandbox;
- dynamic topology, runtime graph construction, or detached branches;
- deep state copying, serialization, or a portable state codec;
- built-in telemetry exporters or a retained execution tree.

These are valid layers above a graph runtime. Keeping them out is what lets
Caskada stay small enough to understand completely.

## Migration from v2

V3 has no compatibility aliases. Migration is an explicit source rewrite because
the state, retry, and execution-ownership contracts have changed.

The conceptual translation is small:

| V2 behavior or code                                                                                 | V3 migration                                                                                                                                                 |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| subclass `Node`                                                                                     | Write one handler function and wrap it with `node(handler, ...)`; Python may use `@node`.                                                                    |
| `prep`, `exec`, and `post`                                                                          | Put the visible sequence in one handler; when the old retry boundary matters, use separate prepare, retrying-work, and commit nodes.                         |
| `self.trigger(action, data)`                                                                        | `context.emit(action, data)`.                                                                                                                                |
| `trigger(DEFAULT_ACTION)` or sentinel `trigger("default")`                                          | Emit nothing or call `context.emit()` and use an unlabelled link. A domain action genuinely named `"default"` remains a named action and needs a named link. |
| several `trigger()` calls                                                                           | Make several `context.emit(...)` calls; order is preserved and commit is atomic.                                                                             |
| no trigger with a default successor                                                                 | Emit nothing; successful zero-emission handlers take the unlabelled link and forward current input.                                                          |
| no trigger at a terminal leaf                                                                       | Usually emit nothing: the implicit unlabelled route exits the current Flow. Use `context.end()` only for an intentional hard terminal.                       |
| `trigger(None)`                                                                                     | Use `context.end()` when it meant hard termination; use no emission or `context.emit()` when it meant the unlabelled route.                                  |
| `exec_fallback`                                                                                     | Supply `recover=callback` to `node`; emit to handle, or emit nothing to propagate the exact Failure.                                                         |
| `a.on("yes", b)`                                                                                    | `a.link(b, "yes")`.                                                                                                                                          |
| `a.next(b)` or `a >> b`                                                                             | `a.link(b)`.                                                                                                                                                 |
| unmatched named action intentionally propagated from a Flow                                         | Declare that name in the owning `Flow(exits=(...))` / `new Flow(..., { exits: [...] })`, then emit it. An undeclared missing link is now `unknown_action`.   |
| multiple physical targets for one action                                                            | Give targets distinct actions, or emit the same action more than once with different inputs.                                                                 |
| global `memory`                                                                                     | `context.state`, the one run-owned map shared by all activations.                                                                                            |
| branch-local `memory` / `forking_data`                                                              | `context.input` in the receiving branch.                                                                                                                     |
| terminal branch-local data                                                                          | `context.end(value)` and `result.outputs` in a Flow combiner; inspect `terminals` only for control metadata.                                                 |
| caller-borrowed global Memory                                                                       | `initial_state` is shallow-copied once; `await flow.run(initial_state)` returns the run-owned final state directly.                                          |
| deep-cloned local overlays                                                                          | No automatic clone; explicitly copy the value passed as `input` when the domain needs isolation.                                                             |
| `Node(max_retries=N, wait=S)`                                                                       | `node(..., retry=RetryPolicy(max_attempts=N, delay_ms=milliseconds))`; use a delay callback only when the wait varies by failure/attempt.                    |
| `ParallelFlow(start)`                                                                               | `Flow(start, concurrency=N)`; the omitted run ceiling derives from compiled Flow caps, while an explicit run option can throttle or permit aggregate scopes. |
| custom `Flow.prep`                                                                                  | Add an explicit entry node or call a helper before entering the Flow.                                                                                        |
| custom `Flow.post`                                                                                  | Use `combine`; emit the replacement boundary outcome, or emit nothing to preserve the exact child outcomes.                                                  |
| custom `Flow.run_tasks`                                                                             | Redesign against `Flow(concurrency=...)` or an extension scheduler; there is no mechanical core rewrite.                                                     |
| `Flow(start, {"max_visits": N})` / `new Flow(start, { maxVisits: N })`, including v2's default `15` | Choose an explicit aggregate `Flow(..., max_activations=N)` component budget and/or run-wide limits. There is no hidden default or exact per-node rewrite.   |
| `Flow.start` as the entry field                                                                     | `Flow.entry`; execution uses `start(initial_state)` for advanced results.                                                                                    |
| `node.run(memory)`                                                                                  | `Flow(node).run(initial_state)`; a Node occurrence is not a second runner.                                                                                   |
| TypeScript `createMemory`, `Memory`, `SharedStore`                                                  | Remove them; pass a typed plain state object to `Flow.run()`.                                                                                                |
| `node.clone()`                                                                                      | Remove it; compilation snapshots topology and each run owns framework state.                                                                                 |
| `ExecutionTree`                                                                                     | Attach an observer or use an event-built extension.                                                                                                          |
| direct `successors` access                                                                          | Use `links()` or `CompiledFlow.describe()`.                                                                                                                  |

Most v2 leaves need neither `end()` nor a custom combiner. A zero-emission
handler follows the unlabelled edge; without a matching edge it exits the current
Flow, which completes a root Flow and can continue through a nested Flow's parent.
Use `end()` only to bypass those enclosing links deliberately or to publish a
terminal output. Default Flow boundary behavior forwards terminals unchanged;
write a custom `combine` callback only to aggregate branch outputs into shared
state or replace the boundary's outward control.

The distinction is visible in the cookbook experiments: a map worker uses
`end(row)` because the map Flow's combiner needs a new `Row` output, while an
accepted leaf inside a nested supervisor flow emits nothing so its ordinary
unlabelled Flow exit can resume the parent's linked supervisor node. `end()` is a
branch-level hard boundary, not routine leaf punctuation.

One action now identifies one route. V2's repeated physical targets made a
topology edit silently change one decision into broadcast, gave every target the
same branch data, and obscured cardinality and order. V3 keeps topology a switch;
several ordered `emit()` calls make fan-out and each branch input explicit.

V2 also overloaded the literal string `"default"` as its unlabelled-routing
sentinel. V3's unlabelled route is private and every string, including
`"default"`, is an ordinary named action. Migration must therefore inspect the
source topology: rewrite sentinel use to zero emissions or `emit()`, while
preserving a genuine domain path named `"default"` with a named link. Likewise,
v2 propagated an unmatched named action out of a Flow automatically; v3 requires
that intended boundary explicitly in the Flow's `exits`, while an accidental
missing link fails as `unknown_action`.

V2 Flow subclasses need an architectural rewrite, not a method rename. Entry
preparation becomes an explicit entry node, and post-Flow aggregation or routing
becomes `combine`. A zero-emission combiner preserves the exact child outcomes;
emitting from it replaces those outcomes, so an additive v2 `Flow.post` must
reproduce every child outcome it intends to retain. A custom `run_tasks`
scheduler must be reconsidered against Flow concurrency or an extension. Cyclic
work also needs explicit v3 run-wide limits because the v2 per-node visit cap has
no exact topology-local counterpart.

The practical global-memory pattern remains: every node may mutate
`context.state`, later nodes observe the same top-level map, and `run()` returns
that map with surviving writes. The differences are that the caller's top-level
`initial_state` is shallow-copied once and branch-local handoff no longer hides inside a
global/local Memory proxy; it is the explicit `context.input` channel.

V2's `max_retries` already counts total attempts despite its name, so it maps
directly to `max_attempts`. Delay conversion from seconds to integer milliseconds
still requires an explicit rounding policy when multiplication is not exact.

### Python comparison

```python
# v2
from caskada import Node


class Model:
    async def answer(self, question: str) -> str:
        return question.upper()


model = Model()


class Answer(Node):
    async def prep(self, memory):
        return memory.question

    async def exec(self, question):
        return await model.answer(question)

    async def post(self, memory, question, answer):
        memory.answer = answer
        self.trigger("review", {"question": question})


class Review(Node):
    async def prep(self, memory):
        return memory.question

    async def exec(self, question):
        assert question


answer = Answer()
answer.on("review", Review())
```

```python
# v3
from typing import NotRequired, TypedDict

from caskada import Context, node


class Model:
    async def answer(self, question: str) -> str:
        return question.upper()


model = Model()


class AnswerState(TypedDict):
    question: str
    answer: NotRequired[str]


class ReviewInput(TypedDict):
    question: str


@node
async def answer(context: Context[AnswerState]) -> None:
    question = context.state["question"]
    context.state["answer"] = await model.answer(question)
    context.emit("review", {"question": question})


@node
def review(context: Context[AnswerState, ReviewInput]) -> None:
    assert context.input["question"] == context.state["question"]
    # No control call exits the root Flow.


answer.link(review, "review")
```

The v3 handler has one control surface and no inherited lifecycle. The explicit
input preserves v2's branch-local handoff. When the successor already reads the
shared question from state, omit that argument and call
`context.emit("review")`.

Final state retrieval also becomes direct:

```python
from caskada import Flow


async def run_answer() -> None:
    initial_state: AnswerState = {"question": "Why?"}
    state = await Flow(answer).run(initial_state)
    assert state is not initial_state
    assert state.get("answer")
```

The identity assertion specifies only the top-level copy; nested values remain
borrowed references.

### TypeScript comparison

```typescript
// v2
import { Memory, Node, SharedStore } from 'caskada'

interface AnswerState extends SharedStore {
  question: string
  answer?: string
}

declare const model: {
  answer(question: string): Promise<string>
}

class Answer extends Node<AnswerState, string, string, ['review']> {
  override async prep(memory: Memory<AnswerState>) {
    return memory.question
  }

  override async exec(question: string) {
    return model.answer(question)
  }

  override async post(memory: Memory<AnswerState>, question: string, answer: string) {
    memory.answer = answer
    this.trigger('review', { question })
  }
}

class Review extends Node<AnswerState, string, void> {
  override async prep(memory: Memory<AnswerState>) {
    return memory.question
  }

  override async exec(question: string) {
    if (!question) throw new Error('missing question')
  }
}

const answer = new Answer()
answer.on('review', new Review())
```

```typescript
import { node } from 'caskada'

import type { Context } from 'caskada'

// v3

interface AnswerState {
  question: string
  answer?: string
}

interface ReviewInput {
  question: string
}

declare const model: {
  answer(question: string): Promise<string>
}

const answer = node<AnswerState>(
  async (context: Context<AnswerState>) => {
    const { question } = context.state
    context.state.answer = await model.answer(question)
    context.emit('review', { question })
  },
  { name: 'answer' },
)

const review = node<AnswerState, ReviewInput>(
  (context) => {
    if (context.input.question !== context.state.question) throw new Error('mismatch')
    // No control call exits the root Flow.
  },
  { name: 'review' },
)

answer.link(review, 'review')
```

The `ReviewInput` parameter improves local callback reads only. The returned
occurrences are both `Node<AnswerState>`; `link()` checks their state type but
does not claim that the `'review'` emission carries `ReviewInput`.

When v2 `prep` served as application validation, put the parser at the start of
the consuming v3 handler before any state write or external effect. If the work
node retries but parsing must stay outside that at-least-once boundary, make
validation an ordinary predecessor node and emit the parsed value as its input.
Neither spelling adds a runtime schema claim to the link.

The v3 retry boundary is the whole handler. Direct state mutations, nested
mutations, and external effects from a failed attempt remain visible to a retry
and recovery. The migration guide and any codemod diagnostics must surface that
at-least-once boundary before enabling retries. `should_retry(Failure)` is the one
portable selector; core adds no duplicate exception-class option because
JavaScript can throw arbitrary values and cross-realm constructor tests are not
portable. When v2 preparation or post-processing is non-repeatable, split it into
ordinary prepare, retrying-work, and commit node occurrences and pass their local
values through `context.input`.

The migration guide must distinguish v2's caller-borrowed global store and
deep-cloned local overlays from v3's run-owned shared map and explicit token
inputs. Application code must choose the intended ownership at that boundary.

## Implementation plan

Each phase ends with cross-language fixtures, complexity instrumentation, and a
surface review. Later phases may not revise earlier author semantics silently.

### Phase 0: executable contract fixtures

Create one language-neutral JSON fixture format and an initial serial corpus for
compiled topology, emissions, terminal order, shared-state observations, inputs,
outputs, basic failures, event order, stats, and simple-run errors. Fixture
application values remain JSON-compatible even though runtime values are not
restricted to JSON. Cross-language fixtures also preserve each host's
missing-field behavior and agree only once application code turns absence into
an explicit error. Before each later implementation phase begins, extend this
same corpus with that phase's exact packets, timers, cancellation, observer, and
resource-bound snapshots.

Build tiny Python and TypeScript reference interpreters for the serial subset:
function-backed node occurrences, one shared state, buffered emit/end calls,
implicit unlabelled continuation, token input, terminal output, declared exits,
nested Flow forwarding, combination, `run()` projection, and `start()` results.
Resolve every cross-port ambiguity in fixtures before implementing concurrency.

### Phase 1: definition compiler

Implement `GraphElement`, function-backed `Node` occurrences, `node()` / Python
`@node`, `Flow`, target-first `link()`, `links()`, immutable placement compilation,
containment-cycle rejection, and `describe()`. Add topology parity tests,
occurrence-reuse tests, automatic-concurrency derivation, and a
100,000-placement nonrecursive compile test. Capture every Flow's optional
direct-activation cap in its compiled scope description.

### Phase 2: serial execution kernel

Implement the run-owned top-level state copy, Context epochs, input/output
presence capture, private emission buffers, all zero-emission rules, atomic
buffer settlement, scalar and fan-out token creation, Flow scopes, exact terminal
forwarding, the single ordered output projection, combine behavior,
completed/failed results, simple `run()` projection, and one typed `RunError` at
concurrency one. There are no state patches,
branch maps, public decision records, or v2 Memory objects in this path.

### Phase 3: retry and recovery

Implement retry admission and timers, packet-owned Node/Flow recovery, universal
failure replacement, scope fences, the active-packet registry, deterministic
run-fence drain, persistent suppression order, and unrecoverable classifications.
Recovery receives the controlling token input and the shared state; it never
receives an invented branch state.

### Phase 4: structured concurrency

Implement per-scope queues, the ready-scope ring, run-wide callback permits,
parallel settlement, live-token accounting, cancellation hierarchy, callback
timeouts, run deadline, grace timers, packet drain, topology-auto and explicit
run callback ceilings, per-scope direct-activation counters and atomic
preflights, and abandonment. Add
controlled fixtures for shared-state visibility and document that conflicting
parallel writes are application-coordinated rather than scheduler-merged.

### Phase 5: observation and adapters

Implement the synchronous observer, contiguous publication bundles, and
`Context.report()`. Build non-core reference adapters for logging, event streams,
and execution-tree reconstruction. Adapter buffering, persistence, and delivery
policy must not enter core conformance.

### Phase 6: migration and removal

Publish the v2-to-v3 migration guide. Remove
`BaseNode`, subclass authoring, `ParallelFlow`, `Memory`, triggers, public clone
behavior, operators, visit counts, public decision/patch objects, and mandatory
execution trees from v3 core. Run a stale-term scan across code, types, tests,
examples, and generated documentation. Keep the cookbook v3 ports executable
against the shipped runtime and aligned with their documented lessons.

### Implementation budget

No speculative line limit overrides correctness. The dual-language spike must
publish non-comment executable line counts and justify every public abstraction.
An implementation more than three times the current core size, or one that adds
author-facing concepts beyond this RFC, requires another architecture review
before API freeze. Both cores remain in one primary source module until splitting
demonstrably reduces understanding cost rather than distributing it.

### Static validation toolchain

The normative Python block imports/compiles as a `.py` module under CPython 3.13.
Its annotation-equivalent `.pyi` projection replaces only executable private
constructor guards/helper bodies and token initializers with declaration forms;
that projection plus published v3 examples is checked with mypy 1.17.1 using
`--strict --python-version 3.13` and Pyright 1.1.413 using a fixture configuration
with `typeCheckingMode: "strict"` and `pythonVersion: "3.13"`.
The normative TypeScript block is checked as a `.d.ts`; published complete
TypeScript examples and declarations use TypeScript 5.9.3 with
`--strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess`.
Isolated snippets are embedded in typed fixture scaffolds before checking; v2
comparison blocks use their separately pinned v2 surfaces and do not weaken the
v3 checker mode. Changing a checker version is a conformance change and must
publish the resulting fixture diff.

## Conformance matrix

Python and TypeScript must run equivalent fixtures for:

### Graph and compile

- direct `GraphElement`/`Node` construction and Node subclassing fail; unknown
  GraphElement/Flow subclasses are rejected before partial compilation in both
  typed and dynamic call paths;
- `Context`, `Cancellation`, and `RunHandle` are runtime-issued interfaces with
  no public constructor; direct `CompiledFlow` construction/subclassing fails and
  `Flow.compile()` is its only issuer;
- target-first default and named links, duplicate rejection, and insertion order;
  Python accepts the named action positionally or by keyword, omission alone
  selects the unlabelled edge, explicit `None` / `null` / `undefined` actions
  fail, and the reversed v2-style argument order is rejected;
- exact primitive Python/TypeScript actions, names, exits, report names, run IDs,
  numeric options, and dynamic retry delays; Python `str`/`int` subclasses,
  bare string/bytes exits, and TypeScript nonprimitive values are rejected before
  they can participate in lookup or comparison; every accepted JavaScript `-0`
  option or dynamic delay is normalized to observable `+0`;
- scope-specific placements for one definition reused in several scopes;
- the same child flow placed more than once;
- exact `CompiledDescription` shape, IDs, ordering, kind-specific fields,
  definition-only `auto_max_concurrency`, nullable scope-local activation caps,
  and mutation isolation;
- breadth-first compile IDs prove that a nested Flow allocates its child
  scope-definition ID when discovered but assigns the child entry placement ID
  only when that child scope is dequeued;
- ordinary cycles and rejected containment recursion;
- compile-time portable collection/ID bounds for placements, scopes,
  links, exits, and description arrays, rejected without a partial
  `CompiledFlow`;
- definition mutation after compile and concurrent compiled reuse;
- root outgoing links ignored when run directly;
- strict TypeScript and mypy/pyright rejection of mismatched state types across
  links and Flow entries; local `Context<State, Input>` and handler inference
  accept typed input reads while the returned Node remains state-typed and links
  make no payload-compatibility claim;
- strict TypeScript and mypy/pyright require narrowing from the dynamic
  `unknown` / `object` input and output surfaces, while an explicit local input
  type enables callback reads without changing topology;
- initial state required by both ports, with strict TypeScript rejection of
  `run()` / `start()` calls that omit it and equivalent mypy/pyright fixtures;
  `{}` is used explicitly for empty state;
- Python `TypedDict` reads/writes and terminal/result propagation, plus the
  unparameterized `dict[str, Any]` default, checked in both mypy and Pyright;
  the persistent carrier supports the normal dict instance surface, while an
  arbitrary custom Mapping/class type is rejected as an unsupported StateT;
- option, compile, and state-copy preflight precedence, with no handle or event
  created by any rejected start;
- Python `start()` outside a running `asyncio` loop raises the exact native
  `RuntimeError` before options, definition, or state are read; `run()` and
  in-loop `start()` share all remaining preflight behavior;
- Python exact `RunOptions`/`RetryPolicy` instances and TypeScript plain option
  records: unknown/symbol/non-enumerable keys, throwing getters/proxies,
  noncallable callbacks, null/empty/wrong `runId`, invalid definition options,
  declared-order capture, explicit-undefined omission, and immunity to later
  source-record mutation produce their exact pre-start exception/cause;
- omitted Python `max_concurrency=None` and TypeScript `maxConcurrency` select
  the compiled automatic value; explicit smaller and larger positive values
  respectively throttle callbacks and permit aggregate scope concurrency without
  weakening any local Flow cap;
- omitted Flow `max_activations` / `maxActivations` creates no local budget;
  zero/noninteger values fail definition capture, and each nested/repeated runtime
  scope receives an independent counter from the compiled positive cap;
- option combinations whose conservative event/collection capacity exceeds
  `MAX_PORTABLE_COLLECTION_LENGTH` are rejected before a handle or callback,
  even when every individual number is a safe integer;
- malformed or throwing initial-state capture wrapped as `OptionValidationError`
  with its native cause preserved;
- Python initial mappings reject a non-`str` key before reading its value;
  TypeScript rejects the corresponding symbol/non-data property cases, and both
  ports begin every accepted run with only ordinary string bindings;
- TypeScript initial-state proxies observe exactly one prototype read, one
  own-key snapshot, and one descriptor read per visited key in ECMAScript key
  order; accessor getters are never invoked, and a trap failure prevents every
  later descriptor/value access;
- fake Python mappings whose gross length exceeds the portable bound or whose
  key iterator lies past it are rejected before value reads/handle creation;
- a 100,000-node chain without recursion using an explicit 100,001 activation
  budget;
- browser execution with no Node.js built-ins.

### Outcomes and state

- `node(handler)` and Python `@node` create distinct graph occurrences with the
  supplied handler, name, retry, timeout, and recovery configuration; wrapping
  one undecorated handler twice produces independent occurrences and links,
  while one decoration produces exactly one occurrence rather than a reusable
  occurrence factory;
- synchronous and asynchronous handlers both accept one live `Context` and may
  settle only with `None` / `undefined`;
- zero normal-handler emissions synthesize one unlabelled route forwarding the
  current input; one emission is scalar; two or more are atomic fan-out in call
  order; every committed synthetic default increments `transitions` and consumes
  one `max_transitions` unit exactly like an explicit emission;
- named/unlabelled `emit`, `end`, and mixed emit/end buffers commit exactly in
  call order, with no reserved action string and null used only to inspect an
  unlabelled link;
- route resolution proves Node-link-before-owning-exit, nested-Flow-link-before-
  parent-exit, root-callback-exit-only, implicit unlabelled exit, declared named
  exit, unknown-action rejection, and End bypass in both ports;
- `emit` / `end` return `None` / `void`, do not stop the callback, and schedule no
  work before successful settlement; each `end` hard-ends only its emitted branch
  and neither cancels buffered siblings nor ends the run; an early return after
  `context.emit(...)` remains host-language control rather than a return-value
  protocol;
- throw, timeout, cancellation, non-null return, or failed preflight discards the
  complete emission buffer while preserving direct shared-state mutations and
  external effects already performed;
- state, input, emitted input, and output values remain opaque application data;
  Python missing-key indexing retains its exact `KeyError` as an ordinary phase
  Failure while `.get(...)` retains its defaulting behavior, JavaScript missing
  property reads remain `undefined`, and neither port creates a schema-specific
  Failure or claims local input types prove link compatibility;
- parse-before-effects and explicit validation-node-before-retried-work fixtures
  prove that application validation composes from ordinary handlers without a
  core schema hook;
- caught rejected emit/end calls append nothing and retain earlier valid intents;
- a caught first hard-cap overflow from emit/end still commits the exact
  unrecoverable limit failure and run fence; earlier emission intents cannot
  commit, prior direct state writes remain, and later caught Context calls
  allocate nothing;
- stale/different Context use and every later Context property/control/report
  access after settlement or abandonment fail without changing the run; a state
  alias obtained from a live Context remains the persistent carrier and is not
  epoch-revoked;
- action validation and TypeScript unlabelled-input-wrapper capture follow the
  specified prototype/own-key/descriptor/proxy order; accessors are rejected
  without invoking their getter, invalid shape does not inspect later fields, and
  exact trap causes retain the callback phase's failure classification;
- omitted emit input forwards `context.input`, while explicit `None` / `null` /
  `undefined` is retained as a real next input; omission versus presence is
  tested at runtime and under
  `tsc --strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess`;
- omitted end output sets the false presence discriminator and contributes no
  `ScopeResult.outputs` item, while explicit nullish output sets it true and is
  retained; input and present output values are borrowed references and are not
  cloned, serialized, or inspected;
- emitting the persistent Context state carrier as input/output is valid and
  retains that exact application reference; `state.copy()`,
  `dict(context.state)`, or object spread creates a separate shallow snapshot;
- root `context.input` is `None` / `undefined`; scalar routing, fan-out, nested
  Flow entry, retry, Node recovery, Flow recovery, and exit resumption receive
  the exact input reference specified by this RFC;
- every callback in one invocation observes the exact same run-owned top-level
  state map; fan-out allocates tokens and input references but performs no state
  copy, overlay, patch, merge, or hidden local-memory operation;
- caller top-level state is copied exactly once before handle creation;
  malformed or throwing sources fail pre-start, nested and self references retain
  ordinary shallow-copy alias behavior, and the caller's top-level map is not
  mutated;
- linked offline/online phases under one root observe one state identity and one
  invocation, while intentionally passing a returned state as a later
  `initial_state` creates a separate shallow copy, run ID, budgets, and event
  lifecycle; no borrow-mode path exists;
- Python state is a normal `dict`; TypeScript state is a normal object. Their
  reads and mutations follow host-language behavior after the shallow copy;
- retained state aliases, Python iterators/views, and TypeScript references stay
  usable after callback settlement; retained Context capabilities fail. An
  alias may mutate the same top-level map even after a final result, while
  snapshots and nested values follow ordinary shallow host-language aliasing;
- there is no `state_bindings` budget, state-write Failure, or state-write event;
  the initial portable collection bound constrains capture, and later state
  width is application memory outside framework allocation accounting;
- failed attempts expose prior state writes to retry and recovery;
- controlled serial fixtures prove immediate shared-state visibility; controlled
  parallel fixtures prove no scheduler merge or last-writer promise and use
  disjoint writes, synchronization, or outputs plus combine for deterministic
  behavior;
- each emission append and complete settlement batch is bounded by
  `max_transitions`, collection capacity, ready/activation capacity, safe IDs,
  and a final timer/fence checkpoint; rejection commits no transition or
  terminal and never partially publishes a batch;
- batches with several invalid/unknown arms choose the first arm in buffer or
  terminal order; simultaneous batch limits choose `max_transitions`, portable
  collection, run-wide activations, receiving-scope activations, ready, then safe
  integer, with the exact Failure detail and no partial reservation;
  nested-scope admission separately chooses depth, run-wide activations, ready,
  then safe integer when its queued Flow head runs;
- a timer crossing after batch linearization cannot undo committed control; no
  state rollback is attempted;
- terminal-only fan-out and exact forwarding consume `max_transitions`;
- every `RunResult` variant contains the exact same persistent shared carrier;
  completion ends scheduler access rather than granting exclusive ownership,
  failed/cancelled state is partial, and an escaped top-level or nested reference
  may still be changed by uncooperative work after abandonment;
- TypeScript `run()` uses the specified final native-Promise capability and
  synchronous `then: undefined` mask; own callable/noncallable/absent `then`,
  polluted `Object.prototype.then`, exact descriptor
  restoration, multiple waiters, and exact fulfillment identity are covered,
  while a negative fixture proves that an async or intermediate chained return
  would assimilate application state;
- `Completed.terminals` is nonempty; every non-completed result retains exactly
  the possibly-empty ordered root terminals committed before its controlling
  fence, without a post-fence combine or synthetic terminal;
- `run()` and `start()` execute the graph once: every `Completed` projects to the
  exact shared state at any terminal cardinality or kind; failed, cancelled, and
  abandoned execution raises one `RunError` retaining the exact full
  `RunResult` without rerunning;
- `RunError(result)` requires a non-completed result, preserves its identity,
  and has the exact language-normalized class name and cross-port message selected
  by status; no application cause is formatted; a controlling Failure's exact
  non-null native cause is exposed through Python `__cause__` or TypeScript
  `Error.cause` without traversing `Failure.previous`;
- cancelling a Python task inside either `Flow.run()` or `CompiledFlow.run()`
  cancels the underlying handle with `"caller_cancelled"` and re-raises native
  `asyncio.CancelledError`;
- repeated `RunHandle.result` reads and every `RunError` preserve required
  result, state, Failure, terminal, and diagnostic object identities.

### Flow completion

- the optional combine callback is invoked exactly once for each successful root
  and nested scope, including a root Flow run directly;
- combine `context.state` is the one shared map and combine `context.input` is the
  Flow activation's incoming input;
- absent combine or zero combine emissions forwards the exact immutable terminal
  set; one or more combine emissions atomically replace the set;
- exact forwarding preserves terminal kind, action, output presence/reference,
  order, and cardinality while allocating new receiving IDs at a boundary;
- custom combination can validate and aggregate the one ordered
  `ScopeResult.outputs` projection into shared state without emitting; the
  original terminals still reach the root and `run()` returns that one state;
- the map/collect example executes zero, one, and many inputs in both ports; its
  zero-input dispatcher explicitly calls no-output `end()`, while one/many paths
  validate and aggregate worker outputs, and the final result count always
  matches the input count;
- end forwarding remains end; exit forwarding resolves the nested Flow
  occurrence's parent link or declared parent exit and supplies terminal output
  as successor input;
- root outgoing links are ignored; root combine emissions resolve only within
  the root's declared topology/exits;
- root completion always contains one shared state and one or more terminals;
  any mix of End and Exit terminals is valid, and simple `run()` deliberately
  projects every such completion to that shared state;
- `ScopeResult`, `Terminal`, and `ScopeFailure` are immutable records whose
  application output references remain borrowed; `ScopeResult.outputs` contains
  exactly one reference per output-bearing terminal in relative terminal order,
  including explicit nullish outputs but excluding no-output Ends, and there are
  no end/exit-specific convenience projections; Python identity/repr and
  TypeScript reference behavior match without rendering arbitrary outputs or
  suppression chains;
- TypeScript strict fixtures reject direct property access on an output before
  application narrowing, while a validator returning `Row` enables typed use;
  mypy and Pyright accept the corresponding Python validator path over dynamic
  `object` values;
- negative compile fixtures reject `ScopeResult<Row>` and narrower typed combine
  callbacks, while positive fixtures prove that `node(handler)` still captures a
  local input assertion and erases it to state-only topology;
- zero Node-recovery emissions propagate the exact Failure packet; zero
  Flow-recovery emissions propagate the exact ScopeFailure packet; a recovery
  handles only by committing one or more emissions;
- Node recovery receives the failed activation's input and Flow recovery receives
  the active packet's controlling input, both with the shared state;
- a failed child's successful recovery reaches its parent once; exact
  pass-through cannot consume, duplicate, or reorder terminals or packets;
- terminal settlement order is deterministic under serial deterministic work and
  timing order under explicit parallelism; semantic order is represented in
  output data;
- zero-terminal quiescence is invalid, and every live token always has exactly
  one ready, running, waiting-Flow, retry-timer, or settled owner.

### Retry, failure, and cancellation

- run-wide attempt capacity is reserved immediately before `callback_started`:
  concurrent initial nodes deterministically contend for the final slot, while a
  delayed retry may already have emitted `retry_scheduled` before readmission
  fails; the limit has full scope/activation/element IDs, null attempt, exact
  fresh/replacement packet semantics, and no attempt/callback/peak increment;
- exhausted node-local retry policy calls neither the predicate nor a configured
  delay callback; an already empty run-wide attempt budget after an affirmative
  predicate evaluates no delay and publishes no retry, while a concurrently
  consumed last slot can still reject a previously scheduled retry at
  readmission;
- constant and callback retry delays, retry counts, retained state effects, and
  policy failure; invalid constants fail definition capture while invalid
  callback results fail at retry time;
- forbidden asynchronous policy results receive the specified best-effort
  native cleanup without awaiting, cancellation, or workflow admission; native
  coroutine/Future/Task/Promise cases consume the applicable host warning or
  rejection, a native Promise fulfilled with a callable-`then` value proves that
  both no-op handlers leave no assimilating child, and custom awaitable/thenable
  cases exercise the explicitly bounded fallback and preserve the one selected
  `retry_policy` Failure;
- retry timer origin is the atomic schedule commit: slow
  `retry_scheduled` observation consumes delay and a zero-delay retry becomes
  ready only at the first post-bundle checkpoint;
- `should_retry` and callback `delay_ms` returning/throwing immediately before,
  at, and after the run deadline, including skipped next-stage policy, no late
  retry commit, and causal post-fence suppression;
- a policy that reentrantly cancels then throws immediately before, exactly at,
  and after grace: only the strict-before case records suppression, while
  equality/later abandon without a late Failure/event;
- one-based `attempt` only for handle callbacks and handle-origin failures,
  including retry policy, handler preflight, and post-signal errors; null for
  every recovery/combine phase and boundary/unowned failure, with paired
  report-overflow-in-handle and report-overflow-in-Flow-combine fixtures;
- exact producer IDs for nested combine/recovery unknown-action and limit
  preflight, handler admission exhaustion, nested-Flow entry allocation, an
  owned scheduler failure, and a genuinely unowned invariant; fence target and
  packet movement never rewrite those IDs;
- failed-attempt direct mutation visible to retry and Node recovery;
- node recovery success/failure and no recovery for invalid outcomes;
- recovery packet consumed only after its replacement emission batch commits;
- every packet ownership transition, with terminal `Merged`, `Consumed`, and
  `Drained` packets absent from the active registry;
- Flow recovery receives the active packet's controlling input before/after
  fan-out, including the Flow activation input for a fresh combine failure, and
  observes the same shared state as every other callback;
- concurrent failures with distinct inputs prove that the first scope-primary
  packet keeps its input, sibling merge discards the arriving input, boundary
  pass-through preserves it, and only universal replacement may adopt a newer
  producing callback input;
- smallest-scope recovery and failed child recovery reaching its parent once;
- full event snapshots for exact-pass-through and throwing nested Flow recovery:
  callback settlement, child `scope_finished(failed)`, optional parent scope
  fence pair, and eventual root run-fence/terminal order across a multi-level
  unhandled chain;
- `ScopeFailure` primary, suppressed, pre-fence terminals, and combiner result;
- every Failure/detail kind pair is valid and required-nullable: attempted named
  actions survive `unknown_action`, every runtime budget identifies its exact
  `LimitName`, every invalid-outcome/combination rule has its exact reason, and
  handler/lifecycle failures carry null; result and `failure_recorded` expose the
  same Failure object with matching Python/TypeScript schema;
- `ScopeFailure.failing_activation_id` is null for the Flow's own combiner
  failure and remains the original direct child activation across recovery
  replacement;
- transitive suppressed packets through unhandled and throwing Flow recovery;
- deep nesting times wide sibling failure instrumentation proves O(1) packet
  append/merge, no intermediate suppression flatten, guarded scoped iteration,
  and one ordered final flatten;
- replacement in every phase preserves `previous` and inherited suppression;
- a 10,000-replacement Python chain compares identity rather than fields and has
  bounded nonrecursive `repr`; result/failure/terminal reprs never walk outputs,
  terminals, state, causes, reasons, or suppression, matching reference identity
  in TypeScript;
- handler, policy, mapping/proxy, recovery, and observer causes whose Python
  `__str__` or JavaScript `message`/prototype/`toString` access throws are never
  coerced: canonical messages, exact cause identity/null rules, packet commits,
  and observer diagnostics still complete once;
- observer cancellation from a retry-policy replacement's
  `failure_recorded` event cannot overtake its already-committed failed fence;
- post-signal exceptions append after registry/final-suppression commit without
  replacing timeout primary or creating another active packet;
- when a failing scope packet signals a sibling that already owns its own active
  packet, a post-signal error appends only to the sibling packet and merges in
  `[sibling primary, inherited suppression..., new error]` order; the same error
  from a healthy controlled sibling appends to the scope packet, with exact
  `previous` IDs and no unrelated-packet selection;
- simultaneous active packets drain deterministically and without duplication on
  failure, cancellation, deadline, and grace abandonment;
- a sibling packet parked in retry/queued recovery merges into a recoverable
  scope primary before successful Flow recovery, appears in that recovery's
  suppression/events, and leaves the active registry empty afterward;
- cancel before admission, during handle, during retry delay, and during
  recovery/combine;
- a captured emission buffer under an existing attempt/scope/run fence is
  discarded without route resolution, input/output inspection, allocation, or
  publication; attempt timeout keeps its timeout disposition and later callback
  settlement is discarded;
- fresh attempt signals after cooperative timeout;
- no retry overlap with a timed-out attempt;
- sibling success/failure after a fence and recovery only after settlement;
- deadline/cancellation/failure first-fence races;
- grace expiry and immutable abandonment;
- separate attempt-grace and recoverable-scope-grace promotion fixtures with
  several active packets, proving heap-order primary selection, complete drain,
  run-fence event order, and an empty registry;
- attempt/scope/run grace timestamps never reset and overlapping fences use the
  earliest due time;
- `remaining_ms` / `remainingMs` reports run/attempt time before a fence and the
  earliest controlling grace afterward for caller cancel, scope failure, attempt
  timeout, and overlapping fences; due reports zero and closed Context raises;
- slow fence observers and synchronous TypeScript abort listeners see committed,
  already-signalled state; listener settlements remain queued and reentrant
  cancellation cannot change the first fence/reason;
- cancellation or grace crossed by the first attempt/scope fence observer
  commits immediately but cannot interleave its run events inside the current
  contiguous publication bundle;
- Python token cancellation versus TypeScript abort settlement normalization;
- Python wrappers catch `BaseException`: a token-correlated `CancelledError` is
  cooperative, while unsignalled `CancelledError`, `KeyboardInterrupt`,
  `SystemExit`, and `GeneratorExit` become the exact lifecycle Failure and the
  run still settles once; TypeScript uncorrelated abort-like errors match it;
- `BaseException` from retry policy, observer, live state/mapping access, and
  initial-state mapping access follows its policy-Failure, diagnostic,
  callback-Failure, or pre-start `OptionValidationError` boundary respectively,
  with exact cause identity and no scheduler escape;
- late callback outcomes observed and discarded without unhandled rejections.

### Scheduling and observation

- `start()` drains opening-caused event bundles synchronously, admits no
  lifecycle callback before returning, and may return already done after an
  immediate opening fence; `done`, result-envelope freeze, Promise/Future settlement,
  repeated result reads, and post-terminal `cancel()` follow the exact handle
  timing and object-identity contract;
- synchronous and asynchronous handlers in both ports have zero application
  side effects when a `callback_started` observer cancels or crosses the
  attempt/run deadline: the starting wrapper skips before invocation, publishes
  fence then callback-finish order, preserves admitted stats, and zero grace does
  not abandon work that never began;
- zero deadline and a slow `run_started` observer preserve the contiguous
  sequence-1/2 opening bundle, commit the deadline fence during observation,
  then report exact two-activation/one-scope/peak-ready-one zero-work stats;
- observer cancellation from the first `failure_recorded` cannot interleave its
  events before the matching `callback_finished`, and cancellation from the
  first transition/terminal event cannot interleave before the rest of that
  already-committed emission/forwarding publication bundle;
- a long emission bundle whose observer crosses an attempt timeout, whose token
  listener cancels the run, and whose zero grace commits abandonment uses only
  the fixed current/local/run/terminal slots; it delivers every bundle in
  control-commit order, keeps `run_finished` last, and counts duration only up to
  terminal commit despite slower observers afterward;
- terminal suppression/result materialization that crosses a fake deadline
  after the final linearization checkpoint preserves the fixed status, stats,
  and complete collections;
- every started scope finishes exactly once before `run_finished`; nested
  siblings with pre-fence terminals under completed/failed/cancelled/abandoned
  runs prove child-before-parent and `(depth desc, scope_id asc)` terminal order,
  internal-only terminal sequences, exact stats, and terminal-observer duration
  exclusion;
- direct-scope concurrency, nested parallelism, and the effective global callback
  ceiling; all-local-one topology proves serial admission, topology-auto equals
  the maximum local Flow cap rather than a product/sum, and explicit lower/higher
  run overrides retain local caps;
- with the callback ceiling saturated, a blocked Node-head scope cannot prevent
  a permit-free nested-Flow head in another scope from starting; ready-category
  instrumentation proves no pop/restore loop or queue scan;
- two concurrently ready callbacks prove that node-local exhaustion/policy
  decline and failed Flow combination release their old permit, enqueue recovery
  at the `callback_ready` tail, and never invoke recovery inline;
- nested flow waiting without a callback permit;
- FIFO order within one scope and round-robin readiness across scopes;
- retry timers retaining live tokens and scope slots;
- live attempt/grace/deadline timers, removal, and every tie priority;
- fake-clock durations near `MAX_SAFE_INTEGER` prove overflow-safe ordering and
  equality, public duration saturation at `MAX_SAFE_INTEGER`, and a host with a
  small maximum wake delay does not shorten a long timer;
- activation, transition, ready, depth, and safe-integer bounds;
- a scope-local cap counts its entry, counts nested Flow owners only in the parent,
  excludes descendants/retries/callbacks/transitions, resets for every scope
  invocation, and atomically rejects an over-cap fan-out after the run-wide
  activation check but before `max_ready`; the Failure names the receiving scope
  and `scope_max_activations` without partial activations;
- root and nested entry activation IDs in budgets, stats, and causal events;
- the complete ancestry/source table for root owner/entry, Node routes, nested
  Flow owner/entry, Flow boundary routes, direct Ends, fan-out, retries, and
  recovery yields identical `parent_activation_id` and
  `source_activation_id` values in both ports;
- report before a fence accepted; post-fence/closed-Context report emits and
  counts nothing and raises existing cancellation/framework error;
- report names reject wrong types and empty strings after fence/timer checks but
  before budget accounting: a fence wins without inspecting the name, semantic
  misuse wins over an exhausted budget, and no rejected name is charged;
- first report-budget overflow creates one failure, while repeated caught calls
  cannot grow events, failures, diagnostics, or IDs;
- portable event-sequence capacity;
- omitted versus explicit `None` / `null` / `undefined` report data;
- direct Python `payload.data` reads return `None` for omitted data while
  `has_data` distinguishes it from explicit `None`; TypeScript exposes a present
  `data=undefined` field and uses `hasData` to distinguish omission from explicit
  `undefined`; neither port exposes an internal sentinel;
- every event discriminator, required field, report-data presence variant,
  destination variant, and complete failure payload;
- the exact callback-disposition/transition-kind table for synthetic default,
  scalar emit/end, mixed fan-out, exact Flow forwarding, and unhandled recovery,
  including a preflight failure that commits no transition;
- event order after committed transitions, with zero-based branch index equal to
  emission-buffer or forwarded-terminal order;
- complete retried/recovered failure events and exact fence producer order;
- nested-parent and root-boundary transition/terminal scope ownership;
- observer cancellation affecting only subsequent work;
- cancellation from a report/non-fence observer commits immediately, delivers
  no recursive callback, drains its pending bundle before application work
  resumes, and makes `report()` raise the existing cancellation;
- an out-of-bundle `RunHandle.cancel()` synchronously drains its fence and
  checkpoint-caused terminal bundles before returning without harvesting an
  unrelated settlement, while cancel called inside an observer signals
  immediately but defers nonrecursive publication until the current bundle ends;
- observer backpressure included in deadline and attempt timeout;
- observer exception/awaitable disablement, the same best-effort native cleanup
  matrix and custom-object fallback, and final diagnostic insertion;
- strict TypeScript rejects an `async` Observer against the `undefined` return
  type, while dynamic asynchronous observer values still follow runtime
  disposal;
- observer/report reentrancy disablement without recursive delivery;
- finite synchronous overrun caught when the host event loop regains control;
- concurrent runs of one compiled graph with isolated framework state and one
  distinct shared application-state map per invocation.

### Migration

- v2 subclass lifecycle becomes function-backed `node` / `@node` without a
  hidden return-value control protocol;
- v2 global Memory becomes one run-owned `context.state` shallow-copied at start,
  and the ordinary caller reads the returned state directly from `run()`;
- v2 local/fork data becomes `context.input`, and terminal branch data becomes
  `context.end(...)`;
- implicit default and multiple-trigger examples become zero or multiple
  buffered Context emissions, with source order and atomic commit tested;
- migration fixtures distinguish v2 `DEFAULT_ACTION` / sentinel `"default"`
  from a genuine domain action named `"default"`, and pair the former only with
  an unlabelled v3 link;
- intentionally propagated v2 named actions declare matching Flow exits at
  every boundary, while accidental missing links become `unknown_action`;
- custom v2 Flow preparation, post-processing, and scheduling receive the
  explicit entry/combine/extension rewrites above; fixtures translate exact
  Python `Flow(start, {"max_visits": N})`, TypeScript `{ maxVisits: N }`, and the
  v2 default `15` into an explicitly chosen aggregate Flow-local activation cap
  and/or run-wide budgets rather than an exact per-placement visit counter;
- v2 retry migration documents the whole-handler at-least-once boundary and
  retained shared-state/external effects, plus the multi-node split when the old
  retry/commit boundary is material;
- migration fixtures cover nested borrowed aliases, explicit input copying where
  old deep local cloning mattered, and parallel conflicting-write warnings;
- published Python and TypeScript v2/v3 comparisons include complete imports;
  their v3 sides contain no Node subclass, Memory, decision, patch,
  branch-state, or `run_many` vocabulary;
- every complete v3 TypeScript example passes
  `tsc --strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess` with
  only its declared application stubs; every complete Python example parses, and examples presented as typed
  type-check under the documented mypy/pyright targets; isolated grammar
  fragments run inside typed fixture scaffolds, and the explicitly labelled v2
  comparison blocks are checked against the v2 surfaces they demonstrate.

## Release gates

V3 may ship only when:

1. Python and TypeScript pass the complete shared conformance matrix with no
   language-specific semantic exception.
2. The normative Python surface imports/compiles and the TypeScript declaration
   surface passes
   `tsc --strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess`.
3. Serial reference fixtures agree on topology, state, input, output, terminal,
   error, event, and stats snapshots.
4. Compile/run instrumentation confirms the stated bounds on long chains, cycles,
   wide emission fan-out, nested scopes, packets, timers, and one-state memory.
5. Cancellation tests include uncooperative Python tasks and JavaScript promises
   and demonstrate immutable failure/cancellation fences and abandonment.
6. Documentation teaches the ordinary grammar before policy: `@node` /
   `node(handler)`, `context.state`, optional `context.input`, `emit` / `end`,
   `link`, `Flow`, and direct `run()` state.
7. Every official example uses function-backed node occurrences and buffered
   Context control. Examples introduce `link`, token input, terminal output, and
   `start()` only when their lesson requires those concepts; the suite covers
   each of them explicitly.
8. The cookbook v3 design ports execute against both implementations where a
   cross-port equivalent exists, preserve their documented behavior, and pass a
   fresh before/after API review.
9. Outside explicitly labelled v2 migration and rejected-alternative prose, a
   repository-wide stale-model scan finds no public Node subclass example,
   `prep/exec/post`, trigger, Caskada control decision/patch object, branch state,
   scoped terminal state, trunk, `ParallelFlow`, or `run_many` in v3 material.
   Extension-domain DTOs such as the router example's `RouteDecision` are not
   Caskada control objects.
10. Core has zero runtime dependencies; the TypeScript suite passes in a browser
    runtime; concurrent runs of one compiled graph share no framework state and
    own distinct top-level state maps. Borrowed nested values and injected
    dependencies may be shared only under the documented application contract.
11. Fresh independent reviews of author API, kernel semantics, and cross-port
    implementability each report no blocker or major issue against this RFC's
    quality bar.

## Research alignment

The definition/run separation follows a broadly proven boundary: XState treats a
machine as an inert definition and an actor as its running process
([XState machines](https://stately.ai/docs/machines)); Dask likewise represents
task graphs as data consumed by a scheduler
([Dask task graphs](https://docs.dask.org/en/stable/graphs.html)). Caskada keeps
that boundary without adopting either system's domain model.

Structured nested scopes and explicit cancellation are consistent with the
failure-containment goals of Python's `TaskGroup`
([Python task groups](https://docs.python.org/3/library/asyncio-task.html#task-groups))
and the web-standard `AbortController`
([Node.js AbortController](https://nodejs.org/api/globals.html#class-abortcontroller)).
Caskada cannot force user work to cooperate, so `Abandoned` makes that limit
observable rather than claiming cancellation succeeded.

LangGraph's compile-before-invoke API demonstrates that compilation can validate
and prepare topology without turning authoring into executable generated code
([LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)).
Caskada's compiler is intentionally narrower: topology, scope, and scalar policy
only.

Durability systems such as Temporal solve crash recovery by imposing durable
workflow execution constraints
([Temporal workflow execution](https://docs.temporal.io/workflow-execution)).
That is a different product boundary. This RFC deliberately specifies an
in-process structured runner and leaves persistence to an extension or another
runtime.

## Final decision ledger

| ID  | Decision                | V3 call                                                                                                                                                                                                   |
| --- | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Product identity        | Keep `Caskada`; describe it as a structured graph runtime.                                                                                                                                                |
| D2  | Authoring unit          | Behavior is a function; each `node(handler, ...)` / Python `@node` call creates one lightweight topology-bearing Node occurrence.                                                                         |
| D3  | Lifecycle               | One handler callback, optional Node recovery, optional Flow combine/recovery; all return `None` / `void` and use ordinary helpers or `try/finally`.                                                       |
| D4  | Control                 | Invocation-local `context.emit` and `context.end` append to one private buffer; successful settlement commits it atomically.                                                                              |
| D5  | Default control         | Zero normal-handler emissions mean one unlabelled route; zero recovery/combine emissions mean exact failure/terminal pass-through.                                                                        |
| D6  | Topology                | Target-first `link(target, action?)` declares one target per action; omission alone is unlabelled, call count creates fan-out, and there are no public decision, patch, fork, or reserved-action objects. |
| D7  | Data roles              | One run-owned shared `context.state`, one branch `context.input`, and terminal output remain opaque application data; local static types require narrowing but do not validate links.                     |
| D8  | State ownership         | Shallow-copy `initial_state` once into one persistent carrier shared by every Context/result; aliases remain live; expose no per-branch copy/merge or borrow mode.                                        |
| D9  | Flow scope              | A Flow owns structured wait, direct-child concurrency, an optional direct-activation cap, terminals, one ordered outputs projection, combine/recovery, named exits, and forwarding.                       |
| D10 | Run APIs                | `run(initial_state)` returns singular shared state for every completion and raises one exact-result `RunError` otherwise; `start(initial_state)` is lossless.                                             |
| D11 | Definition/run boundary | `compile()` snapshots inspectable topology; every invocation owns runtime IDs, queues, packets, timers, state, and Context epochs; remove clone/seal.                                                     |
| D12 | Parallelism             | Flow concurrency defaults to one; omitted run concurrency uses the maximum compiled local concurrency, explicit overrides govern aggregate callbacks, and local concurrency caps remain.                  |
| D13 | Reliability             | Bounded work, at-least-once retries with constant/callback delay, packet-owned recovery, deterministic fences, cancellation, grace, and abandonment.                                                      |
| D14 | Observability           | Read-only `links()` / `describe()` plus one synchronous nonfatal observer and `report()`; streams and retained trees are adapters.                                                                        |
| D15 | Higher layers           | Semantic route metadata, the proposed Jig Graph layer, agents, durability, persistence, distribution, and dynamic workflow catalogues remain extensions.                                                  |

This ledger is normative. An implementation detail may change only when both
ports retain the specified behavior and the change does not add an author-facing
concept or weaken the ordinary grammar.
