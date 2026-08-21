# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeAlias, TypeVar, overload

Action: TypeAlias = str
T = TypeVar("T")
StateT = TypeVar("StateT", default=dict[str, Any])
InputT = TypeVar("InputT", default=object)
ContextStateT_co = TypeVar("ContextStateT_co", covariant=True, default=dict[str, Any])
ContextInputT_co = TypeVar("ContextInputT_co", covariant=True, default=object)
MaybeAwaitable: TypeAlias = T | Awaitable[T]


class CaskadaError(Exception):
    pass


class GraphDefinitionError(CaskadaError):
    pass


class DuplicateLinkError(GraphDefinitionError):
    pass


class Context(Protocol, Generic[ContextStateT_co, ContextInputT_co]):
    @property
    def state(self) -> ContextStateT_co: ...

    @property
    def input(self) -> ContextInputT_co: ...

    @overload
    def emit(self) -> None: ...

    @overload
    def emit(self, *, input: object) -> None: ...

    @overload
    def emit(self, action: Action, /) -> None: ...

    @overload
    def emit(self, action: Action, input: object, /) -> None: ...

    @overload
    def end(self) -> None: ...

    @overload
    def end(self, output: object, /) -> None: ...


@dataclass(frozen=True, slots=True)
class EndTerminal:
    has_output: bool
    output: object
    sequence: int
    source_activation_id: int
    type: Literal["end"] = "end"


@dataclass(frozen=True, slots=True)
class ExitTerminal:
    action: Action | None
    output: object
    sequence: int
    source_activation_id: int
    has_output: Literal[True] = True
    type: Literal["exit"] = "exit"


Terminal: TypeAlias = EndTerminal | ExitTerminal


@dataclass(frozen=True, slots=True)
class ScopeResult:
    terminals: tuple[Terminal, ...]

    @property
    def outputs(self) -> tuple[object, ...]:
        return tuple(
            terminal.output for terminal in self.terminals if terminal.has_output
        )


FailureKind: TypeAlias = Literal[
    "handler",
    "retry_policy",
    "node_recovery",
    "flow_combine",
    "flow_recovery",
    "invalid_outcome",
    "unknown_action",
    "activation_limit",
    "internal",
]


@dataclass(frozen=True, slots=True)
class Failure:
    failure_id: int
    kind: FailureKind
    message: str
    cause: BaseException | None
    scope_id: int
    activation_id: int | None
    element_id: int | None
    attempt: int | None
    previous: Failure | None = None


@dataclass(frozen=True, slots=True)
class ScopeFailure:
    primary: Failure
    terminals: tuple[Terminal, ...]
    result: ScopeResult | None
    failing_activation_id: int | None


@dataclass(frozen=True, slots=True)
class Completed(Generic[StateT]):
    state: StateT
    terminals: tuple[Terminal, ...]
    status: Literal["completed"] = "completed"


@dataclass(frozen=True, slots=True)
class Failed(Generic[StateT]):
    state: StateT
    terminals: tuple[Terminal, ...]
    failure: Failure
    status: Literal["failed"] = "failed"


RunResult: TypeAlias = Completed[StateT] | Failed[StateT]


class RunError(CaskadaError, Generic[StateT]):
    def __init__(self, result: Failed[StateT]) -> None:
        super().__init__(result.failure.message)
        self.result = result
        if result.failure.cause is not None:
            self.__cause__ = result.failure.cause


class RunHandle(Protocol, Generic[StateT]):
    def done(self) -> bool: ...

    async def result(self) -> RunResult[StateT]: ...


NodeHandler: TypeAlias = Callable[[Context[StateT, InputT]], MaybeAwaitable[None]]
NodeRecoveryHandler: TypeAlias = Callable[
    [Context[StateT, InputT], Failure], MaybeAwaitable[None]
]
FlowCombineHandler: TypeAlias = Callable[
    [Context[StateT, object], ScopeResult], MaybeAwaitable[None]
]
FlowRecoveryHandler: TypeAlias = Callable[
    [Context[StateT, object], ScopeFailure], MaybeAwaitable[None]
]


def _retry_all(_failure: Failure) -> bool:
    return True


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    should_retry: Callable[[Failure], bool] = _retry_all
    delay_ms: int | Callable[[int, Failure], int] = 0

    def __post_init__(self) -> None:
        _positive_integer(self.max_attempts, "RetryPolicy.max_attempts")
        if not callable(self.should_retry):
            raise GraphDefinitionError("RetryPolicy.should_retry must be callable")
        if not callable(self.delay_ms):
            _nonnegative_integer(self.delay_ms, "RetryPolicy.delay_ms")


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphDefinitionError(f"{field} must be a nonempty string")
    return value


def _positive_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise GraphDefinitionError(f"{field} must be a positive integer")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GraphDefinitionError(f"{field} must be a nonnegative integer")
    return value
