# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
from __future__ import annotations

import asyncio
import inspect
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    Literal,
    Protocol,
    Self,
    TypeAlias,
    TypedDict,
    TypeVar,
    cast,
    final,
    overload,
)

MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_PORTABLE_COLLECTION_LENGTH = 4_294_967_295
RUN_EVENT_SCHEMA_VERSION = 1
_MAX_HOST_TIMER_DELAY_MS = 2_147_483_647

Action: TypeAlias = str
Phase: TypeAlias = Literal[
    "handle",
    "node_recover",
    "flow_combine",
    "flow_recover",
]
T = TypeVar("T")
StateT = TypeVar("StateT", default=dict[str, Any])
InputT = TypeVar("InputT", default=object)
ContextStateT_co = TypeVar(
    "ContextStateT_co",
    covariant=True,
    default=dict[str, Any],
)
ContextInputT_co = TypeVar("ContextInputT_co", covariant=True, default=object)
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


class Context(Protocol, Generic[ContextStateT_co, ContextInputT_co]):
    """Runtime-issued callback context."""

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
    def emit(self) -> None: ...

    @overload
    def emit(self, *, input: object) -> None: ...

    @overload
    def emit(self, action: Action, /) -> None: ...

    @overload
    def emit(self, action: Action, /, input: object) -> None: ...

    @overload
    def end(self) -> None: ...

    @overload
    def end(self, output: object) -> None: ...

    @overload
    def report(self, name: str) -> None: ...

    @overload
    def report(self, name: str, data: object) -> None: ...


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class EndTerminal:
    has_output: bool
    output: object
    sequence: int
    source_activation_id: int
    type: Literal["end"] = field(default="end", init=False)

    def __repr__(self) -> str:
        return (
            "EndTerminal("
            f"has_output={self.has_output!r}, sequence={self.sequence!r}, "
            f"source_activation_id={self.source_activation_id!r})"
        )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ExitTerminal:
    action: Action | None
    output: object
    sequence: int
    source_activation_id: int
    has_output: Literal[True] = field(default=True, init=False)
    type: Literal["exit"] = field(default="exit", init=False)

    def __repr__(self) -> str:
        return (
            "ExitTerminal("
            f"action={self.action!r}, sequence={self.sequence!r}, "
            f"source_activation_id={self.source_activation_id!r})"
        )


Terminal: TypeAlias = EndTerminal | ExitTerminal
NonEmptyTerminals: TypeAlias = tuple[Terminal, *tuple[Terminal, ...]]


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ScopeResult:
    terminals: NonEmptyTerminals
    outputs: tuple[object, ...]

    def __repr__(self) -> str:
        return (
            f"ScopeResult(terminals=<count {len(self.terminals)}>, "
            f"outputs=<count {len(self.outputs)}>)"
        )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ScopeFailure:
    primary: Failure
    suppressed: Sequence[Failure]
    settled_before_fence: tuple[Terminal, ...]
    result: ScopeResult | None
    failing_activation_id: int | None

    def __repr__(self) -> str:
        return (
            "ScopeFailure("
            f"primary=<Failure {self.primary.failure_id}>, "
            f"suppressed=<count {len(self.suppressed)}>, "
            f"settled_before_fence=<count {len(self.settled_before_fence)}>, "
            f"result={'present' if self.result is not None else 'None'}, "
            f"failing_activation_id={self.failing_activation_id!r})"
        )


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
    "state_record_misuse",
    "report_name",
]
InvalidCombinationReason: TypeAlias = InvalidOutcomeReason
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
    type: Literal["invalid_outcome"] = field(default="invalid_outcome", init=False)


@dataclass(frozen=True, slots=True)
class InvalidCombinationDetail:
    reason: InvalidCombinationReason
    type: Literal["invalid_combination"] = field(
        default="invalid_combination", init=False
    )


@dataclass(frozen=True, slots=True)
class UnknownActionDetail:
    action: Action
    type: Literal["unknown_action"] = field(default="unknown_action", init=False)


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

_FAILURE_MESSAGES: dict[FailureKind, str] = {
    "handler": "Node handler raised",
    "handler_timeout": "Node handler timed out",
    "retry_policy": "Retry policy failed",
    "node_recovery": "Node recovery raised",
    "flow_combine": "Flow combine raised",
    "flow_recovery": "Flow recovery raised",
    "invalid_outcome": "Invalid callback outcome",
    "invalid_combination": "Invalid Flow callback outcome",
    "unknown_action": "Unknown action",
    "limit": "Run limit exceeded",
    "internal": "Caskada runtime invariant failed",
}


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

    def __repr__(self) -> str:
        previous_id = None if self.previous is None else self.previous.failure_id
        return (
            "Failure("
            f"failure_id={self.failure_id!r}, kind={self.kind!r}, "
            f"scope_id={self.scope_id!r}, activation_id={self.activation_id!r}, "
            f"element_id={self.element_id!r}, attempt={self.attempt!r}, "
            f"detail={self.detail!r}, previous_failure_id={previous_id!r})"
        )


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
    outcome: Literal["route", "fanout", "end", "forward", "unhandled"]


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
    kind: Literal["callback_started"] = field(default="callback_started", init=False)


@dataclass(frozen=True, slots=True)
class CallbackFinishedEvent:
    sequence: int
    run_id: str
    payload: CallbackFinishedPayload
    kind: Literal["callback_finished"] = field(default="callback_finished", init=False)


@dataclass(frozen=True, slots=True)
class RetryScheduledEvent:
    sequence: int
    run_id: str
    payload: RetryScheduledPayload
    kind: Literal["retry_scheduled"] = field(default="retry_scheduled", init=False)


@dataclass(frozen=True, slots=True)
class TransitionCommittedEvent:
    sequence: int
    run_id: str
    payload: TransitionCommittedPayload
    kind: Literal["transition_committed"] = field(
        default="transition_committed", init=False
    )


