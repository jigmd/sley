# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# The sole orchestration owner for activations and structured scopes.
from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import (
    Any,
    Generic,
    Literal,
    cast,
)

from ._contracts import (
    MAX_PORTABLE_COLLECTION_LENGTH,
    MAX_SAFE_INTEGER,
    Abandoned,
    Action,
    ActivationDestination,
    CallbackOutcomeDisposition,
    CancellationInfo,
    Cancelled,
    Completed,
    DiscardedDisposition,
    EndTerminal,
    EndTerminalMetadata,
    EndTransition,
    ExitTerminal,
    ExitTerminalMetadata,
    Failed,
    Failure,
    FailureDisposition,
    InternalDetail,
    InvalidCombinationDetail,
    InvalidOutcomeDetail,
    LimitDetail,
    LimitName,
    NonEmptyTerminals,
    OptionValidationError,
    Phase,
    ReportEvent,
    ReportPayload,
    ReportWithDataPayload,
    ReportWithoutDataPayload,
    RetryScheduledEvent,
    RetryScheduledPayload,
    RoutedTransition,
    RunOptions,
    RunResult,
    RunStartedEvent,
    RunStartedPayload,
    RunStats,
    ScopeFailure,
    ScopeResult,
    ScopeStartedEvent,
    ScopeStartedPayload,
    StateT,
    Terminal,
    TerminalCommittedEvent,
    TerminalCommittedPayload,
    TerminalDestination,
    TerminalMetadata,
    Transition,
    TransitionCommittedEvent,
    TransitionCommittedPayload,
    UnknownActionDetail,
)
from ._definition import (
    Node,
    _CompiledPlacement,
    _CompiledScope,
    _CompiledSnapshot,
)
from ._failures import (
    _FailureFactory,
    _FailureFence,
    _FailurePacket,
    _is_recoverable_failure,
    _ProducedFailure,
    _RecoveryPolicy,
    _replace_packet,
    _RunAbandoned,
    _RunCancelled,
    _RunFailure,
    _ScopeFailure,
    _SemanticMisuse,
)
from ._observation import (
    _EventPublisher,
    _EventSpec,
    _RunAccounting,
    _RunObserver,
)
from ._state import _StateCarrier
from ._timing import (
    _CallbackController,
    _CallbackExecutor,
    _CancellationSource,
    _Deadline,
    _dispose_invalid_sync_result,
    _RunCancellation,
    _sleep_milliseconds,
)

