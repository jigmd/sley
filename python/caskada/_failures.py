# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Failure construction, packets, and retry-policy evaluation.
from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
)

from ._contracts import (
    _FAILURE_MESSAGES,
    MAX_SAFE_INTEGER,
    CancellationInfo,
    Failure,
    FailureDetail,
    FailureKind,
    InvalidOutcomeReason,
)


class _SemanticMisuse(TypeError):
    def __init__(self, reason: InvalidOutcomeReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class _FailureFactory:
    """Allocates portable failure identities and immutable failure records."""

    __slots__ = ("_next_id",)

    def __init__(self) -> None:
        self._next_id = 1

    def new(
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
            failure_id=self._next_id,
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
        self._next_id += 1
        return failure


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


class _RecoveryPolicy:
    """Owns retry-policy invocation and replacement-failure semantics."""

    def __init__(
        self, failures, run_cancellation, observer, cancellation, dispose_invalid_result
    ) -> None:
        self.failures = failures
        self.run_cancellation = run_cancellation
        self.observer = observer
        self.cancellation = cancellation
        self.dispose_invalid_result = dispose_invalid_result

    def _should_retry(
        self,
        scope: Any,
        placement: Any,
        activation: Any,
        attempt: int,
        failure: Failure,
        inherited_suppressed: tuple[Failure, ...],
    ) -> bool:
        retry = placement.retry
        if retry is None:
            raise RuntimeError("compiled Node placement has no retry policy")
        try:
            result = retry.should_retry(failure)
        except BaseException as cause:
            replacement = self.failures.new(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                cause=cause,
                previous=failure,
            )
            self.run_cancellation.commit_deadline_if_due()
            if self.cancellation.cancelled:
                raise _RunCancelled(
                    (failure, *inherited_suppressed, replacement)
                ) from None
            self.observer._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed) from None
        self.run_cancellation.check((failure, *inherited_suppressed))
        if type(result) is not bool:
            self.dispose_invalid_result(result)
            replacement = self.failures.new(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                previous=failure,
            )
            self.observer._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed)
        return result

    def _retry_delay(
        self,
        scope: Any,
        placement: Any,
        activation: Any,
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
        except BaseException as cause:
            replacement = self.failures.new(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                cause=cause,
                previous=failure,
            )
            self.run_cancellation.commit_deadline_if_due()
            if self.cancellation.cancelled:
                raise _RunCancelled(
                    (failure, *inherited_suppressed, replacement)
                ) from None
            self.observer._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed) from None
        self.run_cancellation.check((failure, *inherited_suppressed))
        if type(result) is not int or not 0 <= result <= MAX_SAFE_INTEGER:
            self.dispose_invalid_result(result)
            replacement = self.failures.new(
                "retry_policy",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                previous=failure,
            )
            self.observer._publish_failure_recorded(replacement)
            raise _ProducedFailure(replacement, inherited_suppressed)
        return result
