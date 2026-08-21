# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Run accounting, event publication, and observable failure fences.
from __future__ import annotations

import inspect
import time
from collections import deque
from collections.abc import Sequence
from typing import (
    Any,
    Literal,
    TypeAlias,
    cast,
)

from ._contracts import (
    MAX_SAFE_INTEGER,
    AttemptFenceTarget,
    CallbackDisposition,
    CallbackFinishedEvent,
    CallbackFinishedPayload,
    CallbackStartedEvent,
    CallbackStartedPayload,
    CancellationFencedEvent,
    CancellationFencedPayload,
    Failure,
    FailureFencedEvent,
    FailureFencedPayload,
    FailureRecordedEvent,
    FailureRecordedPayload,
    Observer,
    ObserverDiagnostic,
    Phase,
    RunEvent,
    RunFenceTarget,
    RunFinishedEvent,
    RunFinishedPayload,
    RunStats,
    ScopeFenceTarget,
    ScopeFinishedEvent,
    ScopeFinishedPayload,
    ScopeStartedEvent,
    ScopeStartedPayload,
)
from ._failures import _FailureFence, _ProducedFailure
from ._timing import _CancellationSource, _dispose_invalid_sync_result

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
        except BaseException as cause:
            self._disable(event.sequence, "Observer raised", cause)
            return
        try:
            asynchronous = inspect.isawaitable(result) or inspect.isasyncgen(result)
        except BaseException as cause:
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


class _RunAccounting:
    """Owns run counters, portable identities, and the frozen stats snapshot."""

    def __init__(self, started_ns: int) -> None:
        self.started_ns = started_ns
        self.terminal_ns: int | None = None
        self.next_activation_id = 2
        self.next_scope_id = 2
        self.next_terminal_sequence = 1
        self.activations = 1
        self.attempts = 0
        self.transitions = 0
        self.retries = 0
        self.reports = 0
        self.scopes = 0
        self.ready = 0
        self.peak_ready = 0

    def allocate_activation_id(self) -> int:
        value = self.next_activation_id
        self.next_activation_id += 1
        self.activations += 1
        return value

    def allocate_terminal_sequence(self) -> int:
        value = self.next_terminal_sequence
        self.next_terminal_sequence += 1
        return value

    def stats(self, peak_callbacks: int) -> RunStats:
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
            retries=self.retries,
            reports=self.reports,
            scopes=self.scopes,
            peak_ready=self.peak_ready,
            peak_callbacks=peak_callbacks,
            duration_ms=duration_ms,
        )


class _RunObserver:
    """Owns event ordering, fences, and observer-visible run state."""

    def __init__(
        self,
        publisher: _EventPublisher,
        cancellation: _CancellationSource,
        runtime_scopes: dict[int, Any],
    ) -> None:
        self.publisher = publisher
        self.cancellation = cancellation
        self.runtime_scopes = runtime_scopes
        self.failure_fence: _ProducedFailure | None = None
        self.recorded_failures: set[int] = set()
        self.run_fence_published = False
        self.cancellation_fence_published = False
        self.scope_fences_published: set[int] = set()
        self.attempt_fences_published: set[tuple[int, int, int]] = set()

    def _scope_started_spec(self, scope: Any) -> _EventSpec:
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
        scope: Any,
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
        scope: Any,
        status: Literal["completed", "failed", "cancelled", "abandoned"],
    ) -> _EventSpec | None:
        if scope.finished:
            return None
        scope.finished = True
        return self._scope_finished_spec(scope, status)

    @staticmethod
    def _capture_scope_finish_terminals(scope: Any) -> None:
        if scope.finished_terminal_sequences is None:
            scope.finished_terminal_sequences = tuple(
                terminal.sequence for terminal in scope.terminals
            )

    def _publish_terminal(
        self,
        root: Any,
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
        scope: Any,
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
        scope: Any,
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
        context: Any,
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