_MISSING = object()


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
        self.cancellation = cancellation
        self.run_id = run_id
        self.options = options
        self.run_deadline = run_deadline
        self.placements = {
            placement.element_id: placement for placement in snapshot.placements
        }
        self.scopes = {scope.scope_definition_id: scope for scope in snapshot.scopes}
        self.accounting = _RunAccounting(started_ns)
        self.failures = _FailureFactory()
        max_concurrency = options.max_concurrency or snapshot.auto_max_concurrency
        self.callbacks = _CallbackController(max_concurrency, cancellation)
        self.runtime_scopes: dict[int, _RuntimeScope] = {}
        self.observer = _RunObserver(publisher, cancellation, self.runtime_scopes)
        self.run_cancellation = _RunCancellation(
            cancellation, run_deadline, self.observer
        )
        self.callback_executor = _CallbackExecutor(
            cancellation, options, self.run_cancellation, self.observer
        )
        self.recovery = _RecoveryPolicy(
            self.failures,
            self.run_cancellation,
            self.observer,
            cancellation,
            _dispose_invalid_sync_result,
        )

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
                self.accounting.stats(self.callbacks.peak),
                suppressed=abandoned.suppressed,
                abandonment=abandoned.cause,
            )
            status = "abandoned"
        except _RunCancelled as cancelled:
            self.observer._publish_run_cancellation_if_needed()
            result = _SerialOutcome(
                tuple(root.terminals),
                self.accounting.stats(self.callbacks.peak),
                suppressed=cancelled.suppressed,
                cancellation=CancellationInfo(
                    reason=self.cancellation.reason,
                    deadline=self.cancellation.deadline,
                ),
            )
            status = "cancelled"
        except _RunFailure as propagated:
            self.observer._publish_run_failure_fence(propagated.packet.primary)
            result = _SerialOutcome(
                tuple(root.terminals),
                self.accounting.stats(self.callbacks.peak),
                propagated.packet.primary,
                propagated.packet.suppressed,
            )
            status = "failed"
        except _ProducedFailure as produced:
            self.observer._publish_run_failure_fence(produced.failure)
            result = _SerialOutcome(
                tuple(root.terminals),
                self.accounting.stats(self.callbacks.peak),
                produced.failure,
                produced.suppressed,
            )
            status = "failed"
        except BaseException:
            failure = self.failures.new(
                "internal",
                scope_id=1,
                activation_id=None,
                element_id=None,
                attempt=None,
                detail=InternalDetail("scheduler_invariant"),
            )
            self.observer._publish_run_failure_fence(failure)
            result = _SerialOutcome(
                tuple(root.terminals),
                self.accounting.stats(self.callbacks.peak),
                failure,
            )
            status = "failed"
        else:
            result = _SerialOutcome(
                terminals, self.accounting.stats(self.callbacks.peak)
            )
            status = "completed"
        self.observer._publish_terminal(root, status)
        return result

    def _checkpoint(self, suppressed: tuple[Failure, ...] = ()) -> None:
        self.run_cancellation.check(suppressed)

    async def _acquire_callback(
        self,
        scope: _RuntimeScope,
        *,
        ready_callback: bool,
    ) -> None:
        self.run_cancellation.check_scope(scope)
        try:
            await self.callbacks.acquire(
                ready_callback=ready_callback,
                cancellation=scope.cancellation,
                scope_id=scope.scope_id,
            )
        except asyncio.CancelledError:
            self.run_cancellation.check_scope(scope)
            raise

    async def _acquire_callback_source(
        self,
        cancellation: _CancellationSource,
        *,
        ready_callback: bool,
    ) -> None:
        self.run_cancellation.check()
        try:
            await self.callbacks.acquire(
                ready_callback=ready_callback,
                cancellation=cancellation,
            )
        except asyncio.CancelledError:
            self.run_cancellation.check()
            reason = cancellation.reason
            if isinstance(reason, _FailureFence):
                raise reason.produced
            raise

    def _release_callback(self) -> None:
        self.callbacks.release()

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
            self.run_cancellation.check_scope(scope)
            while scope.queue and len(active) < scope.definition.concurrency:
                activation = scope.queue.popleft()
                self.accounting.ready -= 1
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
            self.observer._publish_scope_failure_fence(scope, packet.primary)
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
                self.observer._capture_scope_finish_terminals(scope)
                scope.terminals = recovered
                scope.cancellation.close()
                return
            scope.cancellation.close()
            if scope.parent is None:
                raise _RunFailure(packet)
            finish = self.observer._mark_scope_finished(scope, "failed")
            if finish is not None:
                self.observer.publisher.publish_bundle((finish,))
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
                    self.observer._capture_scope_finish_terminals(scope)
                    scope.terminals = recovered
                else:
                    if intents:
                        self.observer._capture_scope_finish_terminals(scope)
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
            self.run_cancellation.check()
            scope = stack[-1]
            if scope.queue:
                activation = scope.queue.popleft()
                self.accounting.ready -= 1
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
                        self.observer._capture_scope_finish_terminals(scope)
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
            self.run_cancellation.check(
                (packet.primary, *packet.suppressed),
            )
            settled_before_fence = tuple(current_scope.terminals)
            current_scope.cancellation.cancel(
                _FailureFence(_ProducedFailure(packet.primary, packet.suppressed))
            )
            self.observer._publish_scope_failure_fence(current_scope, packet.primary)
            self._discard_scope_ready(current_scope)
            recovered, packet = await self._recover_scope(
                current_scope,
                packet,
                settled_before_fence=settled_before_fence,
                result=current_result,
                failing_activation_id=current_failing_activation_id,
            )
            if recovered is not None:
                self.observer._capture_scope_finish_terminals(current_scope)
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
            finish = self.observer._mark_scope_finished(completed, "failed")
            if finish is not None:
                self.observer.publisher.publish_bundle((finish,))
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
            self.run_cancellation.check((packet.primary, *packet.suppressed))
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
        self.run_cancellation.check((packet.primary, *packet.suppressed))
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
            remaining_ms=lambda: self.callback_executor._remaining_ms(
                callback_source, None
            ),
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
                return self.failures.new(
                    "invalid_combination",
                    scope_id=scope.scope_id,
                    activation_id=scope.owner_activation_id,
                    element_id=scope.owner_placement.element_id,
                    attempt=None,
                    detail=InvalidCombinationDetail(error.reason),
                    previous=causal,
                )
            return self.failures.new(
                "flow_recovery",
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                cause=error,
                previous=causal,
            )

        self.observer._publish_callback_started(
            scope,
            scope.owner_activation_id,
            scope.owner_parent_activation_id,
            scope.owner_placement.element_id,
            "flow_recover",
            None,
        )
        try:
            try:
                callback_result = (
                    await self.callback_executor._await_lifecycle_callback(
                        context,
                        callback_source,
                        lambda: callback(context, failure_view),
                        classify,
                        active=(packet.primary, *packet.suppressed),
                    )
                )
            except _ProducedFailure as produced:
                self.observer._publish_callback_finished(
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
                self.observer._publish_callback_finished(
                    scope_id=scope.scope_id,
                    activation_id=scope.owner_activation_id,
                    phase="flow_recover",
                    attempt=None,
                    disposition=DiscardedDisposition("discarded"),
                )
                raise
        finally:
            intents = context._close()

        self.run_cancellation.check((packet.primary, *packet.suppressed))
        if callback_result is not None:
            failure = self.failures.new(
                "invalid_combination",
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                detail=InvalidCombinationDetail("wrong_return_type"),
                previous=packet.primary,
            )
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_recover",
                attempt=None,
                disposition=FailureDisposition("failure", failure),
                failures=(failure,),
            )
            raise _RunFailure(_replace_packet(packet, failure))
        if not intents:
            self.observer._publish_callback_finished(
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
        self.accounting.ready -= discarded

    def _scope_result(self, scope: _RuntimeScope) -> ScopeResult:
        return ScopeResult(
            terminals=cast(NonEmptyTerminals, tuple(scope.terminals)),
            outputs=tuple(
                terminal.output for terminal in scope.terminals if terminal.has_output
            ),
        )

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
            if (
                self.accounting.transitions + buffered_count
                > self.options.max_transitions
            ):
                limit = "max_transitions"
            elif buffered_count > MAX_PORTABLE_COLLECTION_LENGTH:
                limit = "portable_collection"
            if limit is None:
                return
            produced = _ProducedFailure(
                self.failures.new(
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
            if self.observer.failure_fence is None:
                self.observer.failure_fence = produced
            produced = self.observer.failure_fence
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
            if self.observer.publisher.publishing:
                self.observer.publisher.reject_reentrant_report()
                return
            self.run_cancellation.commit_deadline_if_due()
            if self.observer.failure_fence is not None:
                raise asyncio.CancelledError
            if self.cancellation.cancelled:
                self.observer._publish_run_cancellation_if_needed()
                raise asyncio.CancelledError
            if callback_source.cancelled:
                raise asyncio.CancelledError
            if attempt_deadline is not None and attempt_deadline.due():
                if timeout_failure is None:
                    raise RuntimeError("attempt report checkpoint has no timeout")
                failure = timeout_failure()
                callback_source.cancel("attempt_timeout")
                self.observer._publish_attempt_timeout(context, failure)
                raise asyncio.CancelledError
            if type(name) is not str or not name:
                raise _SemanticMisuse(
                    "report_name", "report name must be a nonempty string"
                )
            if self.accounting.reports >= self.options.max_reports:
                produced = _ProducedFailure(
                    self.failures.new(
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
                self.observer.failure_fence = self.observer.failure_fence or produced
                self.observer._publish_run_failure_fence(
                    self.observer.failure_fence.failure
                )
                callback_source.cancel(_FailureFence(self.observer.failure_fence))
                raise asyncio.CancelledError
            self.accounting.reports += 1
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
            self.observer.publisher.publish(ReportEvent, payload)
            self.run_cancellation.commit_deadline_if_due()
            if self.cancellation.cancelled:
                self.observer._publish_run_cancellation_if_needed()
            if (
                not callback_source.cancelled
                and attempt_deadline is not None
                and attempt_deadline.due()
            ):
                if timeout_failure is None:
                    raise RuntimeError("attempt report checkpoint has no timeout")
                failure = timeout_failure()
                callback_source.cancel("attempt_timeout")
                self.observer._publish_attempt_timeout(context, failure)
            if (
                self.observer.failure_fence is not None
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
                    self.failures.new(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("max_depth"),
                    )
                )
            if self.accounting.activations + 1 > self.options.max_activations:
                raise _ProducedFailure(
                    self.failures.new(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("max_activations"),
                    )
                )
            if self.accounting.ready + 1 > self.options.max_ready:
                raise _ProducedFailure(
                    self.failures.new(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("max_ready"),
                    )
                )
            if (
                self.accounting.next_scope_id > MAX_SAFE_INTEGER
                or self.accounting.next_activation_id > MAX_SAFE_INTEGER
            ):
                raise _ProducedFailure(
                    self.failures.new(
                        "limit",
                        scope_id=parent.scope_id,
                        activation_id=owner_activation_id,
                        element_id=owner_placement.element_id,
                        attempt=None,
                        detail=LimitDetail("safe_integer"),
                    )
                )
            scope_id = self.accounting.next_scope_id
            self.accounting.next_scope_id += 1
            depth = parent.depth + 1
        self.accounting.scopes += 1
        entry_activation_id = self.accounting.allocate_activation_id()
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
        self.accounting.ready += 1
        self.accounting.peak_ready = max(
            self.accounting.peak_ready, self.accounting.ready
        )
        self.runtime_scopes[scope_id] = runtime_scope
        if parent is not None:
            self.observer.publisher.publish_bundle(
                (self.observer._scope_started_spec(runtime_scope),)
            )
            self.run_cancellation.check_scope(parent)
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
            self.run_cancellation.check_scope(scope, active_packet)
            await self._acquire_callback(
                scope,
                ready_callback=attempt > 1,
            )
            permit_held = True
            try:
                if self.accounting.attempts >= self.options.max_attempts:
                    raise _ProducedFailure(
                        self.failures.new(
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
                self.accounting.attempts += 1
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
                    self.run_cancellation.check_scope(scope, active_packet)
                    should_retry = (
                        attempt < placement.retry.max_attempts
                        and self.recovery._should_retry(
                            scope,
                            placement,
                            activation,
                            attempt,
                            failure,
                            packet_suppressed,
                        )
                    )
                    if should_retry:
                        if self.accounting.attempts >= self.options.max_attempts:
                            raise _ProducedFailure(
                                self.failures.new(
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
                        delay_ms = self.recovery._retry_delay(
                            scope,
                            placement,
                            activation,
                            attempt,
                            failure,
                            packet_suppressed,
                        )
                        self.accounting.retries += 1
                        self.observer.publisher.publish(
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
                        self.run_cancellation.check_scope(scope, active_packet)
                        self._release_callback()
                        permit_held = False
                        if not await _sleep_milliseconds(
                            delay_ms,
                            scope.cancellation,
                        ):
                            self.run_cancellation.check_scope(scope, active_packet)
                        attempt += 1
                        continue
                    self._release_callback()
                    permit_held = False
                    self.run_cancellation.check_scope(scope, active_packet)
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
                timeout_failure_value = self.failures.new(
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
            remaining_ms=lambda: self.callback_executor._remaining_ms(
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
                return self.failures.new(
                    "invalid_outcome",
                    scope_id=scope.scope_id,
                    activation_id=activation.activation_id,
                    element_id=placement.element_id,
                    attempt=attempt,
                    detail=InvalidOutcomeDetail(error.reason),
                    previous=causal,
                )
            return self.failures.new(
                "handler",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                cause=error,
                previous=causal,
            )

        self.observer._publish_callback_started(
            scope,
            activation.activation_id,
            activation.parent_activation_id,
            placement.element_id,
            "handle",
            attempt,
        )
        try:
            try:
                result = await self.callback_executor._await_lifecycle_callback(
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
            self.run_cancellation.check_scope(
                scope,
                () if previous is None else (previous,),
            )
            if result is not None:
                raise _ProducedFailure(
                    self.failures.new(
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
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="handle",
                attempt=attempt,
                disposition=FailureDisposition("failure", produced.failure),
                failures=failures,
            )
            raise
        except (_RunCancelled, _RunAbandoned):
            self.observer._publish_callback_finished(
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
            remaining_ms=lambda: self.callback_executor._remaining_ms(
                callback_source, None
            ),
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
                return self.failures.new(
                    "invalid_outcome",
                    scope_id=scope.scope_id,
                    activation_id=activation.activation_id,
                    element_id=placement.element_id,
                    attempt=None,
                    detail=InvalidOutcomeDetail(error.reason),
                    previous=causal,
                )
            return self.failures.new(
                "node_recovery",
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=None,
                cause=error,
                previous=causal,
            )

        self.observer._publish_callback_started(
            scope,
            activation.activation_id,
            activation.parent_activation_id,
            placement.element_id,
            "node_recover",
            None,
        )
        try:
            try:
                result = await self.callback_executor._await_lifecycle_callback(
                    context,
                    callback_source,
                    lambda: callback(context, failure),
                    classify,
                    active=(failure, *inherited_suppressed),
                )
            finally:
                intents = context._close()
            self.run_cancellation.check_scope(scope, (failure, *inherited_suppressed))
            if result is not None:
                raise _ProducedFailure(
                    self.failures.new(
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
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="node_recover",
                attempt=None,
                disposition=FailureDisposition("failure", produced.failure),
                failures=(produced.failure, *produced.suppressed),
            )
            raise
        except (_RunCancelled, _RunAbandoned):
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=activation.activation_id,
                phase="node_recover",
                attempt=None,
                disposition=DiscardedDisposition("discarded"),
            )
            raise
        if not intents:
            self.observer._publish_callback_finished(
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
            remaining_ms=lambda: self.callback_executor._remaining_ms(
                callback_source, None
            ),
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
                return self.failures.new(
                    "invalid_combination",
                    scope_id=scope.scope_id,
                    activation_id=scope.owner_activation_id,
                    element_id=scope.owner_placement.element_id,
                    attempt=None,
                    detail=InvalidCombinationDetail(error.reason),
                    previous=selected,
                )
            return self.failures.new(
                "flow_combine",
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                element_id=scope.owner_placement.element_id,
                attempt=None,
                cause=error,
                previous=selected,
            )

        self.observer._publish_callback_started(
            scope,
            scope.owner_activation_id,
            scope.owner_parent_activation_id,
            scope.owner_placement.element_id,
            "flow_combine",
            None,
        )
        try:
            try:
                result = await self.callback_executor._await_lifecycle_callback(
                    context,
                    callback_source,
                    lambda: callback(context, result_view),
                    classify,
                )
            finally:
                intents = context._close()
            self.run_cancellation.check_scope(scope)
            if result is not None:
                raise _ProducedFailure(
                    self.failures.new(
                        "invalid_combination",
                        scope_id=scope.scope_id,
                        activation_id=scope.owner_activation_id,
                        element_id=scope.owner_placement.element_id,
                        attempt=None,
                        detail=InvalidCombinationDetail("wrong_return_type"),
                    )
                )
        except _ProducedFailure as produced:
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_combine",
                attempt=None,
                disposition=FailureDisposition("failure", produced.failure),
                failures=(produced.failure, *produced.suppressed),
            )
            raise
        except (_RunCancelled, _RunAbandoned):
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase="flow_combine",
                attempt=None,
                disposition=DiscardedDisposition("discarded"),
            )
            raise
        if not intents:
            self.observer._publish_callback_finished(
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
            self.run_cancellation.check(() if previous is None else (previous,))
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
                        self.failures.new(
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
                self.observer._publish_callback_finished(
                    scope_id=scope.scope_id,
                    activation_id=source_activation_id,
                    phase=callback_phase,
                    attempt=attempt,
                    disposition=FailureDisposition("failure", produced.failure),
                    failures=(produced.failure, *produced.suppressed),
                )
            else:
                self.observer._publish_failure_recorded(produced.failure)
            raise

        if callback_phase is not None:
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=source_activation_id,
                phase=callback_phase,
                attempt=attempt,
                disposition=CallbackOutcomeDisposition(
                    "outcome", self._intent_outcome(intents)
                ),
            )
            self.run_cancellation.check(() if previous is None else (previous,))
        self.accounting.transitions += len(intents)
        scope.direct_activations += target_count
        specs: list[_EventSpec] = []
        for branch_index, (intent, (resolution, target)) in enumerate(
            zip(intents, resolutions, strict=True)
        ):
            if resolution == "target":
                if target is None:
                    raise RuntimeError("target resolution has no element")
                activation_id = self.accounting.allocate_activation_id()
                scope.queue.append(
                    _Activation(
                        target,
                        intent.value,
                        activation_id,
                        source_activation_id,
                    )
                )
                self.accounting.ready += 1
                self.accounting.peak_ready = max(
                    self.accounting.peak_ready, self.accounting.ready
                )
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
                    sequence=self.accounting.allocate_terminal_sequence(),
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
        self.observer.publisher.publish_bundle(specs)

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
            self.run_cancellation.check(() if previous is None else (previous,))
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
                        self.failures.new(
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
            self.observer._publish_callback_finished(
                scope_id=scope.scope_id,
                activation_id=scope.owner_activation_id,
                phase=callback_phase,
                attempt=None,
                disposition=FailureDisposition("failure", produced.failure),
                failures=(produced.failure, *produced.suppressed),
            )
            raise
        self.observer._publish_callback_finished(
            scope_id=scope.scope_id,
            activation_id=scope.owner_activation_id,
            phase=callback_phase,
            attempt=None,
            disposition=CallbackOutcomeDisposition(
                "outcome", self._intent_outcome(intents)
            ),
        )
        self.run_cancellation.check(() if previous is None else (previous,))
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
                    sequence=self.accounting.allocate_terminal_sequence(),
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
        self.accounting.transitions += len(intents)
        self.observer.publisher.publish_bundle(specs)
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
        if (
            self.accounting.transitions + transition_count
            > self.options.max_transitions
        ):
            limit = "max_transitions"
        elif (
            transition_count > MAX_PORTABLE_COLLECTION_LENGTH
            or len(scope.queue) + target_count > MAX_PORTABLE_COLLECTION_LENGTH
            or len(scope.terminals) + terminal_count > MAX_PORTABLE_COLLECTION_LENGTH
        ):
            limit = "portable_collection"
        elif self.accounting.activations + target_count > self.options.max_activations:
            limit = "max_activations"
        elif (
            scope.definition.max_activations is not None
            and scope.direct_activations + target_count
            > scope.definition.max_activations
        ):
            limit = "scope_max_activations"
        elif self.accounting.ready + target_count > self.options.max_ready:
            limit = "max_ready"
        elif (
            target_count > 0
            and self.accounting.next_activation_id + target_count - 1 > MAX_SAFE_INTEGER
        ) or (
            terminal_count > 0
            and self.accounting.next_terminal_sequence + terminal_count - 1
            > MAX_SAFE_INTEGER
        ):
            limit = "safe_integer"
        if limit is None:
            return
        raise _ProducedFailure(
            self.failures.new(
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
        finish_spec = self.observer._scope_finished_spec(child, "completed")
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
            sequence=self.accounting.allocate_terminal_sequence(),
            source_activation_id=source_activation_id,
        )
