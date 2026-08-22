# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2026, Victor Duarte
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, TypeVar

from ._context import _Context, _Intent, _InvalidOutcome
from ._contracts import (
    Action,
    Completed,
    EndTerminal,
    ExitTerminal,
    Failed,
    Failure,
    FailureKind,
    RunResult,
    ScopeFailure,
    ScopeResult,
    Terminal,
)
from ._graph import (
    _CompiledPlacement,
    _CompiledScope,
    _CompiledSnapshot,
)

StateT = TypeVar("StateT")
_MISSING = object()


def _start(snapshot: _CompiledSnapshot, state: StateT) -> _Handle:
    loop = asyncio.get_running_loop()
    task = loop.create_task(_Run(snapshot, state).execute())
    return _Handle(task)


class _Run:
    def __init__(self, snapshot: _CompiledSnapshot, state: object) -> None:
        self.snapshot = snapshot
        self.state = state
        self.next_activation_id = 1  # The root Flow owns activation 1.
        self.next_failure_id = 0
        self.next_scope_id = 0
        self.next_terminal_sequence = 0

    async def execute(self) -> RunResult[Any]:
        outcome = await self._run_scope(1, 1, None)
        if isinstance(outcome, _ScopeFailed):
            return Failed(self.state, outcome.terminals, outcome.failure)
        return Completed(self.state, outcome.terminals)

    async def _run_scope(
        self,
        compiled_scope_id: int,
        owner_activation_id: int,
        input: object,
    ) -> _ScopeSuccess | _ScopeFailed:
        scope = self.snapshot.scope(compiled_scope_id)
        runtime_scope_id = self._new_scope_id()
        queue = [self._activation(scope.entry_element_id, input)]
        terminals: list[Terminal] = []
        started = 0
        failure: _FailureSignal | None = None

        while queue and failure is None:
            if scope.max_activations is not None and started >= scope.max_activations:
                blocked = queue[0]
                failure = _FailureSignal(
                    self._failure(
                        "activation_limit",
                        f"Flow {scope.name!r} exceeded max_activations",
                        runtime_scope_id,
                        blocked.activation_id,
                        blocked.element_id,
                    ),
                    blocked.activation_id,
                    blocked.input,
                )
                break

            width = min(scope.concurrency, len(queue))
            if scope.max_activations is not None:
                width = min(width, scope.max_activations - started)
            batch, queue = queue[:width], queue[width:]
            started += len(batch)
            outcomes = await asyncio.gather(
                *(self._run_activation(scope, runtime_scope_id, item) for item in batch)
            )
            for activation, outcome in zip(batch, outcomes, strict=True):
                if isinstance(outcome, _FailureSignal):
                    if failure is None:
                        failure = outcome
                    continue
                for item in outcome.items:
                    if isinstance(item, (EndTerminal, ExitTerminal)):
                        terminals.append(item)
                    elif failure is None:
                        queue.append(self._activation(item.element_id, item.input))

        ordered = tuple(sorted(terminals, key=lambda terminal: terminal.sequence))
        if failure is not None:
            return await self._recover_scope(
                scope,
                runtime_scope_id,
                owner_activation_id,
                failure,
                ordered,
            )

        if scope.combine is None:
            return _ScopeSuccess(ordered)
        result = ScopeResult(ordered)
        callback = await self._callback(scope.combine, input, result)
        if isinstance(callback, Exception):
            signal = self._callback_failure(
                callback,
                "flow_combine",
                "Flow combine failed",
                runtime_scope_id,
                owner_activation_id,
                scope.owner_element_id,
                None,
                input,
                result=result,
            )
            return await self._recover_scope(
                scope,
                runtime_scope_id,
                owner_activation_id,
                signal,
                ordered,
            )
        if not callback:
            return _ScopeSuccess(ordered)

        transformed = self._boundary_terminals(callback, owner_activation_id)
        invalid = self._invalid_root_exit(scope, transformed, runtime_scope_id)
        if invalid is not None:
            return await self._recover_scope(
                scope,
                runtime_scope_id,
                owner_activation_id,
                invalid,
                ordered,
            )
        return _ScopeSuccess(transformed)

    async def _run_activation(
        self,
        scope: _CompiledScope,
        runtime_scope_id: int,
        activation: _Activation,
    ) -> _Success | _FailureSignal:
        placement = self.snapshot.placement(activation.element_id)
        if placement.kind == "flow":
            if placement.owned_scope_id is None:
                raise RuntimeError("compiled Flow has no owned scope")
            # ponytail: recurse by Flow depth; use an explicit stack only if real
            # workflows reach Python's recursion limit.
            child = await self._run_scope(
                placement.owned_scope_id,
                activation.activation_id,
                activation.input,
            )
            if isinstance(child, _ScopeFailed):
                return _FailureSignal(
                    child.failure, activation.activation_id, activation.input
                )
            return self._route_child(
                scope, runtime_scope_id, placement, activation, child.terminals
            )

        intents = await self._run_node(placement, runtime_scope_id, activation)
        if isinstance(intents, _FailureSignal):
            return intents
        return self._route_intents(
            scope, runtime_scope_id, placement, activation, intents
        )

    async def _run_node(
        self,
        placement: _CompiledPlacement,
        scope_id: int,
        activation: _Activation,
    ) -> tuple[_Intent, ...] | _FailureSignal:
        if placement.handler is None or placement.retry is None:
            raise RuntimeError("compiled Node is incomplete")
        previous: Failure | None = None

        for attempt in range(1, placement.retry.max_attempts + 1):
            callback = await self._callback(placement.handler, activation.input)
            if not isinstance(callback, Exception):
                return callback or (_Intent("emit", None, activation.input, True),)

            kind: FailureKind = (
                "invalid_outcome"
                if isinstance(callback, _InvalidOutcome)
                else "handler"
            )
            failure = self._failure(
                kind,
                str(callback),
                scope_id,
                activation.activation_id,
                placement.element_id,
                attempt,
                callback,
                previous,
            )
            if kind == "handler" and attempt < placement.retry.max_attempts:
                policy_failure = self._retry(placement, attempt, failure)
                if isinstance(policy_failure, Failure):
                    return _FailureSignal(
                        policy_failure, activation.activation_id, activation.input
                    )
                if policy_failure is not None:
                    if policy_failure:
                        await asyncio.sleep(policy_failure / 1000)
                    previous = failure
                    continue
            return await self._recover_node(placement, scope_id, activation, failure)

        raise RuntimeError("retry loop did not return")

    def _retry(
        self,
        placement: _CompiledPlacement,
        attempt: int,
        failure: Failure,
    ) -> int | None | Failure:
        if placement.retry is None:
            raise RuntimeError("compiled Node has no retry policy")
        try:
            should_retry = placement.retry.should_retry(failure)
            if type(should_retry) is not bool:
                raise TypeError("should_retry must return bool")
            if not should_retry:
                return None
            delay = placement.retry.delay_ms
            delay_ms = delay(attempt, failure) if callable(delay) else delay
            if (
                not isinstance(delay_ms, int)
                or isinstance(delay_ms, bool)
                or delay_ms < 0
            ):
                raise TypeError("delay_ms must return a nonnegative integer")
            return delay_ms
        except Exception as cause:  # noqa: BLE001 - retry policy is user code
            return self._failure(
                "retry_policy",
                str(cause),
                failure.scope_id,
                failure.activation_id,
                failure.element_id,
                failure.attempt,
                cause,
                failure,
            )

    async def _recover_node(
        self,
        placement: _CompiledPlacement,
        scope_id: int,
        activation: _Activation,
        failure: Failure,
    ) -> tuple[_Intent, ...] | _FailureSignal:
        if placement.recover is None:
            return _FailureSignal(failure, activation.activation_id, activation.input)
        callback = await self._callback(placement.recover, activation.input, failure)
        if isinstance(callback, Exception):
            kind: FailureKind = (
                "invalid_outcome"
                if isinstance(callback, _InvalidOutcome)
                else "node_recovery"
            )
            replacement = self._failure(
                kind,
                str(callback),
                scope_id,
                activation.activation_id,
                placement.element_id,
                None,
                callback,
                failure,
            )
            return _FailureSignal(
                replacement, activation.activation_id, activation.input
            )
        if not callback:
            return _FailureSignal(failure, activation.activation_id, activation.input)
        return callback

    async def _recover_scope(
        self,
        scope: _CompiledScope,
        runtime_scope_id: int,
        owner_activation_id: int,
        signal: _FailureSignal,
        terminals: tuple[Terminal, ...],
    ) -> _ScopeSuccess | _ScopeFailed:
        if scope.recover is None:
            return _ScopeFailed(terminals, signal.failure)
        scope_failure = ScopeFailure(
            signal.failure,
            terminals,
            signal.result,
            signal.activation_id,
        )
        callback = await self._callback(scope.recover, signal.input, scope_failure)
        if isinstance(callback, Exception):
            kind: FailureKind = (
                "invalid_outcome"
                if isinstance(callback, _InvalidOutcome)
                else "flow_recovery"
            )
            return _ScopeFailed(
                terminals,
                self._failure(
                    kind,
                    str(callback),
                    runtime_scope_id,
                    owner_activation_id,
                    scope.owner_element_id,
                    None,
                    callback,
                    signal.failure,
                ),
            )
        if not callback:
            return _ScopeFailed(terminals, signal.failure)

        transformed = self._boundary_terminals(callback, owner_activation_id)
        invalid = self._invalid_root_exit(scope, transformed, runtime_scope_id)
        if invalid is not None:
            return _ScopeFailed(terminals, invalid.failure)
        return _ScopeSuccess(transformed)

    async def _callback(
        self,
        callback: Any,
        input: object,
        extra: object = _MISSING,
    ) -> tuple[_Intent, ...] | Exception:
        context = _Context(self.state, input)
        try:
            value = callback(context) if extra is _MISSING else callback(context, extra)
            if inspect.isawaitable(value):
                value = await value
            if value is not None:
                raise _InvalidOutcome("callbacks must return None")
            return context.close()
        except Exception as cause:  # noqa: BLE001 - callback is user code
            context.close()
            return cause

    def _route_intents(
        self,
        scope: _CompiledScope,
        scope_id: int,
        placement: _CompiledPlacement,
        activation: _Activation,
        intents: tuple[_Intent, ...],
    ) -> _Success | _FailureSignal:
        destinations: list[tuple[_Intent, int | None]] = []
        for intent in intents:
            if intent.kind == "end":
                destinations.append((intent, None))
                continue
            target = next(
                (
                    link.target_element_id
                    for link in placement.links
                    if link.action == intent.action
                ),
                None,
            )
            if (
                target is None
                and intent.action is not None
                and intent.action not in scope.exits
            ):
                return _FailureSignal(
                    self._failure(
                        "unknown_action",
                        f"unknown action {intent.action!r} from {placement.name!r}",
                        scope_id,
                        activation.activation_id,
                        placement.element_id,
                    ),
                    activation.activation_id,
                    activation.input,
                )
            destinations.append((intent, target))

        items: list[Terminal | _Next] = []
        for intent, target in destinations:
            if intent.kind == "end":
                items.append(
                    self._end_terminal(
                        intent.has_value, intent.value, activation.activation_id
                    )
                )
            elif target is not None:
                items.append(_Next(target, intent.value))
            else:
                items.append(
                    self._exit_terminal(
                        intent.action, intent.value, activation.activation_id
                    )
                )
        return _Success(tuple(items))

    def _route_child(
        self,
        scope: _CompiledScope,
        scope_id: int,
        placement: _CompiledPlacement,
        activation: _Activation,
        terminals: tuple[Terminal, ...],
    ) -> _Success | _FailureSignal:
        items: list[Terminal | _Next] = []
        for terminal in terminals:
            if isinstance(terminal, EndTerminal):
                items.append(terminal)
                continue
            intent = _Intent("emit", terminal.action, terminal.output, True)
            routed = self._route_intents(
                scope, scope_id, placement, activation, (intent,)
            )
            if isinstance(routed, _FailureSignal):
                return routed
            items.extend(routed.items)
        return _Success(tuple(items))

    def _boundary_terminals(
        self,
        intents: tuple[_Intent, ...],
        source_activation_id: int,
    ) -> tuple[Terminal, ...]:
        terminals: list[Terminal] = []
        for intent in intents:
            if intent.kind == "end":
                terminals.append(
                    self._end_terminal(
                        intent.has_value, intent.value, source_activation_id
                    )
                )
            else:
                terminals.append(
                    self._exit_terminal(
                        intent.action, intent.value, source_activation_id
                    )
                )
        return tuple(terminals)

    def _invalid_root_exit(
        self,
        scope: _CompiledScope,
        terminals: tuple[Terminal, ...],
        runtime_scope_id: int,
    ) -> _FailureSignal | None:
        if scope.parent_scope_id is not None:
            return None
        for terminal in terminals:
            if (
                isinstance(terminal, ExitTerminal)
                and terminal.action is not None
                and terminal.action not in scope.exits
            ):
                return _FailureSignal(
                    self._failure(
                        "unknown_action",
                        f"unknown root exit {terminal.action!r}",
                        runtime_scope_id,
                        terminal.source_activation_id,
                        scope.owner_element_id,
                    ),
                    terminal.source_activation_id,
                    terminal.output,
                )
        return None

    def _callback_failure(
        self,
        cause: Exception,
        ordinary_kind: FailureKind,
        message: str,
        scope_id: int,
        activation_id: int,
        element_id: int,
        attempt: int | None,
        input: object,
        *,
        result: ScopeResult | None = None,
    ) -> _FailureSignal:
        kind: FailureKind = (
            "invalid_outcome" if isinstance(cause, _InvalidOutcome) else ordinary_kind
        )
        return _FailureSignal(
            self._failure(
                kind,
                str(cause) if isinstance(cause, _InvalidOutcome) else message,
                scope_id,
                activation_id,
                element_id,
                attempt,
                cause,
            ),
            activation_id,
            input,
            result,
        )

    def _failure(
        self,
        kind: FailureKind,
        message: str,
        scope_id: int,
        activation_id: int | None,
        element_id: int | None,
        attempt: int | None = None,
        cause: BaseException | None = None,
        previous: Failure | None = None,
    ) -> Failure:
        self.next_failure_id += 1
        return Failure(
            self.next_failure_id,
            kind,
            message,
            cause,
            scope_id,
            activation_id,
            element_id,
            attempt,
            previous,
        )

    def _activation(self, element_id: int, input: object) -> _Activation:
        self.next_activation_id += 1
        return _Activation(self.next_activation_id, element_id, input)

    def _new_scope_id(self) -> int:
        self.next_scope_id += 1
        return self.next_scope_id

    def _end_terminal(
        self, has_output: bool, output: object, source_activation_id: int
    ) -> EndTerminal:
        self.next_terminal_sequence += 1
        return EndTerminal(
            has_output,
            output,
            self.next_terminal_sequence,
            source_activation_id,
        )

    def _exit_terminal(
        self, action: Action | None, output: object, source_activation_id: int
    ) -> ExitTerminal:
        self.next_terminal_sequence += 1
        return ExitTerminal(
            action,
            output,
            self.next_terminal_sequence,
            source_activation_id,
        )


@dataclass(frozen=True, slots=True)
class _Activation:
    activation_id: int
    element_id: int
    input: object


@dataclass(frozen=True, slots=True)
class _Next:
    element_id: int
    input: object


@dataclass(frozen=True, slots=True)
class _Success:
    items: tuple[Terminal | _Next, ...]


@dataclass(frozen=True, slots=True)
class _FailureSignal:
    failure: Failure
    activation_id: int | None
    input: object
    result: ScopeResult | None = None


@dataclass(frozen=True, slots=True)
class _ScopeSuccess:
    terminals: tuple[Terminal, ...]


@dataclass(frozen=True, slots=True)
class _ScopeFailed:
    terminals: tuple[Terminal, ...]
    failure: Failure


class _Handle:
    def __init__(self, task: asyncio.Task[RunResult[Any]]) -> None:
        self._task = task

    def done(self) -> bool:
        return self._task.done()

    async def result(self) -> RunResult[Any]:
        return await self._task
