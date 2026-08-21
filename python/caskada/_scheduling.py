# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# The sole iterative orchestrator for activations and structured scopes.
from __future__ import annotations

import asyncio
import inspect
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, cast

from ._contracts import (
    MAX_PORTABLE_COLLECTION_LENGTH,
    MAX_SAFE_INTEGER,
    Abandoned,
    Action,
    ActivationDestination,
    AttemptFenceTarget,
    CallbackFinishedEvent,
    CallbackFinishedPayload,
    CallbackOutcomeDisposition,
    CallbackStartedEvent,
    CallbackStartedPayload,
    CancellationFencedEvent,
    CancellationFencedPayload,
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
    FailureFencedEvent,
    FailureFencedPayload,
    FailureRecordedEvent,
    FailureRecordedPayload,
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
    RunFenceTarget,
    RunFinishedEvent,
    RunFinishedPayload,
    RunOptions,
    RunResult,
    RunStartedEvent,
    RunStartedPayload,
    ScopeFailure,
    ScopeFenceTarget,
    ScopeFinishedEvent,
    ScopeFinishedPayload,
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
from ._definition import Node, _CompiledPlacement, _CompiledScope, _CompiledSnapshot
from ._failures import (
    _FailureFactory,
    _PacketOwner,
    _PacketRegistry,
    _SemanticMisuse,
)
from ._observation import _EventPublisher, _EventSpec, _RunAccounting
from ._state import _StateCarrier
from ._timing import (
    _CancellationSource,
    _dispose_invalid_sync_result,
    _Timer,
    _TimerHeap,
)

_MISSING = object()


class _RuntimeRunHandle(Generic[StateT]):
    __slots__ = ("_kernel", "_task")

    def __init__(
        self,
        task: asyncio.Task[RunResult[StateT]],
        kernel: _RuntimeKernel,
    ) -> None:
        self._task = task
        self._kernel = kernel

    def cancel(self, reason: Any = "cancelled") -> None:
        if not self._task.done():
            self._kernel.cancel(reason)

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


@dataclass(frozen=True, slots=True)
class _Intent:
    kind: Literal["emit", "end"]
    action: Action | None
    value: object
    present: bool


@dataclass(slots=True)
class _Activation:
    element_id: int
    input: object
    activation_id: int
    parent_activation_id: int
    scope_id: int
    status: str = "pending"
    attempt: int = 0
    packet_id: int | None = None
    child_scope_id: int | None = None
    work_id: int | None = None
    slot_held: bool = False


@dataclass(slots=True)
class _RuntimeScope:
    scope_id: int
    definition: _CompiledScope
    owner_activation_id: int
    owner_parent_activation_id: int | None
    incoming_input: object
    parent_scope_id: int | None
    owner_placement: _CompiledPlacement
    entry_activation_id: int
    pending: deque[int]
    terminals: list[Terminal]
    depth: int
    allocated_direct: int
    active_direct: int
    live_tokens: int
    cancellation: _CancellationSource
    activation_ids: set[int] = field(default_factory=set)
    status: str = "running"
    ready_queue: str | None = None
    packet_id: int | None = None
    work_id: int | None = None
    failing_activation_id: int | None = None
    settled_before_fence: tuple[Terminal, ...] = ()
    combine_result: ScopeResult | None = None
    finished_terminal_sequences: tuple[int, ...] | None = None
    combined: bool = False


@dataclass(frozen=True, slots=True)
class _CallbackWork:
    work_id: int
    kind: Literal["handle", "node_recover", "flow_combine", "flow_recover"]
    scope_id: int
    activation_id: int


@dataclass(slots=True)
class _CallbackWrapper:
    wrapper_id: int
    work: _CallbackWork
    context: _RuntimeContext
    source: _CancellationSource
    status: str = "starting"
    task: asyncio.Task[None] | None = None
    attempt_timer_id: int | None = None
    grace_timer_ids: set[int] = field(default_factory=set)
    settled_at_ns: int | None = None
    lifecycle_done_at_ns: int | None = None
    drained_packet_primary: Failure | None = None


@dataclass(frozen=True, slots=True)
class _CallbackSettlement:
    wrapper_id: int
    sequence: int
    settled_at_ns: int
    result: object
    error: BaseException | None
    intents: tuple[_Intent, ...]


@dataclass(slots=True)
class _GraceFence:
    grace_id: int
    timer_id: int
    due_ns: int
    protected: set[int]
    cause: Failure | CancellationInfo


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
            self, name, None if data is _MISSING else data, data is not _MISSING
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


def _start_runtime(
    snapshot: _CompiledSnapshot,
    state: _StateCarrier,
    loop: asyncio.AbstractEventLoop,
    options: RunOptions,
) -> _RuntimeRunHandle[Any]:
    kernel = _RuntimeKernel(snapshot, state, time.monotonic_ns(), options)
    kernel.publish_opening()
    kernel.opening_checkpoint()
    if kernel.final_status is not None:
        completed: asyncio.Future[RunResult[Any]] = loop.create_future()
        completed.set_result(kernel._finish_result())
        return _RuntimeRunHandle(cast(Any, completed), kernel)
    return _RuntimeRunHandle(loop.create_task(kernel.run()), kernel)


class _RuntimeKernel:
    def __init__(
        self,
        snapshot: _CompiledSnapshot,
        state: _StateCarrier,
        started_ns: int,
        options: RunOptions,
    ) -> None:
        self.snapshot = snapshot
        self.state = state
        self.options = options
        self.run_id = options.run_id or _allocate_run_id()
        self.publisher = _EventPublisher(self.run_id, options.observer)
        self.accounting = _RunAccounting(started_ns)
        self.failures = _FailureFactory()
        self.packets = _PacketRegistry()
        self.cancellation = _CancellationSource()
        self.timers = _TimerHeap()
        self.inbox: asyncio.Queue[_CallbackSettlement | None] = asyncio.Queue()

        self.placements = {
            placement.element_id: placement for placement in snapshot.placements
        }
        self.scope_definitions = {
            scope.scope_definition_id: scope for scope in snapshot.scopes
        }
        self.activations: dict[int, _Activation] = {}
        self.scopes: dict[int, _RuntimeScope] = {}
        self.flow_scope_ready: OrderedDict[int, None] = OrderedDict()
        self.node_scope_ready: OrderedDict[int, None] = OrderedDict()
        self.callback_ready: OrderedDict[int, _CallbackWork] = OrderedDict()
        self.wrappers: dict[int, _CallbackWrapper] = {}
        self.graces: dict[int, _GraceFence] = {}
        self.settlements: list[_CallbackSettlement] = []

        self.callback_limit = options.max_concurrency or snapshot.auto_max_concurrency
        self.active_callbacks = 0
        self.peak_callbacks = 0
        self.next_work_id = 1
        self.next_wrapper_id = 1
        self.next_settlement_sequence = 1
        self.next_grace_id = 1

        self.recorded_failures: set[int] = set()
        self.scope_fences: set[int] = set()
        self.attempt_fences: set[tuple[int, int, int]] = set()
        self.finished_scopes: set[int] = set()

        self.run_fence: Literal["failed", "cancelled"] | None = None
        self.final_status: (
            Literal["completed", "failed", "cancelled", "abandoned"] | None
        ) = None
        self.final_failure: Failure | None = None
        self.final_suppressed: tuple[Failure, ...] = ()
        self.final_cancellation: CancellationInfo | None = None
        self.final_abandonment: Failure | CancellationInfo | None = None
        self._terminal_result: RunResult[Any] | None = None

        if options.deadline_ms is not None:
            self.timers.add(
                "run_deadline",
                started_ns + options.deadline_ms * 1_000_000,
                0,
            )
        self.root = self._create_root_scope()

    def _create_root_scope(self) -> _RuntimeScope:
        definition = self.scope_definitions[1]
        placement = self.placements[1]
        entry_id = self.accounting.allocate_activation_id()
        activation = _Activation(
            definition.entry_element_id,
            None,
            entry_id,
            1,
            1,
        )
        self.activations[entry_id] = activation
        scope = _RuntimeScope(
            1,
            definition,
            1,
            None,
            None,
            None,
            placement,
            entry_id,
            deque((entry_id,)),
            [],
            1,
            1,
            0,
            1,
            _CancellationSource(self.cancellation),
        )
        self.scopes[1] = scope
        scope.activation_ids.add(entry_id)
        self.accounting.scopes = 1
        self.accounting.ready = 1
        self.accounting.peak_ready = 1
        self._recategorize_scope(scope)
        return scope

    def publish_opening(self) -> None:
        self.publisher.publish_bundle(
            (
                (RunStartedEvent, RunStartedPayload(1, 1)),
                (
                    ScopeStartedEvent,
                    ScopeStartedPayload(
                        1,
                        None,
                        1,
                        self.root.entry_activation_id,
                        self.root.definition.entry_element_id,
                        1,
                        1,
                    ),
                ),
            )
        )

    def opening_checkpoint(self) -> None:
        self._checkpoint()
        self._maybe_finish_run()

    def cancel(self, reason: Any = "cancelled") -> None:
        if self.final_status is not None or self.run_fence is not None:
            return
        self._commit_run_cancellation(
            reason, deadline=False, time_ns=time.monotonic_ns()
        )
        self.inbox.put_nowait(None)

    async def run(self) -> RunResult[Any]:
        try:
            while self.final_status is None:
                self._drain_inbox()
                self._checkpoint()
                if self.final_status is not None:
                    break
                self._process_settlements()
                self._advance_scopes()
                self._checkpoint()
                if self.final_status is not None:
                    break
                self._admit()
                self._advance_scopes()
                self._maybe_finish_run()
                if self.final_status is not None:
                    break
                await self._wait_for_work()
        except BaseException as cause:
            if self.final_status is None:
                failure = self.failures.new(
                    "internal",
                    scope_id=1,
                    activation_id=None,
                    element_id=None,
                    attempt=None,
                    cause=cause,
                    detail=InternalDetail("scheduler_invariant"),
                )
                packet_id = self.packets.create(
                    failure,
                    None,
                    _PacketOwner("run", None),
                )
                self._commit_run_failure(packet_id, time.monotonic_ns())
                self._force_terminal_if_quiet()
        return self._finish_result()

    def _drain_inbox(self) -> None:
        while True:
            try:
                item = self.inbox.get_nowait()
            except asyncio.QueueEmpty:
                return
            if item is not None:
                wrapper = self.wrappers.get(item.wrapper_id)
                if wrapper is not None and wrapper.status not in {
                    "abandoned",
                    "processed",
                }:
                    wrapper.settled_at_ns = item.settled_at_ns
                    wrapper.status = "published"
                    self.settlements.append(item)

    def _checkpoint(self) -> None:
        while self.final_status is None:
            timer = self.timers.peek()
            now_ns = time.monotonic_ns()
            if timer is None or timer.due_ns > now_ns:
                return
            self._process_timers(self.timers.pop_due(now_ns))

    def _process_timers(self, due: Sequence[_Timer]) -> None:
        retries: list[_Timer] = []
        for timer in due:
            if timer.kind == "retry":
                retries.append(timer)
            elif timer.kind == "run_deadline":
                if self.run_fence is None:
                    self._commit_run_cancellation(
                        "deadline_exceeded",
                        deadline=True,
                        time_ns=time.monotonic_ns(),
                    )
            elif timer.kind == "attempt":
                self._attempt_timeout(timer, time.monotonic_ns())
            else:
                self._grace_expired(timer)
            if self.final_status is not None:
                return
        self._process_settlements()
        for timer in retries:
            self._retry_ready(timer)

    async def _wait_for_work(self) -> None:
        timer = self.timers.peek()
        if timer is None:
            item = await self.inbox.get()
            self.inbox.put_nowait(item)
            return
        remaining_ms = max(
            0,
            (timer.due_ns - time.monotonic_ns() + 999_999) // 1_000_000,
        )
        if remaining_ms:
            try:
                item = await asyncio.wait_for(
                    self.inbox.get(), timeout=remaining_ms / 1_000
                )
            except TimeoutError:
                pass
            else:
                self.inbox.put_nowait(item)
                return
        current = self.timers.peek()
        if current is not None and current.timer_id == timer.timer_id:
            self._process_timers((self.timers.remove(timer.timer_id),))

    def _recategorize_scope(self, scope: _RuntimeScope) -> None:
        self.flow_scope_ready.pop(scope.scope_id, None)
        self.node_scope_ready.pop(scope.scope_id, None)
        scope.ready_queue = None
        if (
            scope.status != "running"
            or not scope.pending
            or scope.active_direct >= scope.definition.concurrency
        ):
            return
        activation = self.activations[scope.pending[0]]
        placement = self.placements[activation.element_id]
        if placement.kind == "flow":
            self.flow_scope_ready[scope.scope_id] = None
            scope.ready_queue = "flow"
        else:
            self.node_scope_ready[scope.scope_id] = None
            scope.ready_queue = "node"

    def _admit(self) -> None:
        while self.final_status is None and self.run_fence is None:
            self._checkpoint()
            if self.final_status is not None or self.run_fence is not None:
                return
            if self.callback_ready and self.active_callbacks < self.callback_limit:
                _work_id, work = self.callback_ready.popitem(last=False)
                self._start_callback(work, retry=work.kind == "handle")
                continue
            if self.flow_scope_ready:
                scope_id, _unused = self.flow_scope_ready.popitem(last=False)
                self.scopes[scope_id].ready_queue = None
                self._admit_nested_flow(self.scopes[scope_id])
                continue
            if self.node_scope_ready and self.active_callbacks < self.callback_limit:
                scope_id, _unused = self.node_scope_ready.popitem(last=False)
                self.scopes[scope_id].ready_queue = None
                self._admit_fresh_node(self.scopes[scope_id])
                continue
            return

    def _admit_fresh_node(self, scope: _RuntimeScope) -> None:
        activation = self.activations[scope.pending[0]]
        placement = self.placements[activation.element_id]
        if placement.kind != "node":
            raise RuntimeError("node-ready scope has a Flow head")
        if self.accounting.attempts >= self.options.max_attempts:
            self._fail_attempt_admission(scope, activation)
            return
        if scope.pending.popleft() != activation.activation_id:
            raise RuntimeError("scope pending head changed during admission")
        self.accounting.ready -= 1
        scope.active_direct += 1
        activation.slot_held = True
        activation.status = "callback_ready"
        activation.attempt = 1
        self.accounting.attempts += 1
        work = self._new_work("handle", scope.scope_id, activation.activation_id)
        activation.work_id = work.work_id
        self._start_callback(work, retry=False)
        self._recategorize_scope(scope)

    def _admit_nested_flow(self, parent: _RuntimeScope) -> None:
        activation = self.activations[parent.pending[0]]
        placement = self.placements[activation.element_id]
        if placement.kind != "flow" or placement.owned_scope_definition_id is None:
            raise RuntimeError("flow-ready scope has an incomplete head")
        definition = self.scope_definitions[placement.owned_scope_definition_id]
        limit: LimitName | None = None
        if parent.depth + 1 > self.options.max_depth:
            limit = "max_depth"
        elif self.accounting.activations + 1 > self.options.max_activations:
            limit = "max_activations"
        elif self.accounting.ready + 1 > self.options.max_ready:
            limit = "max_ready"
        elif (
            self.accounting.next_scope_id > MAX_SAFE_INTEGER
            or self.accounting.next_activation_id > MAX_SAFE_INTEGER
        ):
            limit = "safe_integer"
        if limit is not None:
            failure = self.failures.new(
                "limit",
                scope_id=parent.scope_id,
                activation_id=activation.activation_id,
                element_id=placement.element_id,
                attempt=None,
                detail=LimitDetail(limit),
            )
            packet_id = self.packets.create(
                failure,
                activation.input,
                _PacketOwner("activation", activation.activation_id),
            )
            activation.packet_id = packet_id
            self._commit_run_failure(packet_id, time.monotonic_ns())
            return

        parent.pending.popleft()
        self.accounting.ready -= 1
        parent.active_direct += 1
        activation.slot_held = True
        activation.status = "child_live"
        scope_id = self.accounting.next_scope_id
        self.accounting.next_scope_id += 1
        entry_id = self.accounting.allocate_activation_id()
        entry = _Activation(
            definition.entry_element_id,
            activation.input,
            entry_id,
            activation.activation_id,
            scope_id,
        )
        child = _RuntimeScope(
            scope_id,
            definition,
            activation.activation_id,
            activation.parent_activation_id,
            activation.input,
            parent.scope_id,
            placement,
            entry_id,
            deque((entry_id,)),
            [],
            parent.depth + 1,
            1,
            0,
            1,
            _CancellationSource(parent.cancellation),
        )
        activation.child_scope_id = scope_id
        self.activations[entry_id] = entry
        self.scopes[scope_id] = child
        child.activation_ids.add(entry_id)
        self.accounting.scopes += 1
        self.accounting.ready += 1
        self.accounting.peak_ready = max(
            self.accounting.peak_ready, self.accounting.ready
        )
        self.publisher.publish(
            ScopeStartedEvent,
            ScopeStartedPayload(
                scope_id,
                parent.scope_id,
                activation.activation_id,
                entry_id,
                definition.entry_element_id,
                placement.element_id,
                child.depth,
            ),
        )
        self._checkpoint()
        self._recategorize_scope(parent)
        self._recategorize_scope(child)

    def _new_work(
        self,
        kind: Literal["handle", "node_recover", "flow_combine", "flow_recover"],
        scope_id: int,
        activation_id: int,
    ) -> _CallbackWork:
        work = _CallbackWork(self.next_work_id, kind, scope_id, activation_id)
        self.next_work_id += 1
        return work

    def _queue_callback(self, work: _CallbackWork) -> None:
        self.callback_ready[work.work_id] = work
        activation = self._node_activation(work)
        if activation is not None:
            activation.work_id = work.work_id
            activation.status = "callback_ready"
        else:
            self.scopes[work.scope_id].work_id = work.work_id

    def _start_callback(self, work: _CallbackWork, *, retry: bool) -> None:
        scope = self.scopes[work.scope_id]
        activation = self._node_activation(work)
        if retry:
            if activation is None or work.kind != "handle":
                raise RuntimeError("retry work has no Node activation")
            if self.accounting.attempts >= self.options.max_attempts:
                self._fail_attempt_admission(scope, activation)
                return
            activation.attempt += 1
            self.accounting.attempts += 1

        wrapper_id = self.next_wrapper_id
        self.next_wrapper_id += 1
        source_parent = scope.cancellation
        if work.kind == "flow_recover":
            source_parent = (
                self.cancellation
                if scope.parent_scope_id is None
                else self.scopes[scope.parent_scope_id].cancellation
            )
        source = _CancellationSource(source_parent)
        context = self._make_context(wrapper_id, work, source)
        wrapper = _CallbackWrapper(wrapper_id, work, context, source)
        self.wrappers[wrapper_id] = wrapper
        self.active_callbacks += 1
        self.peak_callbacks = max(self.peak_callbacks, self.active_callbacks)
        if activation is not None:
            activation.status = "callback_live"

        attempt = activation.attempt if work.kind == "handle" and activation else None
        placement = self._work_placement(work)
        if work.kind == "handle" and placement.timeout_ms is not None:
            wrapper.attempt_timer_id = self.timers.add(
                "attempt",
                time.monotonic_ns() + placement.timeout_ms * 1_000_000,
                wrapper_id,
            )
        self.publisher.publish(
            CallbackStartedEvent,
            CallbackStartedPayload(
                scope.scope_id,
                work.activation_id,
                (
                    activation.parent_activation_id
                    if activation is not None
                    else scope.owner_parent_activation_id
                ),
                placement.element_id,
                work.kind,
                attempt,
            ),
        )
        self._checkpoint()
        if self._wrapper_controlled(wrapper):
            self._skip_starting(wrapper)
            return
        wrapper.status = "invoked"
        self._invoke_callback(wrapper, self._callback_invocation(wrapper))

    def _fail_attempt_admission(
        self, scope: _RuntimeScope, activation: _Activation
    ) -> None:
        placement = self.placements[activation.element_id]
        previous = (
            None
            if activation.packet_id is None
            else self.packets.get(activation.packet_id).primary
        )
        failure = self.failures.new(
            "limit",
            scope_id=scope.scope_id,
            activation_id=activation.activation_id,
            element_id=placement.element_id,
            attempt=None,
            detail=LimitDetail("max_attempts"),
            previous=previous,
        )
        if activation.packet_id is None:
            activation.packet_id = self.packets.create(
                failure,
                activation.input,
                _PacketOwner("activation", activation.activation_id),
            )
        else:
            self.packets.replace(activation.packet_id, failure)
        self._commit_run_failure(activation.packet_id, time.monotonic_ns())

    def _work_placement(self, work: _CallbackWork) -> _CompiledPlacement:
        activation = self._node_activation(work)
        if work.kind in {"handle", "node_recover"}:
            if activation is None:
                raise RuntimeError("Node work has no activation")
            return self.placements[activation.element_id]
        return self.scopes[work.scope_id].owner_placement

    def _node_activation(self, work: _CallbackWork) -> _Activation | None:
        if work.kind not in {"handle", "node_recover"}:
            return None
        activation = self.activations.get(work.activation_id)
        if activation is None:
            raise RuntimeError("Node work has no activation")
        return activation

    def _make_context(
        self,
        wrapper_id: int,
        work: _CallbackWork,
        source: _CancellationSource,
    ) -> _RuntimeContext:
        scope = self.scopes[work.scope_id]
        activation = self._node_activation(work)
        attempt = activation.attempt if work.kind == "handle" and activation else None
        input_value = (
            activation.input if activation is not None else scope.incoming_input
        )
        if work.kind == "flow_recover":
            if scope.packet_id is None:
                raise RuntimeError("Flow recovery work has no packet")
            input_value = self.packets.get(scope.packet_id).input
        parent_id = (
            activation.parent_activation_id
            if activation is not None
            else scope.owner_parent_activation_id
        )
        return _RuntimeContext(
            self.state,
            input_value,
            scope_id=scope.scope_id,
            activation_id=work.activation_id,
            parent_activation_id=parent_id,
            attempt=attempt,
            phase=work.kind,
            cancellation=source,
            run_id=self.run_id,
            remaining_ms=lambda: self._remaining_ms(wrapper_id),
            intent_reserver=self._make_intent_reserver(work, source),
            reporter=self._make_reporter(work, source),
        )

    def _make_intent_reserver(
        self, work: _CallbackWork, source: _CancellationSource
    ) -> Callable[[int], None]:
        def reserve(buffered_count: int) -> None:
            if source.cancelled or self.run_fence is not None:
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
            scope = self.scopes[work.scope_id]
            activation = self._node_activation(work)
            placement = self._work_placement(work)
            packet_id = self._packet_for_work(work)
            previous = (
                None if packet_id is None else self.packets.get(packet_id).primary
            )
            failure = self.failures.new(
                "limit",
                scope_id=scope.scope_id,
                activation_id=work.activation_id,
                element_id=placement.element_id,
                attempt=(
                    activation.attempt if work.kind == "handle" and activation else None
                ),
                detail=LimitDetail(limit),
                previous=previous,
            )
            if packet_id is None:
                packet_id = self.packets.create(
                    failure,
                    activation.input
                    if activation is not None
                    else scope.incoming_input,
                    _PacketOwner(
                        "activation" if activation is not None else "scope",
                        work.activation_id
                        if activation is not None
                        else scope.scope_id,
                    ),
                )
                self._set_packet_for_work(work, packet_id)
            else:
                self.packets.replace(packet_id, failure)
            self._commit_run_failure(packet_id, time.monotonic_ns())
            raise asyncio.CancelledError

        return reserve

    def _make_reporter(
        self, work: _CallbackWork, source: _CancellationSource
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
            self._checkpoint()
            if source.cancelled or self.run_fence is not None:
                raise asyncio.CancelledError
            if type(name) is not str or not name:
                raise _SemanticMisuse(
                    "report_name", "report name must be a nonempty string"
                )
            if self.accounting.reports >= self.options.max_reports:
                self._commit_report_limit(work)
                raise asyncio.CancelledError
            self.accounting.reports += 1
            payload: ReportPayload = (
                ReportWithDataPayload(work.scope_id, work.activation_id, name, data)
                if has_data
                else ReportWithoutDataPayload(work.scope_id, work.activation_id, name)
            )
            self.publisher.publish(ReportEvent, payload)
            self._checkpoint()
            if source.cancelled or self.run_fence is not None:
                raise asyncio.CancelledError

        return report

    def _commit_report_limit(self, work: _CallbackWork) -> None:
        scope = self.scopes[work.scope_id]
        activation = self._node_activation(work)
        placement = self._work_placement(work)
        packet_id = self._packet_for_work(work)
        previous = None if packet_id is None else self.packets.get(packet_id).primary
        failure = self.failures.new(
            "limit",
            scope_id=scope.scope_id,
            activation_id=work.activation_id,
            element_id=placement.element_id,
            attempt=(
                activation.attempt if work.kind == "handle" and activation else None
            ),
            detail=LimitDetail("max_reports"),
            previous=previous,
        )
        if packet_id is None:
            packet_id = self.packets.create(
                failure,
                activation.input if activation is not None else scope.incoming_input,
                _PacketOwner(
                    "activation" if activation else "scope", work.activation_id
                ),
            )
            self._set_packet_for_work(work, packet_id)
        else:
            self.packets.replace(packet_id, failure)
        self._commit_run_failure(packet_id, time.monotonic_ns())

    def _packet_for_work(self, work: _CallbackWork) -> int | None:
        activation = self._node_activation(work)
        return (
            activation.packet_id
            if activation is not None
            else self.scopes[work.scope_id].packet_id
        )

    def _set_packet_for_work(self, work: _CallbackWork, packet_id: int | None) -> None:
        activation = self._node_activation(work)
        if activation is not None:
            activation.packet_id = packet_id
        else:
            self.scopes[work.scope_id].packet_id = packet_id

    def _remaining_ms(self, wrapper_id: int) -> int | None:
        wrapper = self.wrappers.get(wrapper_id)
        if wrapper is None:
            return None
        due_values: list[int] = []
        if wrapper.attempt_timer_id is not None:
            try:
                due_values.append(self.timers.get(wrapper.attempt_timer_id).due_ns)
            except RuntimeError:
                pass
        for grace_id in wrapper.grace_timer_ids:
            grace = self.graces.get(grace_id)
            if grace is not None:
                due_values.append(grace.due_ns)
        timer = self.timers.peek()
        if timer is not None and timer.kind == "run_deadline":
            due_values.append(timer.due_ns)
        if not due_values:
            return None
        remaining = min(due_values) - time.monotonic_ns()
        return 0 if remaining <= 0 else (remaining + 999_999) // 1_000_000

    def _callback_invocation(self, wrapper: _CallbackWrapper) -> Callable[[], object]:
        work = wrapper.work
        scope = self.scopes[work.scope_id]
        placement = self._work_placement(work)
        activation = self._node_activation(work)
        if work.kind == "handle":
            if (
                type(placement.definition) is not Node
                or placement.definition._handler is None
            ):
                raise RuntimeError("compiled Node placement has no handler")
            return lambda: placement.definition._handler(wrapper.context)
        if work.kind == "node_recover":
            if (
                type(placement.definition) is not Node
                or placement.definition._recover is None
                or activation is None
                or activation.packet_id is None
            ):
                raise RuntimeError("Node recovery work is incomplete")
            failure = self.packets.get(activation.packet_id).primary
            return lambda: placement.definition._recover(wrapper.context, failure)
        if work.kind == "flow_combine":
            callback = scope.definition.combine
            if callback is None or scope.combine_result is None:
                raise RuntimeError("Flow combine work is incomplete")
            return lambda: callback(wrapper.context, scope.combine_result)
        callback = scope.definition.recover
        if callback is None or scope.packet_id is None:
            raise RuntimeError("Flow recovery work is incomplete")
        packet = self.packets.get(scope.packet_id)
        failure_view = ScopeFailure(
            primary=packet.primary,
            suppressed=packet.suppressed,
            settled_before_fence=scope.settled_before_fence,
            result=scope.combine_result,
            failing_activation_id=scope.failing_activation_id,
        )
        return lambda: callback(wrapper.context, failure_view)

    def _invoke_callback(
        self,
        wrapper: _CallbackWrapper,
        callback: Callable[[], object],
    ) -> None:
        try:
            result = callback()
            asynchronous = inspect.isawaitable(result)
        except BaseException as error:
            self._complete_wrapper(wrapper, None, error)
            return
        if not asynchronous:
            self._complete_wrapper(wrapper, result, None)
            return
        wrapper.task = asyncio.create_task(self._await_callback(wrapper, result))

    async def _await_callback(
        self, wrapper: _CallbackWrapper, awaitable: object
    ) -> None:
        try:
            result = await cast(Any, awaitable)
        except BaseException as error:
            self._complete_wrapper(wrapper, None, error)
        else:
            self._complete_wrapper(wrapper, result, None)

    def _complete_wrapper(
        self,
        wrapper: _CallbackWrapper,
        result: object,
        error: BaseException | None,
    ) -> None:
        settled_ns = time.monotonic_ns()
        intents = wrapper.context._close()
        wrapper.source.close()
        settlement = _CallbackSettlement(
            wrapper.wrapper_id,
            self.next_settlement_sequence,
            settled_ns,
            result,
            error,
            intents,
        )
        self.next_settlement_sequence += 1
        wrapper.settled_at_ns = settled_ns
        wrapper.status = "published"
        self.inbox.put_nowait(settlement)

    def _wrapper_controlled(self, wrapper: _CallbackWrapper) -> bool:
        return wrapper.source.cancelled or self.run_fence is not None

    def _skip_starting(self, wrapper: _CallbackWrapper) -> None:
        wrapper.context._abandon()
        wrapper.source.close()
        settled_ns = time.monotonic_ns()
        wrapper.settled_at_ns = settled_ns
        wrapper.status = "published"
        self.inbox.put_nowait(
            _CallbackSettlement(
                wrapper.wrapper_id,
                self.next_settlement_sequence,
                settled_ns,
                None,
                asyncio.CancelledError(),
                (),
            )
        )
        self.next_settlement_sequence += 1

    def _process_settlements(self) -> None:
        if not self.settlements:
            return
        pending = sorted(self.settlements, key=lambda item: item.sequence)
        self.settlements.clear()
        for settlement in pending:
            if self.final_status is not None:
                return
            wrapper = self.wrappers.get(settlement.wrapper_id)
            if wrapper is None or wrapper.status == "abandoned":
                continue
            if self._settlement_is_controlled(wrapper):
                self._settle_controlled(wrapper, settlement)
            else:
                self._settle_ordinary(wrapper, settlement)

    def _settlement_is_controlled(self, wrapper: _CallbackWrapper) -> bool:
        return wrapper.source.cancelled or self.run_fence is not None

    def _settle_controlled(
        self,
        wrapper: _CallbackWrapper,
        settlement: _CallbackSettlement,
    ) -> None:
        work = wrapper.work
        activation = self._node_activation(work)
        attempt_timeout = wrapper.source.reason == "attempt_timeout"
        packet_id = self._packet_for_work(work)
        if settlement.error is not None and not (
            isinstance(settlement.error, asyncio.CancelledError)
            and wrapper.source.cancelled
        ):
            failure = self._classify_error(wrapper, settlement.error)
            if packet_id is not None:
                self.packets.append(packet_id, failure)
            else:
                self.final_suppressed += (failure,)
            self._publish_failure_recorded(failure)

        if attempt_timeout and packet_id is not None:
            timeout = self.packets.get(packet_id).primary
            self._publish_callback_finished(
                wrapper,
                FailureDisposition("failure", timeout),
            )
            self._finish_wrapper(wrapper)
            self._select_retry_or_recovery(cast(_Activation, activation))
            return

        self._publish_callback_finished(wrapper, DiscardedDisposition("discarded"))
        self._finish_wrapper(wrapper)
        if activation is not None:
            self._discard_activation(activation)
        elif work.kind in {"flow_combine", "flow_recover"}:
            scope = self.scopes[work.scope_id]
            scope.work_id = None

    def _settle_ordinary(
        self,
        wrapper: _CallbackWrapper,
        settlement: _CallbackSettlement,
    ) -> None:
        work = wrapper.work
        if settlement.error is not None:
            failure = self._classify_error(wrapper, settlement.error)
            self._settle_callback_failure(wrapper, failure)
            return
        if settlement.result is not None:
            failure = self._wrong_return_failure(wrapper)
            self._settle_callback_failure(wrapper, failure)
            return

        intents = settlement.intents
        if work.kind == "handle" and not intents:
            activation = self.activations[work.activation_id]
            intents = (_Intent("emit", None, activation.input, True),)
        if work.kind == "node_recover" and not intents:
            self._publish_callback_finished(
                wrapper,
                CallbackOutcomeDisposition("outcome", "unhandled"),
            )
            self._finish_wrapper(wrapper)
            self._propagate_activation_failure(self.activations[work.activation_id])
            return
        if work.kind == "flow_combine" and not intents:
            self._publish_callback_finished(
                wrapper,
                CallbackOutcomeDisposition("outcome", "forward"),
            )
            self._finish_wrapper(wrapper)
            scope = self.scopes[work.scope_id]
            scope.work_id = None
            scope.status = "running"
            self._complete_scope(scope)
            return
        if work.kind == "flow_recover" and not intents:
            self._publish_callback_finished(
                wrapper,
                CallbackOutcomeDisposition("outcome", "unhandled"),
            )
            self._finish_wrapper(wrapper)
            self._propagate_scope_failure(self.scopes[work.scope_id])
            return

        disposition = CallbackOutcomeDisposition(
            "outcome", self._intent_outcome(intents)
        )
        self._publish_callback_finished(wrapper, disposition)
        self._finish_wrapper(wrapper)
        if work.kind in {"handle", "node_recover"}:
            activation = self.activations[work.activation_id]
            self._commit_node_route(activation, intents, work.kind)
        else:
            self._commit_flow_boundary(self.scopes[work.scope_id], intents, work.kind)

    def _settle_callback_failure(
        self, wrapper: _CallbackWrapper, failure: Failure
    ) -> None:
        work = wrapper.work
        packet_id = self._packet_for_work(work)
        activation = self._node_activation(work)
        scope = self.scopes[work.scope_id]
        if packet_id is None:
            packet_id = self.packets.create(
                failure,
                activation.input if activation is not None else scope.incoming_input,
                _PacketOwner(
                    "activation" if activation is not None else "scope",
                    work.activation_id if activation is not None else scope.scope_id,
                ),
            )
            self._set_packet_for_work(work, packet_id)
        else:
            self.packets.replace(packet_id, failure)
        self._publish_callback_finished(
            wrapper,
            FailureDisposition("failure", failure),
            failures=(failure,),
        )

        if failure.kind not in {
            "handler",
            "handler_timeout",
            "node_recovery",
            "flow_combine",
            "flow_recovery",
        }:
            self._finish_wrapper(wrapper)
            self._commit_run_failure(packet_id, time.monotonic_ns())
            return
        if work.kind == "handle":
            wrapper.status = "selecting_retry"
            self._select_retry_or_recovery(cast(_Activation, activation), wrapper)
            return
        self._finish_wrapper(wrapper)
        if work.kind == "node_recover":
            self._propagate_activation_failure(cast(_Activation, activation))
        elif work.kind == "flow_combine":
            self._begin_scope_failure(scope, packet_id, None)
        else:
            self._propagate_scope_failure(scope)

    def _classify_error(
        self, wrapper: _CallbackWrapper, error: BaseException
    ) -> Failure:
        work = wrapper.work
        scope = self.scopes[work.scope_id]
        activation = self._node_activation(work)
        placement = self._work_placement(work)
        packet_id = self._packet_for_work(work)
        previous = None if packet_id is None else self.packets.get(packet_id).primary
        attempt = activation.attempt if work.kind == "handle" and activation else None
        if isinstance(error, _SemanticMisuse):
            kind = (
                "invalid_outcome"
                if work.kind in {"handle", "node_recover"}
                else "invalid_combination"
            )
            detail = (
                InvalidOutcomeDetail(error.reason)
                if kind == "invalid_outcome"
                else InvalidCombinationDetail(error.reason)
            )
            return self.failures.new(
                kind,
                scope_id=scope.scope_id,
                activation_id=work.activation_id,
                element_id=placement.element_id,
                attempt=attempt,
                detail=detail,
                previous=previous,
            )
        kind = {
            "handle": "handler",
            "node_recover": "node_recovery",
            "flow_combine": "flow_combine",
            "flow_recover": "flow_recovery",
        }[work.kind]
        return self.failures.new(
            kind,
            scope_id=scope.scope_id,
            activation_id=work.activation_id,
            element_id=placement.element_id,
            attempt=attempt,
            cause=error,
            previous=previous,
        )

    def _wrong_return_failure(self, wrapper: _CallbackWrapper) -> Failure:
        work = wrapper.work
        scope = self.scopes[work.scope_id]
        activation = self._node_activation(work)
        placement = self._work_placement(work)
        packet_id = self._packet_for_work(work)
        previous = None if packet_id is None else self.packets.get(packet_id).primary
        if work.kind in {"handle", "node_recover"}:
            detail = InvalidOutcomeDetail("wrong_return_type")
            kind = "invalid_outcome"
        else:
            detail = InvalidCombinationDetail("wrong_return_type")
            kind = "invalid_combination"
        return self.failures.new(
            kind,
            scope_id=scope.scope_id,
            activation_id=work.activation_id,
            element_id=placement.element_id,
            attempt=(
                activation.attempt if work.kind == "handle" and activation else None
            ),
            detail=detail,
            previous=previous,
        )

    def _select_retry_or_recovery(
        self,
        activation: _Activation,
        wrapper: _CallbackWrapper | None = None,
    ) -> None:
        placement = self.placements[activation.element_id]
        if placement.retry is None or activation.packet_id is None:
            raise RuntimeError("failed Node activation has no retry packet")
        packet = self.packets.get(activation.packet_id)
        if activation.attempt >= placement.retry.max_attempts:
            if wrapper is not None:
                wrapper.lifecycle_done_at_ns = time.monotonic_ns()
                self._finish_wrapper(wrapper)
            self._queue_node_recovery(activation)
            return

        policy_error: BaseException | None = None
        try:
            should_retry = placement.retry.should_retry(packet.primary)
        except BaseException as error:
            policy_error = error
            should_retry = False
        policy_ns = time.monotonic_ns()
        if wrapper is not None:
            wrapper.lifecycle_done_at_ns = policy_ns
        self._checkpoint()
        if self.final_status is not None:
            return
        if self.run_fence is not None:
            if wrapper is not None and wrapper.wrapper_id in self.wrappers:
                self._finish_wrapper(wrapper)
            return
        if policy_error is not None or type(should_retry) is not bool:
            if policy_error is None:
                _dispose_invalid_sync_result(should_retry)
            self._fail_retry_policy(
                activation,
                policy_error,
                wrapper,
                policy_ns,
            )
            return
        if not should_retry:
            if wrapper is not None:
                self._finish_wrapper(wrapper)
            self._queue_node_recovery(activation)
            return
        if self.accounting.attempts >= self.options.max_attempts:
            if wrapper is not None:
                self._finish_wrapper(wrapper)
            self._fail_attempt_admission(self.scopes[activation.scope_id], activation)
            return

        delay_error: BaseException | None = None
        delay_value: object
        if callable(placement.retry.delay_ms):
            try:
                delay_value = placement.retry.delay_ms(
                    activation.attempt, packet.primary
                )
            except BaseException as error:
                delay_error = error
                delay_value = None
            delay_ns = time.monotonic_ns()
            if wrapper is not None:
                wrapper.lifecycle_done_at_ns = delay_ns
            self._checkpoint()
            if self.final_status is not None:
                return
            if self.run_fence is not None:
                if wrapper is not None and wrapper.wrapper_id in self.wrappers:
                    self._finish_wrapper(wrapper)
                return
            if (
                delay_error is not None
                or type(delay_value) is not int
                or not 0 <= cast(int, delay_value) <= MAX_SAFE_INTEGER
            ):
                if delay_error is None:
                    _dispose_invalid_sync_result(delay_value)
                self._fail_retry_policy(
                    activation,
                    delay_error,
                    wrapper,
                    delay_ns,
                )
                return
            delay_ms = cast(int, delay_value)
        else:
            delay_ms = placement.retry.delay_ms

        scheduled_ns = time.monotonic_ns()
        timer_id = self.timers.add(
            "retry",
            scheduled_ns + delay_ms * 1_000_000,
            activation.activation_id,
        )
        activation.work_id = timer_id
        activation.status = "retry_wait"
        self.accounting.retries += 1
        self.publisher.publish(
            RetryScheduledEvent,
            RetryScheduledPayload(
                activation.scope_id,
                activation.activation_id,
                packet.primary.failure_id,
                activation.attempt,
                activation.attempt + 1,
                delay_ms,
            ),
        )
        if wrapper is not None:
            wrapper.lifecycle_done_at_ns = scheduled_ns
            self._finish_wrapper(wrapper)
        self._checkpoint()

    def _fail_retry_policy(
        self,
        activation: _Activation,
        cause: BaseException | None,
        wrapper: _CallbackWrapper | None,
        settled_ns: int,
    ) -> None:
        if activation.packet_id is None:
            raise RuntimeError("retry policy failure has no packet")
        packet = self.packets.get(activation.packet_id)
        failure = self.failures.new(
            "retry_policy",
            scope_id=activation.scope_id,
            activation_id=activation.activation_id,
            element_id=activation.element_id,
            attempt=activation.attempt,
            cause=cause,
            previous=packet.primary,
        )
        self.packets.replace(activation.packet_id, failure)
        if wrapper is not None:
            wrapper.lifecycle_done_at_ns = settled_ns
            self._finish_wrapper(wrapper)
        self._commit_run_failure(activation.packet_id, settled_ns)

    def _queue_node_recovery(self, activation: _Activation) -> None:
        placement = self.placements[activation.element_id]
        definition = placement.definition
        if type(definition) is Node and definition._recover is not None:
            self._queue_callback(
                self._new_work(
                    "node_recover", activation.scope_id, activation.activation_id
                )
            )
            return
        self._propagate_activation_failure(activation)

    def _retry_ready(self, timer: _Timer) -> None:
        if self.run_fence is not None:
            return
        activation = self.activations.get(timer.owner_id)
        if activation is None or activation.status != "retry_wait":
            return
        work = self._new_work("handle", activation.scope_id, activation.activation_id)
        activation.work_id = work.work_id
        self._queue_callback(work)

    def _finish_wrapper(self, wrapper: _CallbackWrapper) -> None:
        self.timers.discard(wrapper.attempt_timer_id)
        wrapper.attempt_timer_id = None
        for grace_id in tuple(wrapper.grace_timer_ids):
            grace = self.graces.get(grace_id)
            if grace is None:
                continue
            grace.protected.discard(wrapper.wrapper_id)
            if not grace.protected:
                self.timers.discard(grace.timer_id)
                del self.graces[grace_id]
        wrapper.grace_timer_ids.clear()
        if self.active_callbacks <= 0:
            raise RuntimeError("callback permit released without ownership")
        self.active_callbacks -= 1
        if wrapper.work.kind in {"flow_combine", "flow_recover"}:
            scope = self.scopes[wrapper.work.scope_id]
            if scope.work_id == wrapper.work.work_id:
                scope.work_id = None
        wrapper.status = "processed"
        self.wrappers.pop(wrapper.wrapper_id, None)

    def _attempt_timeout(self, timer: _Timer, fenced_ns: int) -> None:
        wrapper = self.wrappers.get(timer.owner_id)
        if wrapper is None:
            return
        wrapper.attempt_timer_id = None
        if wrapper.settled_at_ns is not None and wrapper.settled_at_ns < timer.due_ns:
            return
        work = wrapper.work
        activation = self.activations.get(work.activation_id)
        if activation is None or work.kind != "handle":
            raise RuntimeError("attempt timer has no Node activation")
        packet_id = activation.packet_id
        previous = None if packet_id is None else self.packets.get(packet_id).primary
        failure = self.failures.new(
            "handler_timeout",
            scope_id=activation.scope_id,
            activation_id=activation.activation_id,
            element_id=activation.element_id,
            attempt=activation.attempt,
            previous=previous,
        )
        if packet_id is None:
            packet_id = self.packets.create(
                failure,
                activation.input,
                _PacketOwner("activation", activation.activation_id),
            )
            activation.packet_id = packet_id
        else:
            self.packets.replace(packet_id, failure)
        wrapper.source.cancel("attempt_timeout", fenced_ns=fenced_ns)
        self._publish_attempt_fence(wrapper, failure)
        if wrapper.status == "starting":
            return
        self._arm_grace(
            {wrapper.wrapper_id},
            failure,
            fenced_ns,
        )

    def _arm_grace(
        self,
        protected: set[int],
        cause: Failure | CancellationInfo,
        fenced_ns: int,
    ) -> None:
        if not protected:
            return
        grace_id = self.next_grace_id
        self.next_grace_id += 1
        due_ns = fenced_ns + self.options.cancel_grace_ms * 1_000_000
        timer_id = self.timers.add("grace", due_ns, grace_id)
        grace = _GraceFence(grace_id, timer_id, due_ns, set(protected), cause)
        self.graces[grace_id] = grace
        for wrapper_id in protected:
            wrapper = self.wrappers.get(wrapper_id)
            if wrapper is not None:
                wrapper.grace_timer_ids.add(grace_id)

    def _grace_expired(self, timer: _Timer) -> None:
        grace = self.graces.pop(timer.owner_id, None)
        if grace is None:
            return
        overdue = [
            self.wrappers[wrapper_id]
            for wrapper_id in grace.protected
            if wrapper_id in self.wrappers
            and (
                self.wrappers[wrapper_id].lifecycle_done_at_ns
                or self.wrappers[wrapper_id].settled_at_ns
                or timer.due_ns
            )
            >= timer.due_ns
        ]
        if not overdue:
            return
        for wrapper in overdue:
            wrapper.context._abandon()
            wrapper.status = "abandoned"
            self.active_callbacks -= 1
            self.wrappers.pop(wrapper.wrapper_id, None)
        if self.run_fence is None and isinstance(grace.cause, Failure):
            packet_id = next(
                (
                    packet.packet_id
                    for packet in self.packets.active_packets()
                    if packet.primary is grace.cause
                ),
                None,
            )
            if packet_id is not None:
                self._commit_run_failure(packet_id, timer.due_ns)
        self.final_status = "abandoned"
        self.final_abandonment = grace.cause

    def _commit_node_route(
        self,
        activation: _Activation,
        intents: tuple[_Intent, ...],
        phase: str,
        *,
        forwarded: bool = False,
        suffix: Sequence[_EventSpec] = (),
    ) -> None:
        if self.run_fence is not None:
            return
        self._checkpoint()
        if self.run_fence is not None or self.final_status is not None:
            return
        scope = self.scopes[activation.scope_id]
        source = self.placements[activation.element_id]
        resolutions: list[tuple[str, int | None]] = []
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
                self._fail_route(
                    scope,
                    activation,
                    source,
                    "unknown",
                    intent.action,
                    phase,
                )
                return
        target_count = sum(kind == "target" for kind, _target in resolutions)
        terminal_count = len(intents) - target_count
        limit = self._batch_limit(
            scope,
            len(intents),
            target_count,
            terminal_count,
        )
        if limit is not None:
            self._fail_route(scope, activation, source, limit, None, phase)
            return
        self._checkpoint()
        if self.run_fence is not None or self.final_status is not None:
            return

        self.accounting.transitions += len(intents)
        scope.allocated_direct += target_count
        scope.live_tokens += target_count - 1
        if activation.slot_held:
            scope.active_direct -= 1
            activation.slot_held = False
        activation.status = "settled"
        specs: list[_EventSpec] = []
        for branch_index, (intent, (resolution, target)) in enumerate(
            zip(intents, resolutions, strict=True)
        ):
            if resolution == "target":
                if target is None:
                    raise RuntimeError("target route has no element")
                activation_id = self.accounting.allocate_activation_id()
                successor = _Activation(
                    target,
                    intent.value,
                    activation_id,
                    activation.activation_id,
                    scope.scope_id,
                )
                self.activations[activation_id] = successor
                scope.activation_ids.add(activation_id)
                scope.pending.append(activation_id)
                self.accounting.ready += 1
                self.accounting.peak_ready = max(
                    self.accounting.peak_ready, self.accounting.ready
                )
                transition: Transition = RoutedTransition(
                    "forward_exit" if forwarded else "route",
                    intent.action,
                    ActivationDestination(activation_id, target),
                )
                specs.append(
                    (
                        TransitionCommittedEvent,
                        TransitionCommittedPayload(
                            scope.scope_id,
                            activation.activation_id,
                            branch_index,
                            transition,
                        ),
                    )
                )
                continue
            if resolution == "end":
                terminal: Terminal = self._end_terminal(
                    intent, activation.activation_id
                )
                transition = EndTransition(
                    "forward_end" if forwarded else "end",
                    TerminalDestination(terminal.sequence),
                )
            else:
                terminal = ExitTerminal(
                    intent.action,
                    intent.value,
                    self.accounting.allocate_terminal_sequence(),
                    activation.activation_id,
                )
                transition = RoutedTransition(
                    "forward_exit" if forwarded else "route",
                    intent.action,
                    TerminalDestination(terminal.sequence),
                )
            scope.terminals.append(terminal)
            specs.extend(
                self._terminal_event_specs(
                    scope.scope_id,
                    activation.activation_id,
                    branch_index,
                    transition,
                    terminal,
                )
            )
        specs.extend(suffix)
        packet_id = activation.packet_id
        if packet_id is not None:
            self.packets.consume(packet_id)
            activation.packet_id = None
        self.publisher.publish_bundle(specs)
        self._recategorize_scope(scope)

    def _commit_flow_boundary(
        self,
        scope: _RuntimeScope,
        intents: tuple[_Intent, ...],
        phase: str,
    ) -> None:
        if self.run_fence is not None:
            return
        self._checkpoint()
        if self.run_fence is not None or self.final_status is not None:
            return
        parent = (
            None
            if scope.parent_scope_id is None
            else self.scopes[scope.parent_scope_id]
        )
        for intent in intents:
            if intent.kind == "end":
                continue
            resolved = (
                intent.action is None or intent.action in scope.definition.exits
                if parent is None
                else any(
                    link.action == intent.action for link in scope.owner_placement.links
                )
                or intent.action is None
                or intent.action in parent.definition.exits
            )
            if not resolved:
                self._fail_scope_boundary(scope, "unknown", intent.action)
                return
        limit = self._batch_limit(scope, len(intents), 0, len(intents))
        if limit is not None:
            self._fail_scope_boundary(scope, limit, None)
            return
        self._checkpoint()
        if self.run_fence is not None or self.final_status is not None:
            return
        if scope.finished_terminal_sequences is None:
            scope.finished_terminal_sequences = tuple(
                terminal.sequence for terminal in scope.terminals
            )
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
                    intent.action,
                    intent.value,
                    self.accounting.allocate_terminal_sequence(),
                    scope.owner_activation_id,
                )
                transition = RoutedTransition(
                    "route",
                    intent.action,
                    TerminalDestination(terminal.sequence),
                )
            terminals.append(terminal)
            if parent is None:
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
        scope.terminals = terminals
        if phase == "flow_recover" and scope.packet_id is not None:
            self.packets.consume(scope.packet_id)
            scope.packet_id = None
        self.publisher.publish_bundle(specs)
        scope.status = "running"
        self._complete_scope(scope)

    def _batch_limit(
        self,
        scope: _RuntimeScope,
        transition_count: int,
        target_count: int,
        terminal_count: int,
    ) -> LimitName | None:
        if (
            self.accounting.transitions + transition_count
            > self.options.max_transitions
        ):
            return "max_transitions"
        if (
            transition_count > MAX_PORTABLE_COLLECTION_LENGTH
            or len(scope.pending) + target_count > MAX_PORTABLE_COLLECTION_LENGTH
            or len(scope.terminals) + terminal_count > MAX_PORTABLE_COLLECTION_LENGTH
        ):
            return "portable_collection"
        if self.accounting.activations + target_count > self.options.max_activations:
            return "max_activations"
        if (
            scope.definition.max_activations is not None
            and scope.allocated_direct + target_count > scope.definition.max_activations
        ):
            return "scope_max_activations"
        if self.accounting.ready + target_count > self.options.max_ready:
            return "max_ready"
        if (
            target_count
            and self.accounting.next_activation_id + target_count - 1 > MAX_SAFE_INTEGER
        ) or (
            terminal_count
            and self.accounting.next_terminal_sequence + terminal_count - 1
            > MAX_SAFE_INTEGER
        ):
            return "safe_integer"
        return None

    def _fail_route(
        self,
        scope: _RuntimeScope,
        activation: _Activation,
        placement: _CompiledPlacement,
        reason: str,
        action: Action | None,
        phase: str,
    ) -> None:
        previous = (
            None
            if activation.packet_id is None
            else self.packets.get(activation.packet_id).primary
        )
        failure = self.failures.new(
            "unknown_action" if reason == "unknown" else "limit",
            scope_id=scope.scope_id,
            activation_id=activation.activation_id,
            element_id=placement.element_id,
            attempt=activation.attempt if phase == "handle" else None,
            detail=(
                UnknownActionDetail(cast(str, action))
                if reason == "unknown"
                else LimitDetail(cast(LimitName, reason))
            ),
            previous=previous,
        )
        if activation.packet_id is None:
            activation.packet_id = self.packets.create(
                failure,
                activation.input,
                _PacketOwner("activation", activation.activation_id),
            )
        else:
            self.packets.replace(activation.packet_id, failure)
        self._commit_run_failure(activation.packet_id, time.monotonic_ns())

    def _fail_scope_boundary(
        self, scope: _RuntimeScope, reason: str, action: Action | None
    ) -> None:
        previous = (
            None
            if scope.packet_id is None
            else self.packets.get(scope.packet_id).primary
        )
        failure = self.failures.new(
            "unknown_action" if reason == "unknown" else "limit",
            scope_id=scope.scope_id,
            activation_id=scope.owner_activation_id,
            element_id=scope.owner_placement.element_id,
            attempt=None,
            detail=(
                UnknownActionDetail(cast(str, action))
                if reason == "unknown"
                else LimitDetail(cast(LimitName, reason))
            ),
            previous=previous,
        )
        if scope.packet_id is None:
            scope.packet_id = self.packets.create(
                failure,
                scope.incoming_input,
                _PacketOwner("scope", scope.scope_id),
            )
        else:
            self.packets.replace(scope.packet_id, failure)
        self._commit_run_failure(scope.packet_id, time.monotonic_ns())

    def _advance_scopes(self) -> None:
        changed = True
        while changed and self.final_status is None:
            changed = False
            for scope in tuple(self.scopes.values()):
                if scope.status == "discarding" and scope.live_tokens == 0:
                    self._finish_discarded_scope(scope)
                    changed = True
                    break
                if scope.status == "failing" and scope.live_tokens == 0:
                    self._queue_flow_recovery(scope)
                    changed = True
                    break
                if (
                    scope.status == "running"
                    and scope.live_tokens == 0
                    and not scope.pending
                ):
                    self._complete_scope(scope)
                    changed = True
                    break

    def _complete_scope(self, scope: _RuntimeScope) -> None:
        if scope.status in {"completed", "failed", "cancelled", "abandoned"}:
            return
        if not scope.combined:
            scope.combined = True
            if scope.definition.combine is not None:
                if not scope.terminals:
                    raise RuntimeError("Flow combine has no terminal result")
                scope.combine_result = self._scope_result(scope)
                scope.status = "combining"
                work = self._new_work(
                    "flow_combine", scope.scope_id, scope.owner_activation_id
                )
                scope.work_id = work.work_id
                self._queue_callback(work)
                return
        scope.status = "completed"
        scope.cancellation.close()
        if scope.parent_scope_id is None:
            if not scope.terminals:
                raise RuntimeError("a completed root Flow must have a terminal")
            return
        self._forward_completed_scope(scope)

    def _forward_completed_scope(self, child: _RuntimeScope) -> None:
        if child.parent_scope_id is None:
            raise RuntimeError("root scope cannot be forwarded")
        parent = self.scopes[child.parent_scope_id]
        activation = self.activations[child.owner_activation_id]
        intents = tuple(
            _Intent(
                "end" if terminal.type == "end" else "emit",
                terminal.action if terminal.type == "exit" else None,
                terminal.output,
                terminal.has_output,
            )
            for terminal in child.terminals
        )
        finish = self._scope_finished_spec(child, "completed")
        self._commit_node_route(
            activation,
            intents,
            "forward",
            forwarded=True,
            suffix=(finish,),
        )
        self.finished_scopes.add(child.scope_id)
        self._recategorize_scope(parent)

    def _propagate_activation_failure(self, activation: _Activation) -> None:
        if activation.packet_id is None:
            raise RuntimeError("failed activation has no packet")
        scope = self.scopes[activation.scope_id]
        packet_id = activation.packet_id
        activation.packet_id = None
        self.packets.transfer(packet_id, _PacketOwner("scope", scope.scope_id))
        self._discard_activation(activation, merge_packet=False)
        self._begin_scope_failure(
            scope,
            packet_id,
            activation.activation_id,
        )

    def _begin_scope_failure(
        self,
        scope: _RuntimeScope,
        packet_id: int,
        failing_activation_id: int | None,
    ) -> None:
        if scope.status == "failing":
            if scope.packet_id is None:
                raise RuntimeError("failing scope has no packet")
            self.packets.merge(scope.packet_id, packet_id)
            return
        if scope.status in {"completed", "failed", "cancelled", "abandoned"}:
            raise RuntimeError("settled scope received a failure")
        scope.status = "failing"
        scope.packet_id = packet_id
        scope.failing_activation_id = failing_activation_id
        scope.settled_before_fence = tuple(scope.terminals)
        self.flow_scope_ready.pop(scope.scope_id, None)
        self.node_scope_ready.pop(scope.scope_id, None)
        scope.ready_queue = None

        while scope.pending:
            activation = self.activations[scope.pending.popleft()]
            self.accounting.ready -= 1
            scope.live_tokens -= 1
            activation.status = "settled"
            if activation.packet_id is not None:
                self.packets.merge(packet_id, activation.packet_id)
                activation.packet_id = None

        for activation_id in tuple(scope.activation_ids):
            activation = self.activations[activation_id]
            if activation.status not in {
                "retry_wait",
                "callback_ready",
            }:
                continue
            if activation.status == "retry_wait":
                self.timers.discard(activation.work_id)
            elif activation.work_id is not None:
                self.callback_ready.pop(activation.work_id, None)
            self._discard_activation(activation)

        descendants = [
            child_id
            for activation_id in scope.activation_ids
            if (child_id := self.activations[activation_id].child_scope_id) is not None
        ]
        while descendants:
            candidate = self.scopes[descendants.pop()]
            descendants.extend(
                child_id
                for activation_id in candidate.activation_ids
                if (child_id := self.activations[activation_id].child_scope_id)
                is not None
            )
            if candidate.status not in {
                "completed",
                "failed",
                "cancelled",
                "abandoned",
                "discarding",
            }:
                self._discard_descendant_scope(candidate)

        fenced_ns = time.monotonic_ns()
        scope.cancellation.cancel("scope_failed", fenced_ns=fenced_ns)
        primary = self.packets.get(packet_id).primary
        self._publish_scope_fence(scope, primary)
        protected = {
            wrapper.wrapper_id
            for wrapper in self.wrappers.values()
            if wrapper.status in {"invoked", "selecting_retry"}
            and self._scope_descends(wrapper.work.scope_id, scope.scope_id)
        }
        self._arm_grace(protected, primary, fenced_ns)

    def _discard_descendant_scope(self, scope: _RuntimeScope) -> None:
        scope.status = "discarding"
        self.flow_scope_ready.pop(scope.scope_id, None)
        self.node_scope_ready.pop(scope.scope_id, None)
        scope.ready_queue = None
        while scope.pending:
            activation = self.activations[scope.pending.popleft()]
            self.accounting.ready -= 1
            scope.live_tokens -= 1
            activation.status = "settled"
        if scope.work_id is not None:
            self.callback_ready.pop(scope.work_id, None)
            scope.work_id = None
        for activation_id in tuple(scope.activation_ids):
            activation = self.activations[activation_id]
            if activation.status == "retry_wait":
                self.timers.discard(activation.work_id)
                self._discard_activation(activation)
            elif activation.status == "callback_ready":
                if activation.work_id is not None:
                    self.callback_ready.pop(activation.work_id, None)
                self._discard_activation(activation)

    def _finish_discarded_scope(self, scope: _RuntimeScope) -> None:
        scope.status = "cancelled"
        scope.cancellation.close()
        if scope.parent_scope_id is None:
            return
        if scope.scope_id not in self.finished_scopes:
            self.publisher.publish_bundle(
                (self._scope_finished_spec(scope, "cancelled"),)
            )
            self.finished_scopes.add(scope.scope_id)
        owner = self.activations[scope.owner_activation_id]
        self._discard_activation(owner)

    def _discard_activation(
        self, activation: _Activation, *, merge_packet: bool = True
    ) -> None:
        if activation.status == "settled":
            return
        scope = self.scopes[activation.scope_id]
        if activation.slot_held:
            scope.active_direct -= 1
            activation.slot_held = False
        scope.live_tokens -= 1
        activation.status = "settled"
        if activation.packet_id is not None:
            if (
                merge_packet
                and scope.status == "failing"
                and scope.packet_id is not None
            ):
                self.packets.merge(scope.packet_id, activation.packet_id)
            activation.packet_id = None
        self._recategorize_scope(scope)

    def _queue_flow_recovery(self, scope: _RuntimeScope) -> None:
        if scope.status != "failing" or scope.work_id is not None:
            return
        if scope.definition.recover is None:
            self._propagate_scope_failure(scope)
            return
        scope.status = "recovering"
        work = self._new_work("flow_recover", scope.scope_id, scope.owner_activation_id)
        scope.work_id = work.work_id
        self._queue_callback(work)

    def _propagate_scope_failure(self, scope: _RuntimeScope) -> None:
        current = scope
        while True:
            if current.packet_id is None:
                raise RuntimeError("failed scope has no packet")
            packet_id = current.packet_id
            current.work_id = None
            current.status = "failed"
            current.cancellation.close()
            if current.parent_scope_id is None:
                self._commit_run_failure(packet_id, time.monotonic_ns())
                return
            self.publisher.publish_bundle(
                (self._scope_finished_spec(current, "failed"),)
            )
            self.finished_scopes.add(current.scope_id)
            parent_activation = self.activations[current.owner_activation_id]
            current.packet_id = None
            self.packets.transfer(
                packet_id,
                _PacketOwner("activation", parent_activation.activation_id),
            )
            parent_activation.packet_id = packet_id
            parent = self.scopes[parent_activation.scope_id]
            self._propagate_activation_failure(parent_activation)
            if parent.live_tokens != 0:
                return
            if parent.definition.recover is not None:
                self._queue_flow_recovery(parent)
                return
            current = parent

    def _scope_descends(self, candidate_id: int, ancestor_id: int) -> bool:
        current_id: int | None = candidate_id
        while current_id is not None:
            if current_id == ancestor_id:
                return True
            current_id = self.scopes[current_id].parent_scope_id
        return False

    def _commit_run_failure(self, packet_id: int, time_ns: int) -> None:
        if self.final_status is not None or self.run_fence is not None:
            return
        controlling = self.packets.get(packet_id)
        self._capture_drained_packet_references()
        drain = self.packets.drain(packet_id)
        if drain.primary is None:
            raise RuntimeError("failure drain has no primary")
        self.run_fence = "failed"
        self.final_failure = drain.primary
        self.final_suppressed = drain.suppressed
        self._stop_admission()
        self.cancellation.cancel("run_failed", fenced_ns=time_ns)
        specs: list[_EventSpec] = []
        record = self._failure_record_spec(controlling.primary)
        if record is not None:
            specs.append(record)
        specs.extend(
            (
                (
                    FailureFencedEvent,
                    FailureFencedPayload(RunFenceTarget(), controlling.primary),
                ),
                (
                    CancellationFencedEvent,
                    CancellationFencedPayload(RunFenceTarget(), "run_failed", False),
                ),
            )
        )
        self.publisher.mark_run_cancellation_published()
        self.publisher.publish_bundle(specs)
        protected = {
            wrapper.wrapper_id
            for wrapper in self.wrappers.values()
            if wrapper.status in {"invoked", "selecting_retry"}
        }
        self._arm_grace(protected, controlling.primary, time_ns)
        self._force_terminal_if_quiet()

    def _commit_run_cancellation(
        self,
        reason: object,
        *,
        deadline: bool,
        time_ns: int,
    ) -> None:
        if self.final_status is not None or self.run_fence is not None:
            return
        self._capture_drained_packet_references()
        drain = self.packets.drain(None)
        self.run_fence = "cancelled"
        self.final_cancellation = CancellationInfo(reason, deadline)
        self.final_suppressed = drain.suppressed
        self._stop_admission()
        self.cancellation.cancel(reason, deadline=deadline, fenced_ns=time_ns)
        self.publisher.publish_run_cancellation(reason, deadline)
        protected = {
            wrapper.wrapper_id
            for wrapper in self.wrappers.values()
            if wrapper.status in {"invoked", "selecting_retry"}
        }
        self._arm_grace(
            protected,
            cast(CancellationInfo, self.final_cancellation),
            time_ns,
        )
        self._force_terminal_if_quiet()

    def _capture_drained_packet_references(self) -> None:
        active = {
            packet.packet_id: packet.primary for packet in self.packets.active_packets()
        }
        for wrapper in self.wrappers.values():
            packet_id = self._packet_for_work(wrapper.work)
            if packet_id is not None:
                wrapper.drained_packet_primary = active.get(packet_id)

    def _stop_admission(self) -> None:
        self.flow_scope_ready.clear()
        self.node_scope_ready.clear()
        self.callback_ready.clear()
        retry_ids = [timer.timer_id for timer in self.timers if timer.kind == "retry"]
        for timer_id in retry_ids:
            self.timers.discard(timer_id)
        for scope in self.scopes.values():
            if scope.status in {"completed", "failed", "cancelled", "abandoned"}:
                continue
            while scope.pending:
                activation = self.activations[scope.pending.popleft()]
                self.accounting.ready -= 1
                scope.live_tokens -= 1
                activation.status = "settled"
            for activation_id in scope.activation_ids:
                activation = self.activations[activation_id]
                if activation.status in {"retry_wait", "callback_ready"}:
                    if activation.slot_held:
                        scope.active_direct -= 1
                        activation.slot_held = False
                    scope.live_tokens -= 1
                    activation.status = "settled"

    def _force_terminal_if_quiet(self) -> None:
        if self.final_status is not None or self.active_callbacks != 0:
            return
        if self.run_fence == "failed":
            self.final_status = "failed"
        elif self.run_fence == "cancelled":
            self.final_status = "cancelled"

    def _maybe_finish_run(self) -> None:
        self._force_terminal_if_quiet()
        if self.final_status is not None or self.run_fence is not None:
            return
        root = self.root
        if root.status != "completed" or self.active_callbacks or self.callback_ready:
            return
        if any(timer.kind != "run_deadline" for timer in self.timers):
            return
        self._checkpoint()
        if self.run_fence is not None or self.final_status is not None:
            return
        self.packets.require_empty()
        self.timers.clear()
        self.final_status = "completed"

    def _finish_result(self) -> RunResult[Any]:
        if self._terminal_result is not None:
            return self._terminal_result
        if self.final_status is None:
            self._force_terminal_if_quiet()
        status = self.final_status
        if status is None:
            raise RuntimeError("run result requested before terminal settlement")
        stats = self.accounting.stats(self.peak_callbacks)
        scope_status = status
        specs: list[_EventSpec] = []
        for scope in sorted(
            self.scopes.values(),
            key=lambda candidate: (-candidate.depth, candidate.scope_id),
        ):
            if scope.scope_id in self.finished_scopes:
                continue
            resolved = (
                "completed"
                if scope.status == "completed" and status == "completed"
                else scope_status
            )
            specs.append(self._scope_finished_spec(scope, resolved))
            self.finished_scopes.add(scope.scope_id)
        specs.append((RunFinishedEvent, RunFinishedPayload(status)))
        self.publisher.mark_terminal()
        self.publisher.publish_bundle(specs)
        diagnostics = self.publisher.diagnostics
        terminals = tuple(self.root.terminals)
        suppressed = self.final_suppressed
        if status == "completed":
            result: RunResult[Any] = Completed(
                "completed",
                self.state,
                cast(NonEmptyTerminals, terminals),
                stats,
                diagnostics,
            )
        elif status == "failed":
            if self.final_failure is None:
                raise RuntimeError("failed run has no failure")
            result = Failed(
                "failed",
                self.state,
                terminals,
                self.final_failure,
                suppressed,
                stats,
                diagnostics,
            )
        elif status == "cancelled":
            if self.final_cancellation is None:
                raise RuntimeError("cancelled run has no cancellation")
            result = Cancelled(
                "cancelled",
                self.state,
                terminals,
                self.final_cancellation,
                suppressed,
                stats,
                diagnostics,
            )
        else:
            if self.final_abandonment is None:
                raise RuntimeError("abandoned run has no cause")
            result = Abandoned(
                "abandoned",
                self.state,
                terminals,
                self.final_abandonment,
                suppressed,
                stats,
                diagnostics,
            )
        self._terminal_result = result
        return result

    def _failure_record_spec(self, failure: Failure) -> _EventSpec | None:
        if failure.failure_id in self.recorded_failures:
            return None
        self.recorded_failures.add(failure.failure_id)
        return FailureRecordedEvent, FailureRecordedPayload(failure)

    def _publish_failure_recorded(self, failure: Failure) -> None:
        spec = self._failure_record_spec(failure)
        if spec is not None:
            self.publisher.publish_bundle((spec,))

    def _publish_callback_finished(
        self,
        wrapper: _CallbackWrapper,
        disposition: CallbackOutcomeDisposition
        | FailureDisposition
        | DiscardedDisposition,
        *,
        failures: Sequence[Failure] = (),
    ) -> None:
        work = wrapper.work
        activation = self.activations.get(work.activation_id)
        specs = [
            spec
            for failure in failures
            if (spec := self._failure_record_spec(failure)) is not None
        ]
        specs.append(
            (
                CallbackFinishedEvent,
                CallbackFinishedPayload(
                    work.scope_id,
                    work.activation_id,
                    work.kind,
                    activation.attempt
                    if work.kind == "handle" and activation
                    else None,
                    disposition,
                ),
            )
        )
        self.publisher.publish_bundle(specs)

    def _publish_scope_fence(self, scope: _RuntimeScope, failure: Failure) -> None:
        if scope.scope_id in self.scope_fences:
            raise RuntimeError("scope failure fence published twice")
        self.scope_fences.add(scope.scope_id)
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
                        ScopeFenceTarget(scope.scope_id), "scope_failed", False
                    ),
                ),
            )
        )
        self.publisher.publish_bundle(specs)

    def _publish_attempt_fence(
        self, wrapper: _CallbackWrapper, failure: Failure
    ) -> None:
        work = wrapper.work
        activation = self.activations[work.activation_id]
        key = (work.scope_id, work.activation_id, activation.attempt)
        if key in self.attempt_fences:
            raise RuntimeError("attempt fence published twice")
        self.attempt_fences.add(key)
        specs: list[_EventSpec] = []
        record = self._failure_record_spec(failure)
        if record is not None:
            specs.append(record)
        specs.append(
            (
                CancellationFencedEvent,
                CancellationFencedPayload(
                    AttemptFenceTarget(*key), "attempt_timeout", False
                ),
            )
        )
        self.publisher.publish_bundle(specs)

    def _scope_finished_spec(
        self,
        scope: _RuntimeScope,
        status: Literal["completed", "failed", "cancelled", "abandoned"],
    ) -> _EventSpec:
        return (
            ScopeFinishedEvent,
            ScopeFinishedPayload(
                scope.scope_id,
                status,
                (
                    scope.finished_terminal_sequences
                    if scope.finished_terminal_sequences is not None
                    else tuple(terminal.sequence for terminal in scope.terminals)
                ),
            ),
        )

    def _scope_result(self, scope: _RuntimeScope) -> ScopeResult:
        return ScopeResult(
            cast(NonEmptyTerminals, tuple(scope.terminals)),
            tuple(
                terminal.output for terminal in scope.terminals if terminal.has_output
            ),
        )

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
        metadata: TerminalMetadata = (
            EndTerminalMetadata(terminal.has_output)
            if terminal.type == "end"
            else ExitTerminalMetadata(terminal.action)
        )
        return (
            (
                TransitionCommittedEvent,
                TransitionCommittedPayload(
                    scope_id, source_activation_id, branch_index, transition
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

    def _end_terminal(self, intent: _Intent, source_activation_id: int) -> EndTerminal:
        return EndTerminal(
            intent.present,
            intent.value if intent.present else None,
            self.accounting.allocate_terminal_sequence(),
            source_activation_id,
        )
