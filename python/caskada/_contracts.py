# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Public runtime contracts shared by definition and execution modules.
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
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
        if result.status == "failed":
            cause = result.failure.cause
        elif result.status == "abandoned" and isinstance(result.cause, Failure):
            cause = result.cause.cause
        else:
            cause = None
        if cause is not None:
            self.__cause__ = cause

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
