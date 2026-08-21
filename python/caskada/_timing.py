# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Passive cancellation and timer primitives for the iterative scheduler.
from __future__ import annotations

import asyncio
import heapq
import inspect
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal


class _CancellationSource:
    """One cooperative token in an iteratively-signalled cancellation tree."""

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
        self._event = asyncio.Event()
        self._fenced_ns: int | None = None
        self._parent = parent
        self._reason: Any = None
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
        committed_ns = time.monotonic_ns() if fenced_ns is None else fenced_ns
        pending = [self]
        committed: list[_CancellationSource] = []
        while pending:
            source = pending.pop()
            if source._cancelled:
                continue
            source._cancelled = True
            source._reason = reason
            source._deadline = deadline
            source._fenced_ns = committed_ns
            committed.append(source)
            pending.extend(source._children)
        for source in committed:
            source._event.set()
        return True

    def close(self) -> None:
        if self._parent is not None:
            self._parent._children.discard(self)
            self._parent = None


def _dispose_invalid_sync_result(value: object) -> None:
    if inspect.iscoroutine(value):
        try:
            value.close()
        except BaseException:
            pass
        return
    if isinstance(value, asyncio.Future):
        if value.done():
            _consume_future_exception(value)
        else:
            try:
                value.add_done_callback(_consume_future_exception)
            except BaseException:
                pass
        return
    if inspect.isasyncgen(value) or not inspect.isawaitable(value):
        return
    try:
        iterator = value.__await__()
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
    except BaseException:
        pass


def _consume_future_exception(future: asyncio.Future[Any]) -> None:
    try:
        future.exception()
    except BaseException:
        pass


_TimerKind = Literal["run_deadline", "attempt", "grace", "retry"]
_TIMER_PRIORITY: dict[_TimerKind, int] = {
    "run_deadline": 0,
    "attempt": 1,
    "grace": 2,
    "retry": 3,
}


@dataclass(frozen=True, slots=True)
class _Timer:
    timer_id: int
    kind: _TimerKind
    due_ns: int
    priority: int
    sequence: int
    owner_id: int

    @property
    def key(self) -> tuple[int, int, int]:
        return self.due_ns, self.priority, self.sequence


class _TimerHeap:
    __slots__ = ("_heap", "_next_id", "_next_sequence", "_timers")

    def __init__(self) -> None:
        self._heap: list[tuple[tuple[int, int, int], int]] = []
        self._timers: dict[int, _Timer] = {}
        self._next_id = 1
        self._next_sequence = 1

    def __bool__(self) -> bool:
        return bool(self._timers)

    def __iter__(self) -> Iterator[_Timer]:
        return iter(self._timers.values())

    def add(self, kind: _TimerKind, due_ns: int, owner_id: int) -> int:
        timer_id = self._next_id
        self._next_id += 1
        timer = _Timer(
            timer_id,
            kind,
            due_ns,
            _TIMER_PRIORITY[kind],
            self._next_sequence,
            owner_id,
        )
        self._next_sequence += 1
        self._timers[timer_id] = timer
        heapq.heappush(self._heap, (timer.key, timer_id))
        return timer_id

    def get(self, timer_id: int) -> _Timer:
        try:
            return self._timers[timer_id]
        except KeyError:
            raise RuntimeError("timer is not live")

    def remove(self, timer_id: int) -> _Timer:
        try:
            return self._timers.pop(timer_id)
        except KeyError:
            raise RuntimeError("timer is not live")

    def discard(self, timer_id: int | None) -> None:
        if timer_id is not None:
            self._timers.pop(timer_id, None)

    def peek(self) -> _Timer | None:
        while self._heap:
            _, timer_id = self._heap[0]
            timer = self._timers.get(timer_id)
            if timer is not None:
                return timer
            heapq.heappop(self._heap)
        return None

    def pop_due(self, now_ns: int) -> list[_Timer]:
        due: list[_Timer] = []
        while (timer := self.peek()) is not None and timer.due_ns <= now_ns:
            heapq.heappop(self._heap)
            due.append(self._timers.pop(timer.timer_id))
        return due

    def clear(self) -> None:
        self._heap.clear()
        self._timers.clear()