@dataclass(frozen=True, slots=True)
class TerminalCommittedEvent:
    sequence: int
    run_id: str
    payload: TerminalCommittedPayload
    kind: Literal["terminal_committed"] = field(
        default="terminal_committed", init=False
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
    kind: Literal["failure_recorded"] = field(default="failure_recorded", init=False)


@dataclass(frozen=True, slots=True)
class CancellationFencedEvent:
    sequence: int
    run_id: str
    payload: CancellationFencedPayload
    kind: Literal["cancellation_fenced"] = field(
        default="cancellation_fenced", init=False
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

    def __post_init__(self) -> None:
        if self.max_concurrency is not None:
            _require_run_positive_integer(
                self.max_concurrency, "RunOptions.max_concurrency"
            )
        _require_run_positive_integer(
            self.max_activations, "RunOptions.max_activations"
        )
        if self.max_activations < 2:
            raise OptionValidationError("RunOptions.max_activations must be at least 2")
        _require_run_positive_integer(self.max_attempts, "RunOptions.max_attempts")
        _require_run_positive_integer(
            self.max_transitions, "RunOptions.max_transitions"
        )
        _require_run_positive_integer(self.max_ready, "RunOptions.max_ready")
        _require_run_positive_integer(self.max_reports, "RunOptions.max_reports")
        _require_run_positive_integer(self.max_depth, "RunOptions.max_depth")
        if self.deadline_ms is not None:
            _require_run_nonnegative_integer(self.deadline_ms, "RunOptions.deadline_ms")
        _require_run_nonnegative_integer(
            self.cancel_grace_ms, "RunOptions.cancel_grace_ms"
        )
        if self.observer is not None and not callable(self.observer):
            raise OptionValidationError("RunOptions.observer must be callable")
        if self.run_id is not None and (
            type(self.run_id) is not str or not self.run_id
        ):
            raise OptionValidationError("RunOptions.run_id must be a nonempty string")
        event_capacity = (
            16
            + 16 * self.max_activations
            + 8 * self.max_attempts
            + 4 * self.max_transitions
            + self.max_reports
        )
        if event_capacity > MAX_PORTABLE_COLLECTION_LENGTH:
            raise OptionValidationError(
                "RunOptions event capacity exceeds the portable collection limit"
            )


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

    def __repr__(self) -> str:
        return (
            "ObserverDiagnostic("
            f"event_sequence={self.event_sequence!r}, message={self.message!r})"
        )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class CancellationInfo:
    reason: Any
    deadline: bool

    def __repr__(self) -> str:
        return f"CancellationInfo(deadline={self.deadline!r})"


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Completed(Generic[StateT]):
    status: Literal["completed"]
    state: StateT
    terminals: NonEmptyTerminals
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str:
        return (
            "Completed("
            f"status={self.status!r}, terminals=<count {len(self.terminals)}>, "
            f"diagnostics=<count {len(self.diagnostics)}>)"
        )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Failed(Generic[StateT]):
    status: Literal["failed"]
    state: StateT
    terminals: tuple[Terminal, ...]
    failure: Failure
    suppressed: tuple[Failure, ...]
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str:
        return (
            "Failed("
            f"status={self.status!r}, terminals=<count {len(self.terminals)}>, "
            f"failure_id={self.failure.failure_id!r}, "
            f"suppressed=<count {len(self.suppressed)}>, "
            f"diagnostics=<count {len(self.diagnostics)}>)"
        )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Cancelled(Generic[StateT]):
    status: Literal["cancelled"]
    state: StateT
    terminals: tuple[Terminal, ...]
    cancellation: CancellationInfo
    suppressed: tuple[Failure, ...]
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str:
        return (
            "Cancelled("
            f"status={self.status!r}, terminals=<count {len(self.terminals)}>, "
            f"suppressed=<count {len(self.suppressed)}>, "
            f"diagnostics=<count {len(self.diagnostics)}>)"
        )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Abandoned(Generic[StateT]):
    status: Literal["abandoned"]
    state: StateT
    terminals: tuple[Terminal, ...]
    cause: Failure | CancellationInfo
    suppressed: tuple[Failure, ...]
    stats: RunStats
    diagnostics: tuple[ObserverDiagnostic, ...]

    def __repr__(self) -> str:
        return (
            "Abandoned("
            f"status={self.status!r}, terminals=<count {len(self.terminals)}>, "
            f"suppressed=<count {len(self.suppressed)}>, "
            f"diagnostics=<count {len(self.diagnostics)}>)"
        )


RunResult: TypeAlias = (
    Completed[StateT] | Failed[StateT] | Cancelled[StateT] | Abandoned[StateT]
)


class RunError(CaskadaError, Generic[StateT]):
    def __init__(
        self,
        result: Failed[StateT] | Cancelled[StateT] | Abandoned[StateT],
    ) -> None:
        message = {
            "failed": "Caskada run failed",
            "cancelled": "Caskada run cancelled",
            "abandoned": "Caskada run abandoned",
        }[result.status]
        super().__init__(message)
        self._result = result

    @property
    def result(self) -> Failed[StateT] | Cancelled[StateT] | Abandoned[StateT]:
        return self._result


class RunHandle(Protocol, Generic[StateT]):
    def cancel(self, reason: Any = "cancelled") -> None: ...

    def done(self) -> bool: ...

    async def result(self) -> RunResult[StateT]: ...


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


def _definition_error(
    message: str, cause: BaseException | None = None
) -> GraphDefinitionError:
    error = GraphDefinitionError(message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _require_control_string(value: object, field: str) -> str:
    if type(value) is not str or not value:
        raise GraphDefinitionError(f"{field} must be a nonempty string")
    return value


def _require_positive_integer(value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_SAFE_INTEGER:
        raise GraphDefinitionError(
            f"{field} must be a positive integer no greater than MAX_SAFE_INTEGER"
        )
    return value


def _require_nonnegative_integer(value: object, field: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
        raise GraphDefinitionError(
            f"{field} must be a nonnegative integer no greater than MAX_SAFE_INTEGER"
        )
    return value


def _require_run_positive_integer(value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_SAFE_INTEGER:
        raise OptionValidationError(
            f"{field} must be a positive integer no greater than MAX_SAFE_INTEGER"
        )
    return value


def _require_run_nonnegative_integer(value: object, field: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
        raise OptionValidationError(
            f"{field} must be a nonnegative integer no greater than MAX_SAFE_INTEGER"
        )
    return value


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    should_retry: Callable[[Failure], bool] = _retry_all
    delay_ms: int | Callable[[int, Failure], int] = 0

    def __post_init__(self) -> None:
        _require_positive_integer(self.max_attempts, "RetryPolicy.max_attempts")
        if not callable(self.should_retry):
            raise GraphDefinitionError("RetryPolicy.should_retry must be callable")
        if not callable(self.delay_ms):
            _require_nonnegative_integer(self.delay_ms, "RetryPolicy.delay_ms")


_UNLABELLED = object()


class GraphElement(ABC, Generic[StateT]):
    __slots__ = ("_links_by_action", "_links_in_order", "_name")

    def __init__(self, name: str) -> None:
        self._name = _require_control_string(name, "element name")
        self._links_in_order: list[Link[StateT]] = []
        self._links_by_action: dict[object, Link[StateT]] = {}

    @property
    def name(self) -> str:
        return self._name

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

    def link(
        self,
        target: GraphElement[StateT],
        /,
        action: Action | object = _UNLABELLED,
    ) -> None:
        if not isinstance(target, GraphElement):
            raise GraphDefinitionError("link target must be a GraphElement")

        if action is _UNLABELLED:
            key = _UNLABELLED
            public_action = None
        else:
            public_action = _require_control_string(action, "link action")
            key = public_action

        if key in self._links_by_action:
            description = "unlabelled" if key is _UNLABELLED else repr(public_action)
            raise DuplicateLinkError(f"duplicate link action: {description}")
        if len(self._links_in_order) >= MAX_PORTABLE_COLLECTION_LENGTH:
            raise GraphDefinitionError("link collection exceeds the portable limit")

        record = Link(action=public_action, target=target)
        self._links_by_action[key] = record
        self._links_in_order.append(record)

    def links(self) -> tuple[Link[StateT], ...]:
        return tuple(self._links_in_order)


@dataclass(frozen=True, slots=True)
class Link(Generic[StateT]):
    action: Action | None
    target: GraphElement[StateT]


class _NodeConstructionToken:
    pass


_NODE_CONSTRUCTION_TOKEN = _NodeConstructionToken()


@final
class Node(GraphElement[StateT], Generic[StateT]):
    __slots__ = ("_handler", "_recover", "_retry", "_timeout_ms")

    def __new__(cls, token: _NodeConstructionToken, /) -> Node[StateT]:
        if cls is not Node or token is not _NODE_CONSTRUCTION_TOKEN:
            raise TypeError("Use node(handler) to create a Node")
        return super().__new__(cls)

    def __init__(self, token: _NodeConstructionToken, /) -> None:
        if token is not _NODE_CONSTRUCTION_TOKEN:
            raise TypeError("Use node(handler) to create a Node")
        super().__init__("anonymous")
        self._handler: Callable[..., Any] | None = None
        self._recover: Callable[..., Any] | None = None
        self._retry = RetryPolicy()
        self._timeout_ms: int | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("Node is final; wrap a handler with node(...)")

    @property
    def _caskada_kind(self) -> Literal["node"]:
        return "node"

    @property
    def retry(self) -> RetryPolicy:
        return self._retry

    @property
    def timeout_ms(self) -> int | None:
        return self._timeout_ms


class Flow(GraphElement[StateT], Generic[StateT]):
    __slots__ = (
        "_combine",
        "_concurrency",
        "_entry",
        "_exits",
        "_max_activations",
        "_recover",
    )

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
    ) -> None:
        if not isinstance(entry, GraphElement):
            raise GraphDefinitionError("Flow.entry must be a GraphElement")
        if name is not None:
            resolved_name = _require_control_string(name, "Flow.name")
        else:
            resolved_name = "Flow"
        resolved_exits = _capture_exits(exits)
        resolved_concurrency = _require_positive_integer(
            concurrency, "Flow.concurrency"
        )
        resolved_max_activations = (
            None
            if max_activations is None
            else _require_positive_integer(max_activations, "Flow.max_activations")
        )
        if combine is not None and not callable(combine):
            raise GraphDefinitionError("Flow.combine must be callable")
        if recover is not None and not callable(recover):
            raise GraphDefinitionError("Flow.recover must be callable")

        super().__init__(resolved_name)
        self._entry = entry
        self._exits = resolved_exits
        self._concurrency = resolved_concurrency
        self._max_activations = resolved_max_activations
        self._combine = combine
        self._recover = recover

    @property
    def _caskada_kind(self) -> Literal["flow"]:
        return "flow"

    @property
    def entry(self) -> GraphElement[StateT]:
        return self._entry

    @property
    def exits(self) -> tuple[Action, ...]:
        return self._exits

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @property
    def max_activations(self) -> int | None:
        return self._max_activations

    def compile(self) -> CompiledFlow[StateT]:
        return _compile_flow(self)

    def start(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> RunHandle[StateT]:
        loop = _require_running_loop()
        captured_options = _capture_run_options(options)
        compiled = self.compile()
        if compiled._snapshot is None:
            raise RuntimeError("CompiledFlow is not initialized")
        state = _capture_initial_state(initial_state)
        return _start_runtime(compiled._snapshot, state, loop, captured_options)

    async def run(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> StateT:
        handle = self.start(initial_state, options=options)
        try:
            result = await handle.result()
        except asyncio.CancelledError:
            handle.cancel("caller_cancelled")
            raise
        if result.status == "completed":
            return result.state
        raise RunError(result)


def _capture_exits(exits: Sequence[Action]) -> tuple[Action, ...]:
    if isinstance(exits, (str, bytes)) or not isinstance(exits, Sequence):
        raise GraphDefinitionError("Flow.exits must be a sequence of actions")
    try:
        gross_length = len(exits)
    except BaseException as error:  # noqa: BLE001 - definition capture is total.
        raise _definition_error("Flow.exits could not be captured", error)
    if gross_length > MAX_PORTABLE_COLLECTION_LENGTH:
        raise GraphDefinitionError("Flow.exits exceeds the portable limit")

    try:
        iterator = iter(exits)
    except BaseException as error:  # noqa: BLE001 - definition capture is total.
        raise _definition_error("Flow.exits could not be captured", error)

    captured: list[str] = []
    seen: set[str] = set()
    while True:
        try:
            raw_action = next(iterator)
        except StopIteration:
            break
        except BaseException as error:  # noqa: BLE001 - definition capture is total.
            raise _definition_error("Flow.exits could not be captured", error)
        if len(captured) >= MAX_PORTABLE_COLLECTION_LENGTH:
            raise GraphDefinitionError("Flow.exits exceeds the portable limit")
        action = _require_control_string(raw_action, "Flow exit")
        if action in seen:
            raise GraphDefinitionError(f"duplicate Flow exit: {action!r}")
        captured.append(action)
        seen.add(action)
    return tuple(captured)


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


@dataclass(frozen=True, slots=True)
class _CompiledLink:
    action: Action | None
    target_element_id: int


@dataclass(frozen=True, slots=True)
class _CompiledPlacement:
    element_id: int
    kind: Literal["node", "flow"]
    name: str
    parent_scope_definition_id: int | None
    definition: GraphElement[Any]
    links: tuple[_CompiledLink, ...]
    owned_scope_definition_id: int | None = None
    retry: RetryPolicy | None = None
    timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class _CompiledScope:
    scope_definition_id: int
    owner_element_id: int
    parent_scope_definition_id: int | None
    entry_element_id: int
    exits: tuple[Action, ...]
    concurrency: int
    max_activations: int | None
    flow: Flow[Any]
    combine: Callable[..., Any] | None
    recover: Callable[..., Any] | None


@dataclass(frozen=True, slots=True)
class _CompiledSnapshot:
    root: Flow[Any]
    auto_max_concurrency: int
    scopes: tuple[_CompiledScope, ...]
    placements: tuple[_CompiledPlacement, ...]


@dataclass(slots=True)
class _ScopeWork:
    scope_definition_id: int
    owner_element_id: int
    parent_scope_definition_id: int | None
    flow: Flow[Any]


class _CompiledFlowConstructionToken:
    pass


_COMPILED_FLOW_CONSTRUCTION_TOKEN = _CompiledFlowConstructionToken()


@final
class CompiledFlow(Generic[StateT]):
    __slots__ = ("_snapshot",)

    def __new__(
        cls,
        token: _CompiledFlowConstructionToken,
        /,
    ) -> CompiledFlow[StateT]:
        if cls is not CompiledFlow or token is not _COMPILED_FLOW_CONSTRUCTION_TOKEN:
            raise TypeError("Use Flow.compile() to create a CompiledFlow")
        return super().__new__(cls)

    def __init__(self, token: _CompiledFlowConstructionToken, /) -> None:
        if token is not _COMPILED_FLOW_CONSTRUCTION_TOKEN:
            raise TypeError("Use Flow.compile() to create a CompiledFlow")
        self._snapshot: _CompiledSnapshot | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("CompiledFlow is final; use Flow.compile()")

    def start(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> RunHandle[StateT]:
        loop = _require_running_loop()
        captured_options = _capture_run_options(options)
        if self._snapshot is None:
            raise RuntimeError("CompiledFlow is not initialized")
        state = _capture_initial_state(initial_state)
        return _start_runtime(self._snapshot, state, loop, captured_options)

    async def run(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> StateT:
        result = await self.start(initial_state, options=options).result()
        if result.status == "completed":
            return result.state
        raise RunError(result)

    def describe(self) -> CompiledDescription:
        if self._snapshot is None:
            raise RuntimeError("CompiledFlow is not initialized")
        return _describe_compiled(self._snapshot)


class _DefinitionCompiler:
    def __init__(self, root: Flow[Any]) -> None:
        self.root = root
        self.next_element_id = 2
        self.next_scope_definition_id = 2
        self.compiled_connection_count = 0
        self.compiled_exit_count = 0
        self.placements_by_id: dict[int, _CompiledPlacement] = {
            1: _CompiledPlacement(
                element_id=1,
                kind="flow",
                name=root.name,
                parent_scope_definition_id=None,
                definition=root,
                links=(),
                owned_scope_definition_id=1,
            )
        }
        self.owned_scope_by_element: dict[int, int] = {1: 1}
        self.scope_queue = [
            _ScopeWork(
                scope_definition_id=1,
                owner_element_id=1,
                parent_scope_definition_id=None,
                flow=root,
            )
        ]
        self.compiled_scopes: list[_CompiledScope] = []

    def compile(self) -> _CompiledSnapshot:
        scope_index = 0
        while scope_index < len(self.scope_queue):
            scope = self.scope_queue[scope_index]
            scope_index += 1
            self._compile_scope(scope)

        ordered_placements = tuple(
            self.placements_by_id[element_id]
            for element_id in range(1, self.next_element_id)
        )
        return _CompiledSnapshot(
            root=self.root,
            auto_max_concurrency=max(
                scope.concurrency for scope in self.compiled_scopes
            ),
            scopes=tuple(self.compiled_scopes),
            placements=ordered_placements,
        )

    def _compile_scope(self, scope: _ScopeWork) -> None:
        self.compiled_exit_count = _reserve_portable_total(
            self.compiled_exit_count,
            len(scope.flow.exits),
            "exit",
        )
        placements: dict[GraphElement[Any], int] = {}
        placement_queue: list[GraphElement[Any]] = []
        entry_element_id = self._enqueue(
            scope,
            scope.flow.entry,
            placements,
            placement_queue,
        )

        placement_index = 0
        while placement_index < len(placement_queue):
            element = placement_queue[placement_index]
            placement_index += 1
            element_id = placements[element]
            definition_links = element.links()
            self.compiled_connection_count = _reserve_portable_total(
                self.compiled_connection_count,
                len(definition_links),
                "connection",
            )
            compiled_links = tuple(
                _CompiledLink(
                    link.action,
                    self._enqueue(
                        scope,
                        link.target,
                        placements,
                        placement_queue,
                    ),
                )
                for link in definition_links
            )
            self._capture_placement(scope, element, element_id, compiled_links)

        self.compiled_scopes.append(
            _CompiledScope(
                scope_definition_id=scope.scope_definition_id,
                owner_element_id=scope.owner_element_id,
                parent_scope_definition_id=scope.parent_scope_definition_id,
                entry_element_id=entry_element_id,
                exits=scope.flow.exits,
                concurrency=scope.flow.concurrency,
                max_activations=scope.flow.max_activations,
                flow=scope.flow,
                combine=scope.flow._combine,
                recover=scope.flow._recover,
            )
        )

    def _enqueue(
        self,
        scope: _ScopeWork,
        element: GraphElement[Any],
        placements: dict[GraphElement[Any], int],
        placement_queue: list[GraphElement[Any]],
    ) -> int:
        if type(element) is not Node and type(element) is not Flow:
            raise GraphDefinitionError("unsupported GraphElement definition")
        existing = placements.get(element)
        if existing is not None:
            return existing
        _require_compiled_capacity(self.next_element_id, "element")
        element_id = self.next_element_id
        self.next_element_id += 1
        placements[element] = element_id
        placement_queue.append(element)

        if type(element) is Flow:
            _require_compiled_capacity(self.next_scope_definition_id, "scope")
            owned_scope_id = self.next_scope_definition_id
            self.next_scope_definition_id += 1
            self.owned_scope_by_element[element_id] = owned_scope_id
            self.scope_queue.append(
                _ScopeWork(
                    scope_definition_id=owned_scope_id,
                    owner_element_id=element_id,
                    parent_scope_definition_id=scope.scope_definition_id,
                    flow=element,
                )
            )
        return element_id

    def _capture_placement(
        self,
        scope: _ScopeWork,
        element: GraphElement[Any],
        element_id: int,
        compiled_links: tuple[_CompiledLink, ...],
    ) -> None:
        if type(element) is Node:
            self.placements_by_id[element_id] = _CompiledPlacement(
                element_id=element_id,
                kind="node",
                name=element.name,
                parent_scope_definition_id=scope.scope_definition_id,
                definition=element,
                links=compiled_links,
                retry=element.retry,
                timeout_ms=element.timeout_ms,
            )
            return
        self.placements_by_id[element_id] = _CompiledPlacement(
            element_id=element_id,
            kind="flow",
            name=element.name,
            parent_scope_definition_id=scope.scope_definition_id,
            definition=element,
            links=compiled_links,
            owned_scope_definition_id=self.owned_scope_by_element[element_id],
        )


def _compile_flow(root: Flow[StateT]) -> CompiledFlow[StateT]:
    if type(root) is not Flow:
        raise GraphDefinitionError("only runtime-created Flow definitions can compile")

    _validate_containment(root)
    snapshot = _DefinitionCompiler(root).compile()
    compiled: CompiledFlow[StateT] = CompiledFlow(_COMPILED_FLOW_CONSTRUCTION_TOKEN)
    compiled._snapshot = snapshot
    return compiled


def _validate_containment(root: Flow[Any]) -> None:
    adjacency: dict[Flow[Any], tuple[Flow[Any], ...]] = {}
    colors: dict[Flow[Any], Literal["active", "complete"]] = {root: "active"}
    stack: list[tuple[Flow[Any], int]] = [(root, 0)]

    while stack:
        flow, child_index = stack[-1]
        children = adjacency.get(flow)
        if children is None:
            children = _nested_flow_definitions(flow)
            adjacency[flow] = children
        if child_index >= len(children):
            colors[flow] = "complete"
            stack.pop()
            continue

        child = children[child_index]
        stack[-1] = (flow, child_index + 1)
        color = colors.get(child)
        if color == "active":
            raise GraphDefinitionError("recursive Flow containment is not allowed")
        if color == "complete":
            continue
        colors[child] = "active"
        stack.append((child, 0))


def _nested_flow_definitions(flow: Flow[Any]) -> tuple[Flow[Any], ...]:
    seen: set[GraphElement[Any]] = set()
    worklist: list[GraphElement[Any]] = [flow.entry]
    nested: list[Flow[Any]] = []
    work_index = 0
    while work_index < len(worklist):
        element = worklist[work_index]
        work_index += 1
        if element in seen:
            continue
        seen.add(element)
        if type(element) is not Node and type(element) is not Flow:
            raise GraphDefinitionError("unsupported GraphElement definition")
        if type(element) is Flow:
            nested.append(element)
        for link in element.links():
            worklist.append(link.target)
    return tuple(nested)


def _require_compiled_capacity(next_id: int, kind: str) -> None:
    if next_id > MAX_SAFE_INTEGER or next_id > MAX_PORTABLE_COLLECTION_LENGTH:
        raise GraphDefinitionError(
            f"compiled {kind} collection exceeds the portable limit"
        )


def _reserve_portable_total(current: int, addition: int, kind: str) -> int:
    if addition > MAX_PORTABLE_COLLECTION_LENGTH - current:
        raise GraphDefinitionError(
            f"compiled {kind} collection exceeds the portable limit"
        )
    return current + addition


def _describe_compiled(snapshot: _CompiledSnapshot) -> CompiledDescription:
    elements: list[CompiledElementDescription] = []
    for placement in snapshot.placements:
        links: list[CompiledLinkDescription] = [
            {
                "action": link.action,
                "target_element_id": link.target_element_id,
            }
            for link in placement.links
        ]
        if placement.kind == "node":
            if placement.retry is None or placement.parent_scope_definition_id is None:
                raise RuntimeError("invalid compiled Node placement")
            elements.append(
                {
                    "element_id": placement.element_id,
                    "kind": "node",
                    "name": placement.name,
                    "parent_scope_definition_id": placement.parent_scope_definition_id,
                    "links": links,
                    "retry": {"max_attempts": placement.retry.max_attempts},
                    "timeout_ms": placement.timeout_ms,
                }
            )
        else:
            if placement.owned_scope_definition_id is None:
                raise RuntimeError("invalid compiled Flow placement")
            elements.append(
                {
                    "element_id": placement.element_id,
                    "kind": "flow",
                    "name": placement.name,
                    "parent_scope_definition_id": placement.parent_scope_definition_id,
                    "owned_scope_definition_id": placement.owned_scope_definition_id,
                    "links": links,
                }
            )

    return {
        "schema_version": 1,
        "auto_max_concurrency": snapshot.auto_max_concurrency,
        "root": {"element_id": 1, "scope_definition_id": 1},
        "scope_definitions": [
            {
                "scope_definition_id": scope.scope_definition_id,
                "owner_element_id": scope.owner_element_id,
                "parent_scope_definition_id": scope.parent_scope_definition_id,
                "entry_element_id": scope.entry_element_id,
                "exits": list(scope.exits),
                "concurrency": scope.concurrency,
                "max_activations": scope.max_activations,
            }
            for scope in snapshot.scopes
        ],
        "elements": elements,
    }


_MISSING = object()


@overload
def node(
    handler: NodeHandler[StateT, InputT],
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),  # noqa: B008 - frozen normative default.
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Node[StateT]: ...


@overload
def node(
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),  # noqa: B008 - frozen normative default.
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Callable[[NodeHandler[StateT, InputT]], Node[StateT]]: ...


def node(
    handler: NodeHandler[StateT, InputT] | object = _MISSING,
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),  # noqa: B008 - frozen normative default.
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Node[StateT] | Callable[[NodeHandler[StateT, InputT]], Node[StateT]]:
    if type(retry) is not RetryPolicy:
        raise GraphDefinitionError("node retry must be an exact RetryPolicy")
    if timeout_ms is not None:
        _require_positive_integer(timeout_ms, "Node.timeout_ms")
    if recover is not None and not callable(recover):
        raise GraphDefinitionError("Node.recover must be callable")
    if name is not None:
        _require_control_string(name, "Node.name")

    def create(callback: NodeHandler[StateT, InputT]) -> Node[StateT]:
        if not callable(callback):
            raise GraphDefinitionError("node handler must be callable")
        if name is None:
            try:
                inferred_name = getattr(callback, "__name__", None)
            except BaseException as error:  # noqa: BLE001 - definition capture is total.
                raise _definition_error("node handler name could not be read", error)
            resolved_name = (
                inferred_name
                if type(inferred_name) is str and bool(inferred_name)
                else "anonymous"
            )
        else:
            resolved_name = name

        occurrence: Node[StateT] = Node(_NODE_CONSTRUCTION_TOKEN)
        occurrence._name = resolved_name
        occurrence._handler = callback
        occurrence._recover = recover
        occurrence._retry = retry
        occurrence._timeout_ms = timeout_ms
        return occurrence

    if handler is _MISSING:
        return create
    return create(handler)  # type: ignore[arg-type]


class _CancellationSource:
    __slots__ = (
        "_cancelled",
        "_children",
        "_deadline",
        "_event",
        "_fenced_ns",
        "_parent",
        "_reason",
    )

    def __init__(self, parent: _CancellationSource | None = None) -> None:
        self._cancelled = False
        self._children: set[_CancellationSource] = set()
        self._deadline = False
        self._fenced_ns: int | None = None
        self._parent = parent
        self._reason: Any = None
        self._event = asyncio.Event()
        if parent is not None:
            parent._children.add(self)
            if parent.cancelled:
                self.cancel(
                    parent.reason,
                    deadline=parent.deadline,
                    fenced_ns=parent.fenced_ns,
                )

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def reason(self) -> Any:
        return self._reason

    @property
    def deadline(self) -> bool:
        return self._deadline

    @property
    def fenced_ns(self) -> int | None:
        return self._fenced_ns

    async def wait(self) -> None:
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise asyncio.CancelledError

    def cancel(
        self,
        reason: Any,
        *,
        deadline: bool = False,
        fenced_ns: int | None = None,
    ) -> bool:
        if self._cancelled:
            return False
        self._cancelled = True
        self._reason = reason
        self._deadline = deadline
        self._fenced_ns = time.monotonic_ns() if fenced_ns is None else fenced_ns
        self._event.set()
        for child in tuple(self._children):
            child.cancel(
                reason,
                deadline=deadline,
                fenced_ns=self._fenced_ns,
            )
        return True

    def close(self) -> None:
        if self._parent is not None:
            self._parent._children.discard(self)
            self._parent = None


class _CallbackGate:
    """Run-wide callback permits with callback-ready priority."""

    __slots__ = (
        "_active",
        "_cancellation",
        "_high",
        "_limit",
        "_low_by_scope",
        "_low_members",
        "_low_scopes",
    )

    def __init__(self, limit: int, cancellation: _CancellationSource) -> None:
        self._limit = limit
        self._cancellation = cancellation
        self._active = 0
        self._high: deque[asyncio.Future[None]] = deque()
        self._low_by_scope: dict[int, deque[asyncio.Future[None]]] = {}
        self._low_scopes: deque[int] = deque()
        self._low_members: set[int] = set()

    async def acquire(
        self,
        *,
        ready_callback: bool,
        cancellation: _CancellationSource,
        scope_id: int | None = None,
    ) -> None:
        self._discard_cancelled_waiters()
        if not ready_callback and scope_id is None:
            raise RuntimeError("new callback waiter has no scope")
        if (
            self._active < self._limit
            and not self._high
            and (ready_callback or not self._low_scopes)
        ):
            self._active += 1
            return

        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[None] = loop.create_future()
        if ready_callback:
            self._high.append(waiter)
        else:
            resolved_scope_id = cast(int, scope_id)
            queue = self._low_by_scope.setdefault(resolved_scope_id, deque())
            queue.append(waiter)
            if resolved_scope_id not in self._low_members:
                self._low_members.add(resolved_scope_id)
                self._low_scopes.append(resolved_scope_id)
        cancellation_wait = loop.create_task(cancellation.wait())
        run_wait = loop.create_task(self._cancellation.wait())
        try:
            done, _pending = await asyncio.wait(
                {waiter, cancellation_wait, run_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if waiter in done:
                waiter.result()
                return
            if not waiter.done():
                waiter.cancel()
            raise asyncio.CancelledError
        finally:
            cancellation_wait.cancel()
            run_wait.cancel()
            self._discard_cancelled_waiters()

    def release(self) -> None:
        if self._active <= 0:
            raise RuntimeError("callback permit released without ownership")
        self._active -= 1
        self._admit_waiters()

    def _admit_waiters(self) -> None:
        self._discard_cancelled_waiters()
        while self._active < self._limit:
            waiter: asyncio.Future[None] | None = None
            if self._high:
                waiter = self._high.popleft()
            elif self._low_scopes:
                scope_id = self._low_scopes.popleft()
                self._low_members.discard(scope_id)
                queue = self._low_by_scope[scope_id]
                waiter = queue.popleft()
                if queue:
                    self._low_members.add(scope_id)
                    self._low_scopes.append(scope_id)
                else:
                    del self._low_by_scope[scope_id]
            if waiter is None:
                return
            if waiter.done():
                continue
            self._active += 1
            waiter.set_result(None)

    def _discard_cancelled_waiters(self) -> None:
        while self._high and self._high[0].done():
            self._high.popleft()
        for scope_id in tuple(self._low_scopes):
            queue = self._low_by_scope[scope_id]
            while queue and queue[0].done():
                queue.popleft()
            if queue:
                continue
            del self._low_by_scope[scope_id]
            self._low_members.discard(scope_id)
        if len(self._low_members) != len(self._low_scopes):
            self._low_scopes = deque(
                scope_id
                for scope_id in self._low_scopes
                if scope_id in self._low_members
            )


_EventSpec: TypeAlias = tuple[type[Any], object]


class _EventPublisher:
    __slots__ = (
        "_diagnostics",
        "_disabled",
        "_observer",
        "_pending",
        "_publishing",
        "_run_cancellation_published",
        "_run_id",
        "_sequence",
        "_terminal",
    )

    def __init__(self, run_id: str, observer: Observer | None) -> None:
        self._run_id = run_id
        self._observer = observer
        self._sequence = 0
        self._diagnostics: list[ObserverDiagnostic] = []
        self._disabled = False
        self._publishing = False
        self._pending: deque[tuple[_EventSpec, ...]] = deque()
        self._run_cancellation_published = False
        self._terminal = False

    @property
    def diagnostics(self) -> tuple[ObserverDiagnostic, ...]:
        return tuple(self._diagnostics)

    @property
    def publishing(self) -> bool:
        return self._publishing

    def publish(self, event_type: type[Any], payload: object) -> None:
        self.publish_bundle(((event_type, payload),))

    def publish_bundle(self, specs: Sequence[_EventSpec]) -> None:
        if not specs:
            return
        captured = tuple(specs)
        if self._publishing:
            self._pending.append(captured)
            return
        self._pending.append(captured)
        self._publishing = True
        try:
            while self._pending:
                bundle = self._pending.popleft()
                events: list[RunEvent] = []
                for event_type, payload in bundle:
                    self._sequence += 1
                    events.append(event_type(self._sequence, self._run_id, payload))
                for event in events:
                    self._invoke(event)
        finally:
            self._publishing = False

    def reject_reentrant_report(self) -> None:
        if not self._publishing or self._disabled:
            return
        self._disable(
            self._sequence,
            "Observer reentrancy disabled",
            None,
        )

    def publish_run_cancellation(self, reason: object, deadline: bool) -> None:
        if self._run_cancellation_published:
            return
        self._run_cancellation_published = True
        self.publish(
            CancellationFencedEvent,
            CancellationFencedPayload(RunFenceTarget(), reason, deadline),
        )

    def mark_run_cancellation_published(self) -> None:
        self._run_cancellation_published = True

    @property
    def terminal(self) -> bool:
        return self._terminal

    def mark_terminal(self) -> None:
        self._terminal = True

    def _invoke(self, event: RunEvent) -> None:
        observer = self._observer
        if observer is None or self._disabled:
            return
        try:
            result = observer(event)
        except BaseException as cause:  # noqa: BLE001 - observers are nonfatal.
            self._disable(event.sequence, "Observer raised", cause)
            return
        try:
            asynchronous = inspect.isawaitable(result) or inspect.isasyncgen(result)
        except BaseException as cause:  # noqa: BLE001 - inspection is nonfatal.
            self._disable(event.sequence, "Observer result inspection failed", cause)
            return
        if asynchronous:
            _dispose_invalid_sync_result(result)
            self._disable(
                event.sequence,
                "Observer must return synchronously",
                None,
            )

    def _disable(
        self,
        sequence: int,
        message: str,
        cause: BaseException | None,
    ) -> None:
        if self._disabled:
            return
        self._disabled = True
        self._diagnostics.append(ObserverDiagnostic(sequence, message, cause))


class _RuntimeRunHandle(Generic[StateT]):
    __slots__ = ("_cancellation", "_publisher", "_task")

    def __init__(
        self,
        task: asyncio.Task[RunResult[StateT]],
        cancellation: _CancellationSource,
        publisher: _EventPublisher,
    ) -> None:
        self._task = task
        self._cancellation = cancellation
        self._publisher = publisher

    def cancel(self, reason: Any = "cancelled") -> None:
        if self._task.done() or self._publisher.terminal:
            return
        if self._cancellation.cancel(reason):
            self._publisher.publish_run_cancellation(reason, False)

    def done(self) -> bool:
        return self._task.done()

    async def result(self) -> RunResult[StateT]:
        return await asyncio.shield(self._task)


def _require_running_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError(
            "Caskada start() requires a running asyncio event loop"
        ) from None


def _capture_run_options(options: object) -> RunOptions:
    if options is None:
        return RunOptions()
    if type(options) is not RunOptions:
        raise OptionValidationError("options must be an exact RunOptions instance")
    return options


_next_run_number = 1


def _allocate_run_id() -> str:
    global _next_run_number
    value = _next_run_number
    _next_run_number += 1
    return f"run-{value}"


def _start_runtime(
    snapshot: _CompiledSnapshot,
    state: _StateCarrier,
    loop: asyncio.AbstractEventLoop,
    options: RunOptions,
) -> _RuntimeRunHandle[Any]:
    started_ns = time.monotonic_ns()
    cancellation = _CancellationSource()
    run_id = options.run_id if options.run_id is not None else _allocate_run_id()
    publisher = _EventPublisher(run_id, options.observer)
    root_scope = next(
        scope for scope in snapshot.scopes if scope.scope_definition_id == 1
    )
    publisher.publish_bundle(
        (
            (RunStartedEvent, RunStartedPayload(1, 1)),
            (
                ScopeStartedEvent,
                ScopeStartedPayload(
                    scope_id=1,
                    parent_scope_id=None,
                    owner_activation_id=1,
                    entry_activation_id=2,
                    entry_element_id=root_scope.entry_element_id,
                    flow_element_id=1,
                    depth=1,
                ),
            ),
        )
    )

    async def execute() -> RunResult[Any]:
        deadline = (
            None
            if options.deadline_ms is None
            else _Deadline(started_ns, options.deadline_ms)
        )
        deadline_task = (
            None
            if deadline is None
            else loop.create_task(
                _watch_run_deadline(cancellation, deadline, publisher)
            )
        )
        try:
            outcome = await _RuntimeKernel(
                snapshot,
                state,
                started_ns,
                cancellation,
                run_id,
                options,
                deadline,
                publisher,
            ).run()
        finally:
            if deadline_task is not None:
                deadline_task.cancel()
        if outcome.cancellation is not None:
            return Cancelled(
                status="cancelled",
                state=state,
                terminals=outcome.terminals,
                cancellation=outcome.cancellation,
                suppressed=outcome.suppressed,
                stats=outcome.stats,
                diagnostics=publisher.diagnostics,
            )
        if outcome.abandonment is not None:
            return Abandoned(
                status="abandoned",
                state=state,
                terminals=outcome.terminals,
                cause=outcome.abandonment,
                suppressed=outcome.suppressed,
                stats=outcome.stats,
                diagnostics=publisher.diagnostics,
            )
        if outcome.failure is None:
            return Completed(
                status="completed",
                state=state,
                terminals=cast(NonEmptyTerminals, outcome.terminals),
                stats=outcome.stats,
                diagnostics=publisher.diagnostics,
            )
        return Failed(
            status="failed",
            state=state,
            terminals=outcome.terminals,
            failure=outcome.failure,
            suppressed=outcome.suppressed,
            stats=outcome.stats,
            diagnostics=publisher.diagnostics,
        )

    return _RuntimeRunHandle(loop.create_task(execute()), cancellation, publisher)


class _SemanticMisuse(TypeError):
    def __init__(self, reason: InvalidOutcomeReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class _ProducedFailure(Exception):
    def __init__(
        self,
        failure: Failure,
        suppressed: tuple[Failure, ...] = (),
    ) -> None:
        super().__init__(failure.message)
        self.failure = failure
        self.suppressed = suppressed


@dataclass(frozen=True, slots=True)
class _FailureFence:
    produced: _ProducedFailure


class _StateCarrier(dict[str, Any]):
    """Invocation-owned native dictionary storage with portable string keys."""

    def __getitem__(self, key: object) -> Any:
        return super().__getitem__(_require_state_key(key))

    def __setitem__(self, key: object, value: Any) -> None:
        super().__setitem__(_require_state_key(key), value)

    def __delitem__(self, key: object) -> None:
        super().__delitem__(_require_state_key(key))

    def __contains__(self, key: object) -> bool:
        return super().__contains__(_require_state_key(key))

    def get(self, key: object, default: Any = None) -> Any:
        return super().get(_require_state_key(key), default)

    def setdefault(self, key: object, default: Any = None) -> Any:
        return super().setdefault(_require_state_key(key), default)

    @overload
    def pop(self, key: object) -> Any: ...

    @overload
    def pop(self, key: object, default: Any) -> Any: ...

    def pop(self, key: object, default: object = _MISSING) -> Any:
        checked = _require_state_key(key)
        if default is _MISSING:
            return super().pop(checked)
        return super().pop(checked, default)

    def update(self, *args: object, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 argument, got {len(args)}")
        if args:
            self._update_from(args[0])
        for key, value in kwargs.items():
            self[key] = value

    def copy(self) -> dict[str, Any]:
        return dict(self)

    def __or__(self, other: object) -> dict[str, Any]:  # type: ignore[override]
        if not isinstance(other, dict):
            return NotImplemented
        result = dict(self)
        _update_plain_dict(result, other)
        return result

    def __ror__(self, other: object) -> dict[str, Any]:  # type: ignore[override]
        if not isinstance(other, dict):
            return NotImplemented
        result: dict[str, Any] = {}
        _update_plain_dict(result, other)
        result.update(dict(self))
        return result

    def __ior__(self, other: object) -> Self:  # type: ignore[override]
        if not isinstance(other, Mapping):
            return NotImplemented
        self._update_from(other)
        return self

    @classmethod
    def fromkeys(  # type: ignore[override]
        cls, iterable: object, value: Any = None
    ) -> _StateCarrier:
        result = cls()
        for key in cast(Any, iterable):
            result[key] = value
        return result

    def _update_from(self, source: object) -> None:
        dynamic_source = cast(Any, source)
        try:
            keys_method = dynamic_source.keys
        except AttributeError:
            keys_method = None
        if keys_method is not None:
            keys = keys_method()
            for key in keys:
                checked = _require_state_key(key)
                value = dynamic_source[checked]
                super().__setitem__(checked, value)
            return

        for index, item in enumerate(cast(Any, source)):
            try:
                key, value = item
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"dictionary update sequence element #{index} has invalid length"
                ) from error
            self[key] = value


def _require_state_key(key: object) -> str:
    if type(key) is not str:
        raise _SemanticMisuse("state_record_misuse", "state keys must be exact strings")
    return key


def _update_plain_dict(target: dict[str, Any], source: Mapping[object, Any]) -> None:
    for key in source:
        checked = _require_state_key(key)
        target[checked] = source[checked]


def _capture_initial_state(initial_state: object) -> _StateCarrier:
    if not isinstance(initial_state, Mapping):
        raise OptionValidationError("initial_state must be a Mapping")
    try:
        gross_length = len(initial_state)
    except BaseException as error:  # noqa: BLE001 - option capture is total.
        raise _option_error("initial_state length could not be read", error)
    if gross_length > MAX_PORTABLE_COLLECTION_LENGTH:
        raise OptionValidationError("initial_state exceeds the portable limit")
    try:
        iterator = iter(initial_state)
    except BaseException as error:  # noqa: BLE001 - option capture is total.
        raise _option_error("initial_state keys could not be read", error)

    state = _StateCarrier()
    seen: set[str] = set()
    while True:
        try:
            key = next(iterator)
        except StopIteration:
            break
        except BaseException as error:  # noqa: BLE001 - option capture is total.
            raise _option_error("initial_state keys could not be read", error)
        if len(seen) >= MAX_PORTABLE_COLLECTION_LENGTH:
            raise OptionValidationError("initial_state exceeds the portable limit")
        if type(key) is not str:
            raise OptionValidationError("initial_state keys must be exact strings")
        if key in seen:
            raise OptionValidationError("initial_state contains a duplicate key")
        seen.add(key)
        try:
            value = initial_state[key]
        except BaseException as error:  # noqa: BLE001 - option capture is total.
            raise _option_error("initial_state value could not be read", error)
        state[key] = value
    return state


def _option_error(message: str, cause: BaseException) -> OptionValidationError:
    error = OptionValidationError(message)
    error.__cause__ = cause
    return error


def _dispose_invalid_sync_result(value: object) -> None:
    if inspect.iscoroutine(value):
        try:
            value.close()
        except BaseException:  # noqa: BLE001, S110 - cleanup cannot change the Failure.
            pass
        return
    if isinstance(value, asyncio.Future):
        if value.done():
            _consume_future_exception(value)
        else:
            try:
                value.add_done_callback(_consume_future_exception)
            except BaseException:  # noqa: BLE001, S110 - cleanup is best effort.
                pass
        return
    if inspect.isasyncgen(value) or not inspect.isawaitable(value):
        return
    try:
        iterator = value.__await__()
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
    except BaseException:  # noqa: BLE001, S110 - cleanup cannot change the Failure.
        pass


def _consume_future_exception(future: asyncio.Future[Any]) -> None:
    try:
        future.exception()
    except BaseException:  # noqa: BLE001, S110 - cleanup cannot change the Failure.
        pass


def _consume_callback_completion(task: asyncio.Task[_CallbackCompletion]) -> None:
    try:
        task.result()
    except BaseException:  # noqa: BLE001, S110 - abandoned work is unobservable.
        pass


async def _sleep_milliseconds(
    delay_ms: int,
    cancellation: _CancellationSource,
) -> bool:
    remaining = delay_ms
    if remaining == 0:
        await asyncio.sleep(0)
        return not cancellation.cancelled
    while remaining > _MAX_HOST_TIMER_DELAY_MS:
        try:
            await asyncio.wait_for(
                cancellation.wait(),
                timeout=_MAX_HOST_TIMER_DELAY_MS / 1_000,
            )
        except TimeoutError:
            pass
        else:
            return False
        remaining -= _MAX_HOST_TIMER_DELAY_MS
    try:
        await asyncio.wait_for(cancellation.wait(), timeout=remaining / 1_000)
    except TimeoutError:
        return not cancellation.cancelled
    return False


@dataclass(frozen=True, slots=True)
class _Deadline:
    origin_ns: int
    duration_ms: int

    def due(self, now_ns: int | None = None) -> bool:
        current = time.monotonic_ns() if now_ns is None else now_ns
        return current - self.origin_ns >= self.duration_ms * 1_000_000

    def remaining_ms(self, now_ns: int | None = None) -> int:
        current = time.monotonic_ns() if now_ns is None else now_ns
        remaining_ns = self.duration_ms * 1_000_000 - (current - self.origin_ns)
        if remaining_ns <= 0:
            return 0
        return (remaining_ns + 999_999) // 1_000_000


async def _watch_run_deadline(
    cancellation: _CancellationSource,
    deadline: _Deadline,
    publisher: _EventPublisher,
) -> None:
    while not cancellation.cancelled:
        remaining = deadline.remaining_ms()
        if remaining == 0:
            if cancellation.cancel("deadline_exceeded", deadline=True):
                publisher.publish_run_cancellation("deadline_exceeded", True)
            return
        if not await _sleep_milliseconds(remaining, cancellation):
            return


@dataclass(frozen=True, slots=True)
class _Intent:
    kind: Literal["emit", "end"]
    action: Action | None
    value: object
    present: bool


@dataclass(frozen=True, slots=True)
class _SerialOutcome:
    terminals: tuple[Terminal, ...]
    stats: RunStats
    failure: Failure | None = None
    suppressed: tuple[Failure, ...] = ()
    cancellation: CancellationInfo | None = None
    abandonment: Failure | CancellationInfo | None = None


@dataclass(frozen=True, slots=True)
class _FailurePacket:
    primary: Failure
    suppressed: tuple[Failure, ...]
    input: object


class _RunFailure(Exception):
    def __init__(self, packet: _FailurePacket) -> None:
        super().__init__(packet.primary.message)
        self.packet = packet


class _ScopeFailure(Exception):
    def __init__(self, packet: _FailurePacket) -> None:
        super().__init__(packet.primary.message)
        self.packet = packet


class _RunCancelled(Exception):
    def __init__(self, suppressed: tuple[Failure, ...] = ()) -> None:
        super().__init__("Caskada run cancelled")
        self.suppressed = suppressed


class _RunAbandoned(Exception):
    def __init__(
        self,
        cause: Failure | CancellationInfo,
        suppressed: tuple[Failure, ...] = (),
    ) -> None:
        super().__init__("Caskada run abandoned")
        self.cause = cause
        self.suppressed = suppressed


def _is_recoverable_failure(failure: Failure) -> bool:
    return failure.kind in {
        "handler",
        "handler_timeout",
        "node_recovery",
        "flow_combine",
        "flow_recovery",
    }


def _replace_packet(packet: _FailurePacket, failure: Failure) -> _FailurePacket:
    return _FailurePacket(failure, packet.suppressed, packet.input)


@dataclass(slots=True)
class _Activation:
    element_id: int
    input: object
    activation_id: int
    parent_activation_id: int


@dataclass(frozen=True, slots=True)
class _NodeSettlement:
    intents: tuple[_Intent, ...]
    attempt: int | None
    previous: Failure | None
    suppressed: tuple[Failure, ...]


@dataclass(frozen=True, slots=True)
class _CallbackCompletion:
    result: object
    error: BaseException | None
    settled_ns: int


@dataclass(slots=True)
class _RuntimeScope:
    scope_id: int
    definition: _CompiledScope
    owner_activation_id: int
    owner_parent_activation_id: int | None
    incoming_input: object
    parent: _RuntimeScope | None
    owner_placement: _CompiledPlacement
    entry_activation_id: int
    queue: deque[_Activation]
    terminals: list[Terminal]
    depth: int
    direct_activations: int
    cancellation: _CancellationSource
    combined: bool = False
    finished: bool = False
    finished_terminal_sequences: tuple[int, ...] | None = None


class _RuntimeContext:
    __slots__ = (
        "_activation_id",
        "_attempt",
        "_cancellation",
        "_input",
        "_intent_reserver",
        "_intents",
        "_live",
        "_parent_activation_id",
        "_phase",
        "_remaining_ms",
        "_reporter",
        "_run_id",
        "_scope_id",
        "_state",
    )

    def __init__(
        self,
        state: _StateCarrier,
        input: object,
        *,
        scope_id: int,
        activation_id: int,
        parent_activation_id: int | None,
        attempt: int | None,
        phase: Phase,
        cancellation: _CancellationSource,
        run_id: str,
        remaining_ms: Callable[[], int | None] | None = None,
        intent_reserver: Callable[[int], None] | None = None,
        reporter: Callable[[_RuntimeContext, object, object, bool], None] | None = None,
    ) -> None:
        self._state = state
        self._input = input
        self._scope_id = scope_id
        self._activation_id = activation_id
        self._parent_activation_id = parent_activation_id
        self._attempt = attempt
        self._phase = phase
        self._cancellation = cancellation
        self._run_id = run_id
        self._remaining_ms = remaining_ms
        self._intent_reserver = intent_reserver
        self._reporter = reporter
        self._intents: list[_Intent] = []
        self._live = True

    @property
    def state(self) -> _StateCarrier:
        self._require_live()
        return self._state

    @property
    def input(self) -> object:
        self._require_live()
        return self._input

    @property
    def run_id(self) -> str:
        self._require_live()
        return self._run_id

    @property
    def attempt(self) -> int | None:
        self._require_live()
        return self._attempt

    @property
    def phase(self) -> Phase:
        self._require_live()
        return self._phase

    @property
    def cancellation(self) -> _CancellationSource:
        self._require_live()
        return self._cancellation

    def remaining_ms(self) -> int | None:
        self._require_live()
        return None if self._remaining_ms is None else self._remaining_ms()

    @property
    def scope_id(self) -> int:
        self._require_live()
        return self._scope_id

    @property
    def activation_id(self) -> int:
        self._require_live()
        return self._activation_id

    @property
    def parent_activation_id(self) -> int | None:
        self._require_live()
        return self._parent_activation_id

    def emit(self, *args: object, **kwargs: object) -> None:
        self._require_live()
        if any(key != "input" for key in kwargs) or len(kwargs) > 1:
            raise _SemanticMisuse(
                "invalid_control_arguments", "emit() received invalid arguments"
            )
        input = kwargs.get("input", _MISSING)
        if len(args) == 0:
            action = None
            value = self._input if input is _MISSING else input
        elif len(args) == 1:
            action = _require_runtime_action(args[0])
            value = self._input if input is _MISSING else input
        elif len(args) == 2 and input is _MISSING:
            action = _require_runtime_action(args[0])
            value = args[1]
        else:
            raise _SemanticMisuse(
                "invalid_control_arguments", "emit() received invalid arguments"
            )
        self._append_intent(_Intent("emit", action, value, True))

    def end(self, *args: object, **kwargs: object) -> None:
        self._require_live()
        if any(key != "output" for key in kwargs) or len(kwargs) > 1:
            raise _SemanticMisuse(
                "invalid_control_arguments", "end() received invalid arguments"
            )
        if len(args) == 0:
            output = kwargs.get("output", _MISSING)
        elif len(args) == 1 and not kwargs:
            output = args[0]
        else:
            raise _SemanticMisuse(
                "invalid_control_arguments", "end() received invalid arguments"
            )
        present = output is not _MISSING
        self._append_intent(
            _Intent("end", None, None if not present else output, present)
        )

    def report(self, *args: object, **kwargs: object) -> None:
        self._require_live()
        if any(key != "data" for key in kwargs) or len(kwargs) > 1:
            raise _SemanticMisuse(
                "invalid_control_arguments", "report() received invalid arguments"
            )
        if len(args) == 1:
            name = args[0]
            data = kwargs.get("data", _MISSING)
        elif len(args) == 2 and not kwargs:
            name, data = args
        else:
            raise _SemanticMisuse(
                "invalid_control_arguments", "report() received invalid arguments"
            )
        if self._reporter is None:
            raise RuntimeError("Context report capability is unavailable")
        self._reporter(
            self,
            name,
            None if data is _MISSING else data,
            data is not _MISSING,
        )

    def _append_intent(self, intent: _Intent) -> None:
        if self._intent_reserver is not None:
            self._intent_reserver(len(self._intents) + 1)
        self._intents.append(intent)

    def _close(self) -> tuple[_Intent, ...]:
        self._live = False
        return tuple(self._intents)

    def _abandon(self) -> None:
        self._live = False
        self._intents.clear()

    def _require_live(self) -> None:
        if not self._live:
            raise RuntimeError("Context is closed")


def _require_runtime_action(value: object) -> str:
    if type(value) is not str or not value:
        raise _SemanticMisuse("invalid_action", "action must be a nonempty string")
    return value


class _RuntimeKernel:
    def __init__(
        self,
        snapshot: _CompiledSnapshot,
        state: _StateCarrier,
        started_ns: int,
        cancellation: _CancellationSource,
        run_id: str,
        options: RunOptions,
        run_deadline: _Deadline | None,
        publisher: _EventPublisher,
    ) -> None:
        self.snapshot = snapshot
        self.state = state
        self.started_ns = started_ns
        self.cancellation = cancellation
        self.run_id = run_id
        self.options = options
        self.run_deadline = run_deadline
        self.publisher = publisher
        self.placements = {
            placement.element_id: placement for placement in snapshot.placements
        }
        self.scopes = {scope.scope_definition_id: scope for scope in snapshot.scopes}
        self.next_activation_id = 2
        self.next_scope_id = 2
        self.next_terminal_sequence = 1
        self.next_failure_id = 1
        self.activations = 1
        self.attempts = 0
        self.retries_count = 0
        self.reports_count = 0
        self.transitions = 0
        self.scopes_created = 0
        self.ready_count = 0
        self.peak_ready = 0
        self.peak_callbacks = 0
        self.active_callbacks = 0
        self.effective_max_concurrency = (
            snapshot.auto_max_concurrency
            if options.max_concurrency is None
            else options.max_concurrency
        )
        self.callback_gate = _CallbackGate(
            self.effective_max_concurrency,
            cancellation,
        )
        self.terminal_ns: int | None = None
        self.failure_fence: _ProducedFailure | None = None
        self.recorded_failures: set[int] = set()
        self.run_fence_published = False
        self.cancellation_fence_published = False
        self.scope_fences_published: set[int] = set()
        self.attempt_fences_published: set[tuple[int, int, int]] = set()
        self.runtime_scopes: dict[int, _RuntimeScope] = {}

    def _scope_started_spec(self, scope: _RuntimeScope) -> _EventSpec:
        return (
            ScopeStartedEvent,
            ScopeStartedPayload(
                scope_id=scope.scope_id,
                parent_scope_id=None if scope.parent is None else scope.parent.scope_id,
                owner_activation_id=scope.owner_activation_id,
                entry_activation_id=scope.entry_activation_id,
                entry_element_id=scope.definition.entry_element_id,
                flow_element_id=scope.owner_placement.element_id,
                depth=scope.depth,
            ),
        )

    def _scope_finished_spec(
        self,
        scope: _RuntimeScope,
        status: Literal["completed", "failed", "cancelled", "abandoned"],
    ) -> _EventSpec:
        return (
            ScopeFinishedEvent,
            ScopeFinishedPayload(
                scope_id=scope.scope_id,
                status=status,
                terminal_sequences=(
                    scope.finished_terminal_sequences
                    if scope.finished_terminal_sequences is not None
                    else tuple(terminal.sequence for terminal in scope.terminals)
                ),
            ),
        )

    def _mark_scope_finished(
        self,
        scope: _RuntimeScope,
        status: Literal["completed", "failed", "cancelled", "abandoned"],
    ) -> _EventSpec | None:
        if scope.finished:
            return None
        scope.finished = True
        return self._scope_finished_spec(scope, status)

    @staticmethod
    def _capture_scope_finish_terminals(scope: _RuntimeScope) -> None:
        if scope.finished_terminal_sequences is None:
            scope.finished_terminal_sequences = tuple(
                terminal.sequence for terminal in scope.terminals
            )

    def _publish_terminal(
        self,
        root: _RuntimeScope,
        status: Literal["completed", "failed", "cancelled", "abandoned"],
    ) -> None:
        self.publisher.mark_terminal()
        scope_status: Literal["completed", "failed", "cancelled", "abandoned"] = status
        specs: list[_EventSpec] = []
        for scope in sorted(
            self.runtime_scopes.values(),
            key=lambda candidate: (-candidate.depth, candidate.scope_id),
        ):
            spec = self._mark_scope_finished(scope, scope_status)
            if spec is not None:
                specs.append(spec)
        specs.append((RunFinishedEvent, RunFinishedPayload(status)))
        self.publisher.publish_bundle(specs)

    def _publish_callback_started(
        self,
        scope: _RuntimeScope,
        activation_id: int,
        parent_activation_id: int | None,
        element_id: int,
        phase: Phase,
        attempt: int | None,
    ) -> None:
        self.publisher.publish(
            CallbackStartedEvent,
            CallbackStartedPayload(
                scope.scope_id,
                activation_id,
                parent_activation_id,
                element_id,
                phase,
                attempt,
            ),
        )

    def _failure_record_spec(self, failure: Failure) -> _EventSpec | None:
        if failure.failure_id in self.recorded_failures:
            return None
        self.recorded_failures.add(failure.failure_id)
        return FailureRecordedEvent, FailureRecordedPayload(failure)

    def _publish_callback_finished(
        self,
        *,
        scope_id: int,
        activation_id: int,
        phase: Phase,
        attempt: int | None,
        disposition: CallbackDisposition,
        failures: Sequence[Failure] = (),
    ) -> None:
        specs = [
            spec
            for failure in failures
            if (spec := self._failure_record_spec(failure)) is not None
        ]
        specs.append(
            (
                CallbackFinishedEvent,
                CallbackFinishedPayload(
                    scope_id,
                    activation_id,
                    phase,
                    attempt,
                    disposition,
                ),
            )
        )
        self.publisher.publish_bundle(specs)

    def _publish_failure_recorded(self, failure: Failure) -> None:
        spec = self._failure_record_spec(failure)
        if spec is not None:
            self.publisher.publish_bundle((spec,))

    def _publish_scope_failure_fence(
        self,
        scope: _RuntimeScope,
        failure: Failure,
    ) -> None:
        if scope.scope_id in self.scope_fences_published:
            return
        self.scope_fences_published.add(scope.scope_id)
        specs: list[_EventSpec] = []
        record = self._failure_record_spec(failure)
        if record is not None:
            specs.append(record)
        specs.extend(
            (
                (
                    FailureFencedEvent,
                    FailureFencedPayload(ScopeFenceTarget(scope.scope_id), failure),
                ),
                (
                    CancellationFencedEvent,
                    CancellationFencedPayload(
                        ScopeFenceTarget(scope.scope_id),
                        "scope_failed",
                        False,
                    ),
                ),
            )
        )
        self.publisher.publish_bundle(specs)

    def _publish_run_failure_fence(self, failure: Failure) -> None:
        if self.run_fence_published:
            return
        self.run_fence_published = True
        self.cancellation_fence_published = True
        self.failure_fence = self.failure_fence or _ProducedFailure(failure)
        self.cancellation.cancel(_FailureFence(self.failure_fence))
        self.publisher.mark_run_cancellation_published()
        specs: list[_EventSpec] = []
        record = self._failure_record_spec(failure)
        if record is not None:
            specs.append(record)
        specs.extend(
            (
                (
                    FailureFencedEvent,
                    FailureFencedPayload(RunFenceTarget(), failure),
                ),
                (
                    CancellationFencedEvent,
                    CancellationFencedPayload(
                        RunFenceTarget(),
                        "run_failed",
                        False,
                    ),
                ),
            )
        )
        self.publisher.publish_bundle(specs)

    def _publish_run_cancellation_if_needed(self) -> None:
        if not self.cancellation.cancelled or self.cancellation_fence_published:
            return
        self.cancellation_fence_published = True
        self.publisher.publish_run_cancellation(
            self.cancellation.reason,
            self.cancellation.deadline,
        )

    def _publish_attempt_timeout(
        self,
        context: _RuntimeContext,
        failure: Failure,
    ) -> None:
        target_key = (
            context._scope_id,
            context._activation_id,
            cast(int, context._attempt),
        )
        if target_key in self.attempt_fences_published:
            return
        self.attempt_fences_published.add(target_key)
        spec = self._failure_record_spec(failure)
        specs: list[_EventSpec] = [] if spec is None else [spec]
        specs.append(
            (
                CancellationFencedEvent,
                CancellationFencedPayload(
                    AttemptFenceTarget(
                        context._scope_id,
                        context._activation_id,
                        target_key[2],
                    ),
                    "attempt_timeout",
                    False,
                ),
            )
        )
        self.publisher.publish_bundle(specs)

    async def run(self) -> _SerialOutcome:
        root_definition = self.scopes[1]
        root_placement = self.placements[1]
        root = self._new_scope(
            root_definition,
            owner_activation_id=1,
            owner_parent_activation_id=None,
            incoming_input=None,
            parent=None,
            owner_placement=root_placement,
        )
        result: _SerialOutcome
        status: Literal["completed", "failed", "cancelled", "abandoned"]
        try:
            self._checkpoint()
            terminals = await self._run_scopes(root)
            self._checkpoint()
        except _RunAbandoned as abandoned:
            result = _SerialOutcome(
                tuple(root.terminals),
                self._stats(),
                suppressed=abandoned.suppressed,
                abandonment=abandoned.cause,
            )
            status = "abandoned"
        except _RunCancelled as cancelled:
            self._publish_run_cancellation_if_needed()
            result = _SerialOutcome(
                tuple(root.terminals),
                self._stats(),
                suppressed=cancelled.suppressed,
                cancellation=CancellationInfo(
                    reason=self.cancellation.reason,
                    deadline=self.cancellation.deadline,
                ),
            )
            status = "cancelled"
        except _RunFailure as propagated:
            self._publish_run_failure_fence(propagated.packet.primary)
            result = _SerialOutcome(
                tuple(root.terminals),
                self._stats(),
                propagated.packet.primary,
                propagated.packet.suppressed,
            )
            status = "failed"
        except _ProducedFailure as produced:
            self._publish_run_failure_fence(produced.failure)
            result = _SerialOutcome(
                tuple(root.terminals),
                self._stats(),
                produced.failure,
                produced.suppressed,
            )
            status = "failed"
        except BaseException:  # noqa: BLE001 - a started run always settles as data.
            failure = self._new_failure(
                "internal",
                scope_id=1,
                activation_id=None,
                element_id=None,
                attempt=None,
                detail=InternalDetail("scheduler_invariant"),
            )
            self._publish_run_failure_fence(failure)
            result = _SerialOutcome(tuple(root.terminals), self._stats(), failure)
            status = "failed"
        else:
            result = _SerialOutcome(terminals, self._stats())
            status = "completed"
        self._publish_terminal(root, status)
        return result

    def _checkpoint(self, suppressed: tuple[Failure, ...] = ()) -> None:
        self._check_cancelled(suppressed)

    def _commit_deadline_if_due(self) -> None:
        if (
            not self.cancellation.cancelled
            and self.run_deadline is not None
            and self.run_deadline.due()
        ):
            self.cancellation.cancel("deadline_exceeded", deadline=True)

    def _check_cancelled(self, suppressed: tuple[Failure, ...] = ()) -> None:
        if self.failure_fence is not None:
            raise self.failure_fence
        self._commit_deadline_if_due()
        if self.cancellation.cancelled:
            self._publish_run_cancellation_if_needed()
            raise _RunCancelled(suppressed)

    def _check_scope_cancelled(
        self,
        scope: _RuntimeScope,
        suppressed: tuple[Failure, ...] = (),
    ) -> None:
        self._check_cancelled(suppressed)
        if not scope.cancellation.cancelled:
            return
        reason = scope.cancellation.reason
        if isinstance(reason, _FailureFence):
            raise reason.produced
        raise _RunCancelled(suppressed)

    async def _acquire_callback(
        self,
        scope: _RuntimeScope,
        *,
        ready_callback: bool,
    ) -> None:
        self._check_scope_cancelled(scope)
        try:
            await self.callback_gate.acquire(
                ready_callback=ready_callback,
                cancellation=scope.cancellation,
                scope_id=scope.scope_id,
            )
        except asyncio.CancelledError:
            self._check_scope_cancelled(scope)
            raise
        self.active_callbacks += 1
        self.peak_callbacks = max(self.peak_callbacks, self.active_callbacks)

    async def _acquire_callback_source(
        self,
        cancellation: _CancellationSource,
        *,
        ready_callback: bool,
    ) -> None:
        self._check_cancelled()
        try:
            await self.callback_gate.acquire(
                ready_callback=ready_callback,
                cancellation=cancellation,
            )
        except asyncio.CancelledError:
            self._check_cancelled()
            reason = cancellation.reason
            if isinstance(reason, _FailureFence):
                raise reason.produced
            raise
        self.active_callbacks += 1
        self.peak_callbacks = max(self.peak_callbacks, self.active_callbacks)

    def _release_callback(self) -> None:
        if self.active_callbacks <= 0:
            raise RuntimeError("callback accounting lost its owner")
        self.active_callbacks -= 1
        self.callback_gate.release()

    async def _run_scopes(self, root: _RuntimeScope) -> NonEmptyTerminals:
        if all(scope.concurrency == 1 for scope in self.snapshot.scopes):
            return await self._run_scopes_serial(root)
        await self._run_scope_concurrent(root)
        if not root.terminals:
            raise RuntimeError("a completed root Flow must have a terminal")
        return cast(NonEmptyTerminals, tuple(root.terminals))

    async def _run_scope_concurrent(self, scope: _RuntimeScope) -> None:
        active: dict[asyncio.Task[None], tuple[int, _Activation]] = {}
        task_sequence = 0
        failure: tuple[_FailurePacket, int | None, bool] | None = None

        while scope.queue or active:
            self._check_scope_cancelled(scope)
            while scope.queue and len(active) < scope.definition.concurrency:
                activation = scope.queue.popleft()
                self.ready_count -= 1
                task = asyncio.create_task(
                    self._run_activation_concurrent(scope, activation)
                )
                active[task] = (task_sequence, activation)
                task_sequence += 1
                # One admission turn per live scope approximates the normative
                # round-robin queues without recursive graph execution.
                await asyncio.sleep(0)

            if not active:
                break
            done, _pending = await asyncio.wait(
                active,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in sorted(done, key=lambda item: active[item][0]):
                _sequence, activation = active.pop(task)
                try:
                    task.result()
                except _ScopeFailure as propagated:
                    if failure is None:
                        failure = (propagated.packet, activation.activation_id, True)
                except _ProducedFailure as produced:
                    if failure is None:
                        failure = (
                            _FailurePacket(
                                produced.failure,
                                produced.suppressed,
                                activation.input,
                            ),
                            activation.activation_id,
                            _is_recoverable_failure(produced.failure),
                        )
                if failure is not None:
                    break

            if failure is None:
                continue

            packet, failing_activation_id, recoverable = failure
            fence = _ProducedFailure(packet.primary, packet.suppressed)
            scope.cancellation.cancel(_FailureFence(fence))
            self._publish_scope_failure_fence(scope, packet.primary)
            self._discard_scope_ready(scope)
            if active:
                drained = await asyncio.gather(*active, return_exceptions=True)
                packet = self._merge_drained_failures(packet, drained)
                active.clear()
            if not recoverable:
                raise _ProducedFailure(packet.primary, packet.suppressed)
            recovered, packet = await self._recover_scope(
                scope,
                packet,
                settled_before_fence=tuple(scope.terminals),
                result=None,
                failing_activation_id=failing_activation_id,
            )
            if recovered is not None:
                self._capture_scope_finish_terminals(scope)
                scope.terminals = recovered
                scope.cancellation.close()
                return
            scope.cancellation.close()
            if scope.parent is None:
                raise _RunFailure(packet)
            finish = self._mark_scope_finished(scope, "failed")
            if finish is not None:
                self.publisher.publish_bundle((finish,))
            raise _ScopeFailure(packet)

        if not scope.combined:
            scope.combined = True
            if scope.definition.combine is not None:
                result_view = self._scope_result(scope)
                try:
                    intents = await self._invoke_combine(scope, result_view)
                except _ProducedFailure as produced:
                    if produced.failure.kind != "flow_combine":
                        raise
                    packet = _FailurePacket(
                        produced.failure,
                        produced.suppressed,
                        scope.incoming_input,
                    )
                    recovered, packet = await self._recover_scope(
                        scope,
                        packet,
                        settled_before_fence=tuple(scope.terminals),
                        result=result_view,
                        failing_activation_id=None,
                    )
                    if recovered is None:
                        scope.cancellation.close()
                        if scope.parent is None:
                            raise _RunFailure(packet)
                        raise _ScopeFailure(packet)
                    self._capture_scope_finish_terminals(scope)
                    scope.terminals = recovered
                else:
                    if intents:
                        self._capture_scope_finish_terminals(scope)
                        scope.terminals = self._boundary_terminals(scope, intents)
        scope.cancellation.close()

    async def _run_activation_concurrent(
        self,
        scope: _RuntimeScope,
        activation: _Activation,
    ) -> None:
        placement = self.placements[activation.element_id]
        if placement.kind == "node":
            settlement = await self._run_node(scope, placement, activation)
            self._route(
                scope,
                placement,
                activation.activation_id,
                settlement.intents,
                attempt=settlement.attempt,
                previous=settlement.previous,
                suppressed=settlement.suppressed,
                callback_phase=(
                    "handle" if settlement.attempt is not None else "node_recover"
                ),
            )
            return
        if placement.owned_scope_definition_id is None:
            raise RuntimeError("compiled Flow placement has no owned scope")
        child = self._new_scope(
            self.scopes[placement.owned_scope_definition_id],
            owner_activation_id=activation.activation_id,
            owner_parent_activation_id=activation.parent_activation_id,
            incoming_input=activation.input,
            parent=scope,
            owner_placement=placement,
        )
        await self._run_scope_concurrent(child)
        self._forward_child(child)

    def _merge_drained_failures(
        self,
        packet: _FailurePacket,
        drained: Sequence[object],
    ) -> _FailurePacket:
        suppressed = list(packet.suppressed)
        seen = {packet.primary.failure_id, *(item.failure_id for item in suppressed)}
        for item in drained:
            failures: tuple[Failure, ...] = ()
            if isinstance(item, _ProducedFailure):
                failures = (item.failure, *item.suppressed)
            elif isinstance(item, _ScopeFailure):
                failures = (item.packet.primary, *item.packet.suppressed)
            for candidate in failures:
                if candidate.failure_id not in seen:
                    seen.add(candidate.failure_id)
                    suppressed.append(candidate)
        return _FailurePacket(packet.primary, tuple(suppressed), packet.input)

    async def _run_scopes_serial(self, root: _RuntimeScope) -> NonEmptyTerminals:
        stack = [root]

        while stack:
            self._check_cancelled()
            scope = stack[-1]
            if scope.queue:
                activation = scope.queue.popleft()
                self.ready_count -= 1
                placement = self.placements[activation.element_id]
                if placement.kind == "node":
                    try:
                        settlement = await self._run_node(scope, placement, activation)
                        self._route(
                            scope,
                            placement,
                            activation.activation_id,
                            settlement.intents,
                            attempt=settlement.attempt,
                            previous=settlement.previous,
                            suppressed=settlement.suppressed,
                            callback_phase=(
                                "handle"
                                if settlement.attempt is not None
                                else "node_recover"
                            ),
                        )
                    except _ProducedFailure as produced:
                        if not _is_recoverable_failure(produced.failure):
                            raise
                        completed = await self._settle_scope_failure(
                            stack,
                            scope,
                            _FailurePacket(
                                produced.failure,
                                produced.suppressed,
                                activation.input,
                            ),
                            failing_activation_id=activation.activation_id,
                            result=None,
                        )
                        if completed is not None:
                            return completed
                    continue

                if placement.owned_scope_definition_id is None:
                    raise RuntimeError("compiled Flow placement has no owned scope")
                child_definition = self.scopes[placement.owned_scope_definition_id]
                stack.append(
                    self._new_scope(
                        child_definition,
                        owner_activation_id=activation.activation_id,
                        owner_parent_activation_id=activation.parent_activation_id,
                        incoming_input=activation.input,
                        parent=scope,
                        owner_placement=placement,
                    )
                )
                continue

            if not scope.combined:
                scope.combined = True
                if scope.definition.combine is not None:
                    result_view = self._scope_result(scope)
                    try:
                        intents = await self._invoke_combine(scope, result_view)
                    except _ProducedFailure as produced:
                        if produced.failure.kind != "flow_combine":
                            raise
                        completed = await self._settle_scope_failure(
                            stack,
                            scope,
                            _FailurePacket(
                                produced.failure,
                                produced.suppressed,
                                scope.incoming_input,
                            ),
                            failing_activation_id=None,
                            result=result_view,
                        )
                        if completed is not None:
                            return completed
                        continue
                    if intents:
                        self._capture_scope_finish_terminals(scope)
                        scope.terminals = self._boundary_terminals(scope, intents)

            completed_scope = stack.pop()
            if completed_scope.parent is None:
                if not completed_scope.terminals:
                    raise RuntimeError("a completed root Flow must have a terminal")
                terminals = cast(
                    NonEmptyTerminals,
                    tuple(completed_scope.terminals),
                )
                return terminals
            self._forward_child(completed_scope)

        raise RuntimeError("scheduler lost its root scope")

    async def _settle_scope_failure(
        self,
        stack: list[_RuntimeScope],
        scope: _RuntimeScope,
        packet: _FailurePacket,
        *,
        failing_activation_id: int | None,
        result: ScopeResult | None,
    ) -> NonEmptyTerminals | None:
        current_scope = scope
        current_failing_activation_id = failing_activation_id
        current_result = result

        while True:
            self._check_cancelled(
                (packet.primary, *packet.suppressed),
            )
            settled_before_fence = tuple(current_scope.terminals)
            current_scope.cancellation.cancel(
                _FailureFence(_ProducedFailure(packet.primary, packet.suppressed))
            )
            self._publish_scope_failure_fence(current_scope, packet.primary)
            self._discard_scope_ready(current_scope)
            recovered, packet = await self._recover_scope(
                current_scope,
                packet,
                settled_before_fence=settled_before_fence,
                result=current_result,
                failing_activation_id=current_failing_activation_id,
            )
            if recovered is not None:
                self._capture_scope_finish_terminals(current_scope)
                current_scope.terminals = recovered
                completed = stack.pop()
                if completed is not current_scope:
                    raise RuntimeError("scope failure stack ownership changed")
                completed.cancellation.close()
                if completed.parent is None:
                    if not completed.terminals:
                        raise RuntimeError("a recovered root Flow must have a terminal")
                    return cast(NonEmptyTerminals, tuple(completed.terminals))
                self._forward_child(completed)
                return None

            completed = stack.pop()
            if completed is not current_scope:
                raise RuntimeError("scope failure stack ownership changed")
            completed.cancellation.close()
            if completed.parent is None:
                raise _RunFailure(packet)
            finish = self._mark_scope_finished(completed, "failed")
            if finish is not None:
                self.publisher.publish_bundle((finish,))
            current_scope = completed.parent
            current_failing_activation_id = completed.owner_activation_id
            current_result = None

    async def _recover_scope(
        self,
        scope: _RuntimeScope,
        packet: _FailurePacket,
        *,
        settled_before_fence: tuple[Terminal, ...],
        result: ScopeResult | None,
        failing_activation_id: int | None,
    ) -> tuple[list[Terminal] | None, _FailurePacket]:
        if scope.definition.recover is None:
            self._check_cancelled((packet.primary, *packet.suppressed))
            return None, packet
        recovery_source = (
            self.cancellation if scope.parent is None else scope.parent.cancellation
        )
        await self._acquire_callback_source(
            recovery_source,
            ready_callback=True,
        )
        try:
            return await self._recover_scope_admitted(
                scope,
                packet,
                settled_before_fence=settled_before_fence,
                result=result,
                failing_activation_id=failing_activation_id,
            )
        finally:
            self._release_callback()

    async def _recover_scope_admitted(
        self,
        scope: _RuntimeScope,
        packet: _FailurePacket,
        *,
        settled_before_fence: tuple[Terminal, ...],
        result: ScopeResult | None,
        failing_activation_id: int | None,
    ) -> tuple[list[Terminal] | None, _FailurePacket]:
        callback = scope.definition.recover
        self._check_cancelled((packet.primary, *packet.suppressed))
        if callback is None:
            raise RuntimeError("admitted Flow recovery has no callback")

        callback_source = _CancellationSource(
            self.cancellation if scope.parent is None else scope.parent.cancellation
        )
        context = _RuntimeContext(
            self.state,
            packet.input,
            scope_id=scope.scope_id,
            activation_id=scope.owner_activation_id,
            parent_activation_id=scope.owner_parent_activation_id,
            attempt=None,
            phase="flow_recover",
            cancellation=callback_source,
            run_id=self.run_id,
            remaining_ms=lambda: self._remaining_ms(callback_source, None),
            intent_reserver=self._make_intent_reserver(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                previous=packet.primary,
                suppressed=packet.suppressed,
                callback_source=callback_source,
            ),
            reporter=self._make_reporter(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                previous=packet.primary,
                suppressed=packet.suppressed,
                callback_source=callback_source,
            ),
        )
        failure_view = ScopeFailure(
            primary=packet.primary,
            suppressed=packet.suppressed,
            settled_before_fence=settled_before_fence,
            result=result,
            failing_activation_id=failing_activation_id,
        )

        def classify(error: BaseException, selected: Failure | None) -> Failure:
            causal = packet.primary if selected is None else selected
            if isinstance(error, _SemanticMisuse):
                return self._new_failure(
                    "invalid_combination",
                    scope_id=scope.scope_id,
                    activation_id=scope.owner_activation_id,
                    element_id=scope.owner_placement.element_id,
                    attempt=None,
                    detail=InvalidCombinationDetail(error.reason),
                    previous=causal,
                )
            return self._new_failure(
                "flow_recovery",
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                cause=error,
                previous=causal,
            )

        self._publish_callback_started(
            scope,
            scope.owner_activation_id,
            scope.owner_parent_activation_id,
            scope.owner_placement.element_id,
            "flow_recover",
            None,
        )
        try:
            try:
                callback_result = await self._await_lifecycle_callback(
                    context,
                    callback_source,
                    lambda: callback(context, failure_view),
                    classify,
                    active=(packet.primary, *packet.suppressed),
                )
            except _ProducedFailure as produced:
                self._publish_callback_finished(
                    scope_id=scope.scope_id,
                    activation_id=scope.owner_activation_id,
                    phase="flow_recover",
                    attempt=None,
                    disposition=FailureDisposition("failure", produced.failure),
                    failures=(produced.failure, *produced.suppressed),
                )
                replaced = _FailurePacket(
                    produced.failure,
                    produced.suppressed,
                    packet.input,
                )
                if not _is_recoverable_failure(produced.failure):
                    raise _RunFailure(replaced) from None
                return None, replaced
            except (_RunCancelled, _RunAbandoned):
                self._publish_callback_finished(
                    scope_id=scope.scope_id,
                    activation_id=scope.owner_activation_id,
                    phase="flow_recover",
                    attempt=None,
                    disposition=DiscardedDisposition("discarded"),
                )
                raise
        finally:
            intents = context._close()

        self._check_cancelled((packet.primary, *packet.suppressed))
        if callback_result is not None:
            failure = self._new_failure(
                "invalid_combination",
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                detail=InvalidCombinationDetail("wrong_return_type"),
                previous=packet.primary,
            )
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_recover",
                attempt=None,
                disposition=FailureDisposition("failure", failure),
                failures=(failure,),
            )
            raise _RunFailure(_replace_packet(packet, failure))
        if not intents:
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_recover",
                attempt=None,
                disposition=CallbackOutcomeDisposition("outcome", "unhandled"),
            )
            return None, packet
        try:
            terminals = self._boundary_terminals(
                scope,
                intents,
                previous=packet.primary,
                callback_phase="flow_recover",
            )
        except _ProducedFailure as produced:
            raise _RunFailure(_replace_packet(packet, produced.failure)) from None
        return terminals, packet

    def _discard_scope_ready(self, scope: _RuntimeScope) -> None:
        discarded = len(scope.queue)
        scope.queue.clear()
        self.ready_count -= discarded

    def _scope_result(self, scope: _RuntimeScope) -> ScopeResult:
        return ScopeResult(
            terminals=cast(NonEmptyTerminals, tuple(scope.terminals)),
            outputs=tuple(
                terminal.output for terminal in scope.terminals if terminal.has_output
            ),
        )

    def _remaining_ms(
        self,
        callback_source: _CancellationSource,
        attempt_deadline: _Deadline | None,
    ) -> int | None:
        now_ns = time.monotonic_ns()
        remaining: list[int] = []
        if not self.cancellation.cancelled and self.run_deadline is not None:
            remaining.append(self.run_deadline.remaining_ms(now_ns))
        if not callback_source.cancelled and attempt_deadline is not None:
            remaining.append(attempt_deadline.remaining_ms(now_ns))
        for source in (callback_source, self.cancellation):
            if source.cancelled and source.fenced_ns is not None:
                grace = _Deadline(source.fenced_ns, self.options.cancel_grace_ms)
                remaining.append(grace.remaining_ms(now_ns))
        return min(remaining) if remaining else None

    async def _capture_callback(
        self,
        callback: Callable[[], object],
    ) -> _CallbackCompletion:
        try:
            result = callback()
            if inspect.isawaitable(result):
                result = await result
            return _CallbackCompletion(result, None, time.monotonic_ns())
        except BaseException as error:  # noqa: BLE001 - lifecycle boundary is total.
            return _CallbackCompletion(None, error, time.monotonic_ns())

    async def _wait_until(self, deadline: _Deadline) -> None:
        while True:
            remaining = deadline.remaining_ms()
            if remaining == 0:
                return
            await asyncio.sleep(min(remaining, _MAX_HOST_TIMER_DELAY_MS) / 1_000)

    async def _await_lifecycle_callback(
        self,
        context: _RuntimeContext,
        callback_source: _CancellationSource,
        callback: Callable[[], object],
        classify: Callable[[BaseException, Failure | None], Failure],
        *,
        active: tuple[Failure, ...] = (),
        attempt_deadline: _Deadline | None = None,
        timeout_failure: Callable[[], Failure] | None = None,
    ) -> object:
        def failure_fence() -> _ProducedFailure | None:
            reason = callback_source.reason
            return reason.produced if isinstance(reason, _FailureFence) else None

        def fenced_produced(
            fence: _ProducedFailure,
            completion: _CallbackCompletion,
        ) -> _ProducedFailure:
            suppressed = list(fence.suppressed)
            if completion.error is not None and not isinstance(
                completion.error, asyncio.CancelledError
            ):
                suppressed.append(classify(completion.error, fence.failure))
            return _ProducedFailure(fence.failure, tuple(suppressed))

        self._check_cancelled(active)
        if attempt_deadline is not None and attempt_deadline.due():
            if timeout_failure is None:
                raise RuntimeError("attempt timeout has no Failure factory")
            failure = timeout_failure()
            callback_source.cancel("attempt_timeout")
            self._publish_attempt_timeout(context, failure)
            callback_source.close()
            context._close()
            raise _ProducedFailure(failure)

        callback_task = asyncio.create_task(self._capture_callback(callback))
        source_wait = asyncio.create_task(callback_source.wait())
        attempt_wait = (
            None
            if attempt_deadline is None
            else asyncio.create_task(self._wait_until(attempt_deadline))
        )
        waiters: set[asyncio.Task[Any]] = {callback_task, source_wait}
        if attempt_wait is not None:
            waiters.add(attempt_wait)
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
            if (
                attempt_wait is not None
                and attempt_wait.done()
                and not callback_task.done()
            ):
                if timeout_failure is None:
                    raise RuntimeError("attempt timeout has no Failure factory")
                callback_source.cancel("attempt_timeout")

            if callback_task.done():
                completion = callback_task.result()
                attempt_due_ns = (
                    None
                    if attempt_deadline is None
                    else attempt_deadline.origin_ns
                    + attempt_deadline.duration_ms * 1_000_000
                )
                attempt_won = (
                    attempt_due_ns is not None
                    and completion.settled_ns >= attempt_due_ns
                    and not self.cancellation.cancelled
                )
                if attempt_won:
                    callback_source.cancel("attempt_timeout")
                elif not self.cancellation.cancelled:
                    fence = failure_fence()
                    if fence is not None:
                        raise fenced_produced(fence, completion)
                    if completion.error is not None:
                        raise _ProducedFailure(
                            classify(completion.error, None),
                            active[1:] if active else (),
                        )
                    return completion.result

            local_timeout = (
                callback_source.cancelled
                and callback_source.reason == "attempt_timeout"
            )
            timeout_primary = (
                timeout_failure() if local_timeout and timeout_failure else None
            )
            if timeout_primary is not None:
                self._publish_attempt_timeout(context, timeout_primary)

            while not callback_task.done():
                grace_deadlines: list[_Deadline] = []
                if callback_source.cancelled and callback_source.fenced_ns is not None:
                    grace_deadlines.append(
                        _Deadline(
                            callback_source.fenced_ns,
                            self.options.cancel_grace_ms,
                        )
                    )
                if (
                    self.cancellation.cancelled
                    and self.cancellation.fenced_ns is not None
                ):
                    grace_deadlines.append(
                        _Deadline(
                            self.cancellation.fenced_ns,
                            self.options.cancel_grace_ms,
                        )
                    )
                if not grace_deadlines:
                    raise RuntimeError("signalled callback has no grace deadline")
                earliest = min(
                    grace_deadlines,
                    key=lambda deadline: (
                        deadline.origin_ns + deadline.duration_ms * 1_000_000
                    ),
                )
                grace_wait = asyncio.create_task(self._wait_until(earliest))
                run_wait = (
                    None
                    if self.cancellation.cancelled
                    else asyncio.create_task(self.cancellation.wait())
                )
                protected: set[asyncio.Task[Any]] = {callback_task, grace_wait}
                if run_wait is not None:
                    protected.add(run_wait)
                await asyncio.wait(protected, return_when=asyncio.FIRST_COMPLETED)
                if run_wait is not None and not run_wait.done():
                    run_wait.cancel()
                if not grace_wait.done():
                    grace_wait.cancel()
                if callback_task.done():
                    break
                if earliest.due():
                    context._abandon()
                    callback_task.add_done_callback(_consume_callback_completion)
                    if self.failure_fence is not None:
                        raise _RunAbandoned(
                            self.failure_fence.failure,
                            self.failure_fence.suppressed,
                        )
                    if self.cancellation.cancelled:
                        cancellation = CancellationInfo(
                            reason=self.cancellation.reason,
                            deadline=self.cancellation.deadline,
                        )
                        suppressed = (
                            (timeout_primary, *active[1:])
                            if timeout_primary is not None
                            else active
                        )
                        raise _RunAbandoned(cancellation, suppressed)
                    fence = failure_fence()
                    if fence is not None:
                        raise _RunAbandoned(
                            fence.failure,
                            fence.suppressed,
                        )
                    if timeout_primary is None:
                        raise RuntimeError("local grace expired without timeout")
                    raise _RunAbandoned(timeout_primary, active[1:])

            completion = callback_task.result()
            protected_sources = tuple(
                source
                for source in (callback_source, self.cancellation)
                if source.cancelled and source.fenced_ns is not None
            )
            grace_expired = any(
                completion.settled_ns - cast(int, source.fenced_ns)
                >= self.options.cancel_grace_ms * 1_000_000
                for source in protected_sources
            )
            if grace_expired:
                context._abandon()
                if self.failure_fence is not None:
                    raise _RunAbandoned(
                        self.failure_fence.failure,
                        self.failure_fence.suppressed,
                    )
                if self.cancellation.cancelled:
                    cancellation = CancellationInfo(
                        reason=self.cancellation.reason,
                        deadline=self.cancellation.deadline,
                    )
                    suppressed = (
                        (timeout_primary, *active[1:])
                        if timeout_primary is not None
                        else active
                    )
                    raise _RunAbandoned(cancellation, suppressed)
                fence = failure_fence()
                if fence is not None:
                    raise _RunAbandoned(fence.failure, fence.suppressed)
                if timeout_primary is None:
                    raise RuntimeError("expired grace has no controlling timeout")
                raise _RunAbandoned(timeout_primary, active[1:])
            if self.failure_fence is not None:
                raise fenced_produced(self.failure_fence, completion)
            if self.cancellation.cancelled:
                cancellation_suppressed = list(
                    (timeout_primary, *active[1:])
                    if timeout_primary is not None
                    else active
                )
                if completion.error is not None and not isinstance(
                    completion.error, asyncio.CancelledError
                ):
                    previous = timeout_primary or (active[0] if active else None)
                    cancellation_suppressed.append(classify(completion.error, previous))
                raise _RunCancelled(tuple(cancellation_suppressed))

            fence = failure_fence()
            if fence is not None:
                raise fenced_produced(fence, completion)

            if timeout_primary is None:
                raise RuntimeError("attempt signal has no timeout Failure")
            post_timeout: tuple[Failure, ...] = ()
            if completion.error is not None and not isinstance(
                completion.error, asyncio.CancelledError
            ):
                post_timeout = (classify(completion.error, timeout_primary),)
            raise _ProducedFailure(
                timeout_primary,
                (*active[1:], *post_timeout),
            )
        finally:
            source_wait.cancel()
            if attempt_wait is not None:
                attempt_wait.cancel()
            callback_source.close()

    def _stats(self) -> RunStats:
        if self.terminal_ns is None:
            self.terminal_ns = time.monotonic_ns()
        duration_ms = min(
            MAX_SAFE_INTEGER,
            (self.terminal_ns - self.started_ns) // 1_000_000,
        )
        return RunStats(
            activations=self.activations,
            attempts=self.attempts,
            transitions=self.transitions,
            retries=self.retries_count,
            reports=self.reports_count,
            scopes=self.scopes_created,
            peak_ready=self.peak_ready,
            peak_callbacks=self.peak_callbacks,
            duration_ms=duration_ms,
        )

    def _new_failure(
        self,
        kind: FailureKind,
        *,
        scope_id: int,
        activation_id: int | None,
        element_id: int | None,
        attempt: int | None,
        cause: BaseException | None = None,
        detail: FailureDetail | None = None,
        previous: Failure | None = None,
    ) -> Failure:
        failure = Failure(
            failure_id=self.next_failure_id,
            kind=kind,
            message=_FAILURE_MESSAGES[kind],
            cause=cause,
            scope_id=scope_id,
            activation_id=activation_id,
            element_id=element_id,
            attempt=attempt,
            detail=detail,
            previous=previous,
        )
        self.next_failure_id += 1
        return failure

    def _make_intent_reserver(
        self,
        *,
        scope_id: int,
        activation_id: int,
        element_id: int,
        attempt: int | None,
        previous: Failure | None,
        suppressed: tuple[Failure, ...],
        callback_source: _CancellationSource,
    ) -> Callable[[int], None]:
        def reserve(buffered_count: int) -> None:
            if callback_source.cancelled:
                raise asyncio.CancelledError
            limit: LimitName | None = None
            if self.transitions + buffered_count > self.options.max_transitions:
                limit = "max_transitions"
            elif buffered_count > MAX_PORTABLE_COLLECTION_LENGTH:
                limit = "portable_collection"
            if limit is None:
                return
            produced = _ProducedFailure(
                self._new_failure(
                    "limit",
                    scope_id=scope_id,
                    activation_id=activation_id,
                    element_id=element_id,
                    attempt=attempt,
                    detail=LimitDetail(limit),
                    previous=previous,
                ),
                suppressed,
            )
            if self.failure_fence is None:
                self.failure_fence = produced
            produced = self.failure_fence
            callback_source.cancel(_FailureFence(produced))
            raise asyncio.CancelledError

        return reserve

    def _make_reporter(
        self,
        *,
        scope_id: int,
        activation_id: int,
        element_id: int,
        attempt: int | None,
        previous: Failure | None,
        suppressed: tuple[Failure, ...],
        callback_source: _CancellationSource,
        attempt_deadline: _Deadline | None = None,
        timeout_failure: Callable[[], Failure] | None = None,
    ) -> Callable[[_RuntimeContext, object, object, bool], None]:
        def report(
            context: _RuntimeContext,
            name: object,
            data: object,
            has_data: bool,
        ) -> None:
            if self.publisher.publishing:
                self.publisher.reject_reentrant_report()
                return
            self._commit_deadline_if_due()
            if self.failure_fence is not None:
                raise asyncio.CancelledError
            if self.cancellation.cancelled:
                self._publish_run_cancellation_if_needed()
                raise asyncio.CancelledError
            if callback_source.cancelled:
                raise asyncio.CancelledError
            if attempt_deadline is not None and attempt_deadline.due():
                if timeout_failure is None:
                    raise RuntimeError("attempt report checkpoint has no timeout")
                failure = timeout_failure()
                callback_source.cancel("attempt_timeout")
                self._publish_attempt_timeout(context, failure)
                raise asyncio.CancelledError
            if type(name) is not str or not name:
                raise _SemanticMisuse(
                    "report_name", "report name must be a nonempty string"
                )
            if self.reports_count >= self.options.max_reports:
                produced = _ProducedFailure(
                    self._new_failure(
                        "limit",
                        scope_id=scope_id,
                        activation_id=activation_id,
                        element_id=element_id,
                        attempt=attempt,
                        detail=LimitDetail("max_reports"),
                        previous=previous,
                    ),
                    suppressed,
                )
                self.failure_fence = self.failure_fence or produced
                self._publish_run_failure_fence(self.failure_fence.failure)
                callback_source.cancel(_FailureFence(self.failure_fence))
                raise asyncio.CancelledError
            self.reports_count += 1
            payload: ReportPayload
            if has_data:
                payload = ReportWithDataPayload(
                    scope_id,
                    activation_id,
                    name,
                    data,
                )
            else:
                payload = ReportWithoutDataPayload(
                    scope_id,
                    activation_id,
                    name,
                )
            self.publisher.publish(ReportEvent, payload)
            self._commit_deadline_if_due()
            if self.cancellation.cancelled:
                self._publish_run_cancellation_if_needed()
            if (
                not callback_source.cancelled
                and attempt_deadline is not None
                and attempt_deadline.due()
            ):
                if timeout_failure is None:
                    raise RuntimeError("attempt report checkpoint has no timeout")
                failure = timeout_failure()
                callback_source.cancel("attempt_timeout")
                self._publish_attempt_timeout(context, failure)
            if (
                self.failure_fence is not None
                or self.cancellation.cancelled
                or callback_source.cancelled
            ):
                raise asyncio.CancelledError

        return report

    def _new_scope(
        self,
        definition: _CompiledScope,
        *,
        owner_activation_id: int,
        owner_parent_activation_id: int | None,
        incoming_input: object,
        parent: _RuntimeScope | None,
        owner_placement: _CompiledPlacement,
    ) -> _RuntimeScope:
        if parent is None:
            scope_id = 1
            depth = 1
        else:
            if parent.depth + 1 > self.options.max_depth:
                raise _ProducedFailure(
                    self._new_failure(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("max_depth"),
                    )
                )
            if self.activations + 1 > self.options.max_activations:
                raise _ProducedFailure(
                    self._new_failure(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("max_activations"),
                    )
                )
            if self.ready_count + 1 > self.options.max_ready:
                raise _ProducedFailure(
                    self._new_failure(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("max_ready"),
                    )
                )
            if (
                self.next_scope_id > MAX_SAFE_INTEGER
                or self.next_activation_id > MAX_SAFE_INTEGER
            ):
                raise _ProducedFailure(
                    self._new_failure(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("safe_integer"),
                    )
                )
            scope_id = self.next_scope_id
            self.next_scope_id += 1
            depth = parent.depth + 1
        self.scopes_created += 1
        entry_activation_id = self._allocate_activation_id()
        entry = _Activation(
            definition.entry_element_id,
            incoming_input,
            entry_activation_id,
            owner_activation_id,
        )
        runtime_scope = _RuntimeScope(
            scope_id,
            definition,
            owner_activation_id,
            owner_parent_activation_id,
            incoming_input,
            parent,
            owner_placement,
            entry_activation_id,
            deque((entry,)),
            [],
            depth,
            1,
            _CancellationSource(
                self.cancellation if parent is None else parent.cancellation
            ),
        )
        self.ready_count += 1
        self.peak_ready = max(self.peak_ready, self.ready_count)
        self.runtime_scopes[scope_id] = runtime_scope
        if parent is not None:
            self.publisher.publish_bundle((self._scope_started_spec(runtime_scope),))
            self._check_scope_cancelled(parent)
        return runtime_scope

    async def _run_node(
        self,
        scope: _RuntimeScope,
        placement: _CompiledPlacement,
        activation: _Activation,
    ) -> _NodeSettlement:
        definition = placement.definition
        if type(definition) is not Node or placement.retry is None:
            raise RuntimeError("compiled Node placement is incomplete")

        attempt = 1
        previous: Failure | None = None
        packet_suppressed: tuple[Failure, ...] = ()
        while True:
            active_packet = (
                packet_suppressed
                if previous is None
                else (previous, *packet_suppressed)
            )
            self._check_scope_cancelled(scope, active_packet)
            await self._acquire_callback(
                scope,
                ready_callback=attempt > 1,
            )
            permit_held = True
            try:
                if self.attempts >= self.options.max_attempts:
                    raise _ProducedFailure(
                        self._new_failure(
                            "limit",
                            scope_id=scope.scope_id,
                            activation_id=activation.activation_id,
                            element_id=placement.element_id,
                            attempt=None,
                            detail=LimitDetail("max_attempts"),
                            previous=previous,
                        ),
                        packet_suppressed,
                    )
                self.attempts += 1
                try:
                    intents = await self._invoke_node(
                        scope,
                        placement,
                        activation,
                        attempt=attempt,
                        previous=previous,
                        inherited_suppressed=packet_suppressed,
                    )
                except _ProducedFailure as produced:
                    failure = produced.failure
                    if failure.kind not in {"handler", "handler_timeout"}:
                        raise
                    packet_suppressed = (*packet_suppressed, *produced.suppressed)
                    previous = failure
                    active_packet = (failure, *packet_suppressed)
                    self._check_scope_cancelled(scope, active_packet)
                    should_retry = (
                        attempt < placement.retry.max_attempts
                        and self._should_retry(
                            scope,
                            placement,
                            activation,
                            attempt,
                            failure,
                            packet_suppressed,
                        )
                    )
                    if should_retry:
                        if self.attempts >= self.options.max_attempts:
                            raise _ProducedFailure(
                                self._new_failure(
                                    "limit",
                                    scope_id=scope.scope_id,
                                    activation_id=activation.activation_id,
                                    element_id=placement.element_id,
                                    attempt=None,
                                    detail=LimitDetail("max_attempts"),
                                    previous=failure,
                                ),
                                packet_suppressed,
                            )
                        delay_ms = self._retry_delay(
                            scope,
                            placement,
                            activation,
                            attempt,
                            failure,
                            packet_suppressed,
                        )
                        self.retries_count += 1
                        self.publisher.publish(
                            RetryScheduledEvent,
                            RetryScheduledPayload(
                                scope.scope_id,
                                activation.activation_id,
                                failure.failure_id,
                                attempt,
                                attempt + 1,
                                delay_ms,
                            ),
                        )
                        self._check_scope_cancelled(scope, active_packet)
                        self._release_callback()
                        permit_held = False
                        if not await _sleep_milliseconds(
                            delay_ms,
                            scope.cancellation,
                        ):
                            self._check_scope_cancelled(scope, active_packet)
                        attempt += 1
                        continue
                    self._release_callback()
                    permit_held = False
                    self._check_scope_cancelled(scope, active_packet)
                    return await self._invoke_node_recovery(
                        scope,
                        placement,
                        activation,
                        failure,
                        packet_suppressed,
                    )

                if not intents:
                    intents = (_Intent("emit", None, activation.input, True),)
                return _NodeSettlement(intents, attempt, previous, packet_suppressed)
            finally:
                if permit_held:
                    self._release_callback()

    def _should_retry(
        self,
        scope: _RuntimeScope,
        placement: _CompiledPlacement,
        activation: _Activation,
        attempt: int,
        failure: Failure,
        inherited_suppressed: tuple[Failure, ...],
    ) -> bool:
        retry = placement.retry
        if retry is None:
            raise RuntimeError("compiled Node placement has no retry policy")
        try:
            result = retry.should_retry(failure)
        except BaseException as cause:  # noqa: BLE001 - policy boundary is total.
            replacement = self._new_failure(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                cause=cause,
                previous=failure,
            )
            self._commit_deadline_if_due()
            if self.cancellation.cancelled:
                raise _RunCancelled(
                    (failure, *inherited_suppressed, replacement)
                ) from None
            self._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed) from None
        self._check_cancelled((failure, *inherited_suppressed))
        if type(result) is not bool:
            _dispose_invalid_sync_result(result)
            replacement = self._new_failure(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                previous=failure,
            )
            self._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed)
        return result

    def _retry_delay(
        self,
        scope: _RuntimeScope,
        placement: _CompiledPlacement,
        activation: _Activation,
        attempt: int,
        failure: Failure,
        inherited_suppressed: tuple[Failure, ...],
    ) -> int:
        retry = placement.retry
        if retry is None:
            raise RuntimeError("compiled Node placement has no retry policy")
        if not callable(retry.delay_ms):
            return retry.delay_ms
        try:
            result = retry.delay_ms(attempt, failure)
        except BaseException as cause:  # noqa: BLE001 - policy boundary is total.
            replacement = self._new_failure(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                cause=cause,
                previous=failure,
            )
            self._commit_deadline_if_due()
            if self.cancellation.cancelled:
                raise _RunCancelled(
                    (failure, *inherited_suppressed, replacement)
                ) from None
            self._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed) from None
        self._check_cancelled((failure, *inherited_suppressed))
        if type(result) is not int or not 0 <= result <= MAX_SAFE_INTEGER:
            _dispose_invalid_sync_result(result)
            replacement = self._new_failure(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                previous=failure,
            )
            self._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed)
        return result

    async def _invoke_node(
        self,
        scope: _RuntimeScope,
        placement: _CompiledPlacement,
        activation: _Activation,
        *,
        attempt: int,
        previous: Failure | None,
        inherited_suppressed: tuple[Failure, ...],
    ) -> tuple[_Intent, ...]:
        definition = placement.definition
        if type(definition) is not Node or definition._handler is None:
            raise RuntimeError("compiled Node placement has no handler")
        handler = definition._handler
        callback_source = _CancellationSource(scope.cancellation)
        attempt_deadline = (
            None
            if placement.timeout_ms is None
            else _Deadline(time.monotonic_ns(), placement.timeout_ms)
        )
        timeout_failure_value: Failure | None = None

        def timeout_failure() -> Failure:
            nonlocal timeout_failure_value
            if timeout_failure_value is None:
                timeout_failure_value = self._new_failure(
                    "handler_timeout",
                    scope_id=scope.scope_id,
                    activation_id=activation.activation_id,
                    element_id=placement.element_id,
                    attempt=attempt,
                    previous=previous,
                )
            return timeout_failure_value

        context = _RuntimeContext(
            self.state,
            activation.input,
            scope_id=scope.scope_id,
            activation_id=activation.activation_id,
            parent_activation_id=activation.parent_activation_id,
            attempt=attempt,
            phase="handle",
            cancellation=callback_source,
            run_id=self.run_id,
            remaining_ms=lambda: self._remaining_ms(
                callback_source,
                attempt_deadline,
            ),
            intent_reserver=self._make_intent_reserver(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                previous=previous,
                suppressed=inherited_suppressed,
                callback_source=callback_source,
            ),
            reporter=self._make_reporter(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                previous=previous,
                suppressed=inherited_suppressed,
                callback_source=callback_source,
                attempt_deadline=attempt_deadline,
                timeout_failure=timeout_failure,
            ),
        )

        def classify(error: BaseException, selected: Failure | None) -> Failure:
            causal = previous if selected is None else selected
            if isinstance(error, _SemanticMisuse):
                return self._new_failure(
                    "invalid_outcome",
                    scope_id=scope.scope_id,
                    activation_id=activation.activation_id,
                    element_id=placement.element_id,
                    attempt=attempt,
                    detail=InvalidOutcomeDetail(error.reason),
                    previous=causal,
                )
            return self._new_failure(
                "handler",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                cause=error,
                previous=causal,
            )

        self._publish_callback_started(
            scope,
            activation.activation_id,
            activation.parent_activation_id,
            placement.element_id,
            "handle",
            attempt,
        )
        try:
            try:
                result = await self._await_lifecycle_callback(
                    context,
                    callback_source,
                    lambda: handler(context),
                    classify,
                    active=(
                        inherited_suppressed
                        if previous is None
                        else (previous, *inherited_suppressed)
                    ),
                    attempt_deadline=attempt_deadline,
                    timeout_failure=timeout_failure,
                )
            finally:
                intents = context._close()
            self._check_scope_cancelled(
                scope,
                () if previous is None else (previous,),
            )
            if result is not None:
                raise _ProducedFailure(
                    self._new_failure(
                        "invalid_outcome",
                        scope_id=scope.scope_id,
                        activation_id=activation.activation_id,
                        element_id=placement.element_id,
                        attempt=attempt,
                        detail=InvalidOutcomeDetail("wrong_return_type"),
                        previous=previous,
                    )
                )
        except _ProducedFailure as produced:
            failures = (produced.failure, *produced.suppressed)
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="handle",
                attempt=attempt,
                disposition=FailureDisposition("failure", produced.failure),
                failures=failures,
            )
            raise
        except (_RunCancelled, _RunAbandoned):
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="handle",
                attempt=attempt,
                disposition=DiscardedDisposition("discarded"),
            )
            raise
        return intents

    async def _invoke_node_recovery(
        self,
        scope: _RuntimeScope,
        placement: _CompiledPlacement,
        activation: _Activation,
        failure: Failure,
        inherited_suppressed: tuple[Failure, ...],
    ) -> _NodeSettlement:
        await self._acquire_callback(scope, ready_callback=True)
        try:
            return await self._invoke_node_recovery_admitted(
                scope,
                placement,
                activation,
                failure,
                inherited_suppressed,
            )
        finally:
            self._release_callback()

    async def _invoke_node_recovery_admitted(
        self,
        scope: _RuntimeScope,
        placement: _CompiledPlacement,
        activation: _Activation,
        failure: Failure,
        inherited_suppressed: tuple[Failure, ...],
    ) -> _NodeSettlement:
        definition = placement.definition
        if type(definition) is not Node:
            raise RuntimeError("compiled Node placement has no Node definition")
        callback = definition._recover
        if callback is None:
            raise _ProducedFailure(failure, inherited_suppressed)

        callback_source = _CancellationSource(scope.cancellation)
        context = _RuntimeContext(
            self.state,
            activation.input,
            scope_id=scope.scope_id,
            activation_id=activation.activation_id,
            parent_activation_id=activation.parent_activation_id,
            attempt=None,
            phase="node_recover",
            cancellation=callback_source,
            run_id=self.run_id,
            remaining_ms=lambda: self._remaining_ms(callback_source, None),
            intent_reserver=self._make_intent_reserver(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=None,
                previous=failure,
                suppressed=inherited_suppressed,
                callback_source=callback_source,
            ),
            reporter=self._make_reporter(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=None,
                previous=failure,
                suppressed=inherited_suppressed,
                callback_source=callback_source,
            ),
        )

        def classify(error: BaseException, selected: Failure | None) -> Failure:
            causal = failure if selected is None else selected
            if isinstance(error, _SemanticMisuse):
                return self._new_failure(
                    "invalid_outcome",
                    scope_id=scope.scope_id,
                    activation_id=activation.activation_id,
                    element_id=placement.element_id,
                    attempt=None,
                    detail=InvalidOutcomeDetail(error.reason),
                    previous=causal,
                )
            return self._new_failure(
                "node_recovery",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=None,
                cause=error,
                previous=causal,
            )

        self._publish_callback_started(
            scope,
            activation.activation_id,
            activation.parent_activation_id,
            placement.element_id,
            "node_recover",
            None,
        )
        try:
            try:
                result = await self._await_lifecycle_callback(
                    context,
                    callback_source,
                    lambda: callback(context, failure),
                    classify,
                    active=(failure, *inherited_suppressed),
                )
            finally:
                intents = context._close()
            self._check_scope_cancelled(scope, (failure, *inherited_suppressed))
            if result is not None:
                raise _ProducedFailure(
                    self._new_failure(
                        "invalid_outcome",
                        scope_id=scope.scope_id,
                        activation_id=activation.activation_id,
                        element_id=placement.element_id,
                        attempt=None,
                        detail=InvalidOutcomeDetail("wrong_return_type"),
                        previous=failure,
                    ),
                    inherited_suppressed,
                )
        except _ProducedFailure as produced:
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="node_recover",
                attempt=None,
                disposition=FailureDisposition("failure", produced.failure),
                failures=(produced.failure, *produced.suppressed),
            )
            raise
        except (_RunCancelled, _RunAbandoned):
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="node_recover",
                attempt=None,
                disposition=DiscardedDisposition("discarded"),
            )
            raise
        if not intents:
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="node_recover",
                attempt=None,
                disposition=CallbackOutcomeDisposition("outcome", "unhandled"),
            )
            raise _ProducedFailure(failure, inherited_suppressed)
        return _NodeSettlement(intents, None, failure, inherited_suppressed)

    async def _invoke_combine(
        self,
        scope: _RuntimeScope,
        result_view: ScopeResult,
    ) -> tuple[_Intent, ...]:
        await self._acquire_callback(scope, ready_callback=True)
        try:
            return await self._invoke_combine_admitted(scope, result_view)
        finally:
            self._release_callback()

    async def _invoke_combine_admitted(
        self,
        scope: _RuntimeScope,
        result_view: ScopeResult,
    ) -> tuple[_Intent, ...]:
        callback = scope.definition.combine
        if callback is None:
            return ()
        callback_source = _CancellationSource(scope.cancellation)
        context = _RuntimeContext(
            self.state,
            scope.incoming_input,
            scope_id=scope.scope_id,
            activation_id=scope.owner_activation_id,
            parent_activation_id=scope.owner_parent_activation_id,
            attempt=None,
            phase="flow_combine",
            cancellation=callback_source,
            run_id=self.run_id,
            remaining_ms=lambda: self._remaining_ms(callback_source, None),
            intent_reserver=self._make_intent_reserver(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                previous=None,
                suppressed=(),
                callback_source=callback_source,
            ),
            reporter=self._make_reporter(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                previous=None,
                suppressed=(),
                callback_source=callback_source,
            ),
        )

        def classify(error: BaseException, selected: Failure | None) -> Failure:
            if isinstance(error, _SemanticMisuse):
                return self._new_failure(
                    "invalid_combination",
                    scope_id=scope.scope_id,
                    activation_id=scope.owner_activation_id,
                    element_id=scope.owner_placement.element_id,
                    attempt=None,
                    detail=InvalidCombinationDetail(error.reason),
                    previous=selected,
                )
            return self._new_failure(
                "flow_combine",
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                cause=error,
                previous=selected,
            )

        self._publish_callback_started(
            scope,
            scope.owner_activation_id,
            scope.owner_parent_activation_id,
            scope.owner_placement.element_id,
            "flow_combine",
            None,
        )
        try:
            try:
                result = await self._await_lifecycle_callback(
                    context,
                    callback_source,
                    lambda: callback(context, result_view),
                    classify,
                )
            finally:
                intents = context._close()
            self._check_scope_cancelled(scope)
            if result is not None:
                raise _ProducedFailure(
                    self._new_failure(
                        "invalid_combination",
                        scope_id=scope.scope_id,
                        activation_id=scope.owner_activation_id,
                        element_id=scope.owner_placement.element_id,
                        attempt=None,
                        detail=InvalidCombinationDetail("wrong_return_type"),
                    )
                )
        except _ProducedFailure as produced:
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_combine",
                attempt=None,
                disposition=FailureDisposition("failure", produced.failure),
                failures=(produced.failure, *produced.suppressed),
            )
            raise
        except (_RunCancelled, _RunAbandoned):
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_combine",
                attempt=None,
                disposition=DiscardedDisposition("discarded"),
            )
            raise
        if not intents:
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_combine",
                attempt=None,
                disposition=CallbackOutcomeDisposition("outcome", "forward"),
            )
        return intents

    def _route(
        self,
        scope: _RuntimeScope,
        source: _CompiledPlacement,
        source_activation_id: int,
        intents: tuple[_Intent, ...],
        *,
        attempt: int | None = None,
        previous: Failure | None = None,
        suppressed: tuple[Failure, ...] = (),
        callback_phase: Phase | None = None,
        forwarded: bool = False,
        suffix: Sequence[_EventSpec] = (),
    ) -> None:
        try:
            self._check_cancelled(() if previous is None else (previous,))
            resolutions: list[tuple[Literal["target", "exit", "end"], int | None]] = []
            for intent in intents:
                if intent.kind == "end":
                    resolutions.append(("end", None))
                    continue
                target = next(
                    (
                        link.target_element_id
                        for link in source.links
                        if link.action == intent.action
                    ),
                    None,
                )
                if target is not None:
                    resolutions.append(("target", target))
                elif intent.action is None or intent.action in scope.definition.exits:
                    resolutions.append(("exit", None))
                else:
                    raise _ProducedFailure(
                        self._new_failure(
                            "unknown_action",
                            scope_id=scope.scope_id,
                            activation_id=source_activation_id,
                            element_id=source.element_id,
                            attempt=attempt,
                            detail=UnknownActionDetail(intent.action),
                            previous=previous,
                        ),
                        suppressed,
                    )

            target_count = sum(
                1 for resolution, _target in resolutions if resolution == "target"
            )
            terminal_count = len(intents) - target_count
            self._preflight_batch_capacity(
                scope,
                source,
                source_activation_id,
                attempt,
                previous,
                transition_count=len(intents),
                target_count=target_count,
                terminal_count=terminal_count,
                suppressed=suppressed,
            )
        except _ProducedFailure as produced:
            if callback_phase is not None:
                self._publish_callback_finished(
                    scope_id=scope.scope_id,
                    activation_id=source_activation_id,
                    phase=callback_phase,
                    attempt=attempt,
                    disposition=FailureDisposition("failure", produced.failure),
                    failures=(produced.failure, *produced.suppressed),
                )
            else:
                self._publish_failure_recorded(produced.failure)
            raise

        if callback_phase is not None:
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=source_activation_id,
                phase=callback_phase,
                attempt=attempt,
                disposition=CallbackOutcomeDisposition(
                    "outcome", self._intent_outcome(intents)
                ),
            )
            self._check_cancelled(() if previous is None else (previous,))
        self.transitions += len(intents)
        scope.direct_activations += target_count
        specs: list[_EventSpec] = []
        for branch_index, (intent, (resolution, target)) in enumerate(
            zip(intents, resolutions, strict=True)
        ):
            if resolution == "target":
                if target is None:
                    raise RuntimeError("target resolution has no element")
                activation_id = self._allocate_activation_id()
                scope.queue.append(
                    _Activation(
                        target,
                        intent.value,
                        activation_id,
                        source_activation_id,
                    )
                )
                self.ready_count += 1
                self.peak_ready = max(self.peak_ready, self.ready_count)
                transition: Transition = RoutedTransition(
                    "forward_exit" if forwarded else "route",
                    intent.action,
                    ActivationDestination(activation_id, target),
                )
            elif resolution == "end":
                terminal = self._end_terminal(intent, source_activation_id)
                scope.terminals.append(terminal)
                transition = EndTransition(
                    "forward_end" if forwarded else "end",
                    TerminalDestination(terminal.sequence),
                )
                specs.extend(
                    self._terminal_event_specs(
                        scope.scope_id,
                        source_activation_id,
                        branch_index,
                        transition,
                        terminal,
                    )
                )
                continue
            else:
                exit_terminal = ExitTerminal(
                    action=intent.action,
                    output=intent.value,
                    sequence=self._allocate_terminal_sequence(),
                    source_activation_id=source_activation_id,
                )
                scope.terminals.append(exit_terminal)
                transition = RoutedTransition(
                    "forward_exit" if forwarded else "route",
                    intent.action,
                    TerminalDestination(exit_terminal.sequence),
                )
                specs.extend(
                    self._terminal_event_specs(
                        scope.scope_id,
                        source_activation_id,
                        branch_index,
                        transition,
                        exit_terminal,
                    )
                )
                continue
            specs.append(
                (
                    TransitionCommittedEvent,
                    TransitionCommittedPayload(
                        scope.scope_id,
                        source_activation_id,
                        branch_index,
                        transition,
                    ),
                )
            )
        specs.extend(suffix)
        self.publisher.publish_bundle(specs)

    @staticmethod
    def _intent_outcome(
        intents: Sequence[_Intent],
    ) -> Literal["route", "fanout", "end", "forward", "unhandled"]:
        if len(intents) > 1:
            return "fanout"
        return "end" if intents[0].kind == "end" else "route"

    @staticmethod
    def _terminal_event_specs(
        scope_id: int,
        source_activation_id: int,
        branch_index: int,
        transition: Transition,
        terminal: Terminal,
    ) -> tuple[_EventSpec, _EventSpec]:
        metadata: TerminalMetadata
        if terminal.type == "end":
            metadata = EndTerminalMetadata(terminal.has_output)
        else:
            metadata = ExitTerminalMetadata(terminal.action)
        return (
            (
                TransitionCommittedEvent,
                TransitionCommittedPayload(
                    scope_id,
                    source_activation_id,
                    branch_index,
                    transition,
                ),
            ),
            (
                TerminalCommittedEvent,
                TerminalCommittedPayload(
                    scope_id,
                    terminal.sequence,
                    source_activation_id,
                    metadata,
                ),
            ),
        )

    def _boundary_terminals(
        self,
        scope: _RuntimeScope,
        intents: tuple[_Intent, ...],
        *,
        previous: Failure | None = None,
        callback_phase: Phase = "flow_combine",
    ) -> list[Terminal]:
        try:
            self._check_cancelled(() if previous is None else (previous,))
            for intent in intents:
                if intent.kind == "end":
                    continue
                if scope.parent is None:
                    resolved = (
                        intent.action is None or intent.action in scope.definition.exits
                    )
                else:
                    resolved = (
                        any(
                            link.action == intent.action
                            for link in scope.owner_placement.links
                        )
                        or intent.action is None
                        or intent.action in scope.parent.definition.exits
                    )
                if not resolved:
                    raise _ProducedFailure(
                        self._new_failure(
                            "unknown_action",
                            scope_id=scope.scope_id,
                            activation_id=scope.owner_activation_id,
                            element_id=scope.owner_placement.element_id,
                            attempt=None,
                            detail=UnknownActionDetail(cast(str, intent.action)),
                            previous=previous,
                        )
                    )

            self._preflight_batch_capacity(
                scope,
                scope.owner_placement,
                scope.owner_activation_id,
                None,
                previous,
                transition_count=len(intents),
                target_count=0,
                terminal_count=len(intents),
            )
        except _ProducedFailure as produced:
            self._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase=callback_phase,
                attempt=None,
                disposition=FailureDisposition("failure", produced.failure),
                failures=(produced.failure, *produced.suppressed),
            )
            raise
        self._publish_callback_finished(
            scope_id=scope.scope_id,
            activation_id=scope.owner_activation_id,
            phase=callback_phase,
            attempt=None,
            disposition=CallbackOutcomeDisposition(
                "outcome", self._intent_outcome(intents)
            ),
        )
        self._check_cancelled(() if previous is None else (previous,))
        terminals: list[Terminal] = []
        specs: list[_EventSpec] = []
        for branch_index, intent in enumerate(intents):
            if intent.kind == "end":
                terminal: Terminal = self._end_terminal(
                    intent, scope.owner_activation_id
                )
                transition: Transition = EndTransition(
                    "end", TerminalDestination(terminal.sequence)
                )
            else:
                terminal = ExitTerminal(
                    action=intent.action,
                    output=intent.value,
                    sequence=self._allocate_terminal_sequence(),
                    source_activation_id=scope.owner_activation_id,
                )
                transition = RoutedTransition(
                    "route",
                    intent.action,
                    TerminalDestination(terminal.sequence),
                )
            terminals.append(terminal)
            if scope.parent is None:
                specs.extend(
                    self._terminal_event_specs(
                        scope.scope_id,
                        scope.owner_activation_id,
                        branch_index,
                        transition,
                        terminal,
                    )
                )
        self.transitions += len(intents)
        self.publisher.publish_bundle(specs)
        return terminals

    def _preflight_batch_capacity(
        self,
        scope: _RuntimeScope,
        source: _CompiledPlacement,
        source_activation_id: int,
        attempt: int | None,
        previous: Failure | None,
        *,
        transition_count: int,
        target_count: int,
        terminal_count: int,
        suppressed: tuple[Failure, ...] = (),
    ) -> None:
        limit: LimitName | None = None
        if self.transitions + transition_count > self.options.max_transitions:
            limit = "max_transitions"
        elif (
            transition_count > MAX_PORTABLE_COLLECTION_LENGTH
            or len(scope.queue) + target_count > MAX_PORTABLE_COLLECTION_LENGTH
            or len(scope.terminals) + terminal_count > MAX_PORTABLE_COLLECTION_LENGTH
        ):
            limit = "portable_collection"
        elif self.activations + target_count > self.options.max_activations:
            limit = "max_activations"
        elif (
            scope.definition.max_activations is not None
            and scope.direct_activations + target_count
            > scope.definition.max_activations
        ):
            limit = "scope_max_activations"
        elif self.ready_count + target_count > self.options.max_ready:
            limit = "max_ready"
        elif (
            target_count > 0
            and self.next_activation_id + target_count - 1 > MAX_SAFE_INTEGER
        ) or (
            terminal_count > 0
            and self.next_terminal_sequence + terminal_count - 1 > MAX_SAFE_INTEGER
        ):
            limit = "safe_integer"
        if limit is None:
            return
        raise _ProducedFailure(
            self._new_failure(
                "limit",
                scope_id=scope.scope_id,
                activation_id=source_activation_id,
                element_id=source.element_id,
                attempt=attempt,
                detail=LimitDetail(limit),
                previous=previous,
            ),
            suppressed,
        )

    def _forward_child(self, child: _RuntimeScope) -> None:
        parent = child.parent
        if parent is None:
            raise RuntimeError("root scope cannot be forwarded")
        intents = tuple(
            _Intent(
                "end" if terminal.type == "end" else "emit",
                terminal.action if terminal.type == "exit" else None,
                terminal.output,
                terminal.has_output,
            )
            for terminal in child.terminals
        )
        finish_spec = self._scope_finished_spec(child, "completed")
        self._route(
            parent,
            child.owner_placement,
            child.owner_activation_id,
            intents,
            forwarded=True,
            suffix=(finish_spec,),
        )
        child.finished = True

    def _end_terminal(self, intent: _Intent, source_activation_id: int) -> EndTerminal:
        return EndTerminal(
            has_output=intent.present,
            output=intent.value if intent.present else None,
            sequence=self._allocate_terminal_sequence(),
            source_activation_id=source_activation_id,
        )

    def _allocate_activation_id(self) -> int:
        value = self.next_activation_id
        self.next_activation_id += 1
        self.activations += 1
        return value

    def _allocate_terminal_sequence(self) -> int:
        value = self.next_terminal_sequence
        self.next_terminal_sequence += 1
        return value
