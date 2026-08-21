# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Run accounting and synchronous event publication.
from __future__ import annotations

import inspect
import time
from collections import deque
from collections.abc import Sequence
from typing import (
    Any,
    TypeAlias,
)

from ._contracts import (
    MAX_SAFE_INTEGER,
    CancellationFencedEvent,
    CancellationFencedPayload,
    Observer,
    ObserverDiagnostic,
    RunEvent,
    RunFenceTarget,
    RunStats,
)
from ._timing import _dispose_invalid_sync_result

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
