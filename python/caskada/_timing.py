# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Cancellation, callback permits, deadlines, and callback races.
from __future__ import annotations

import asyncio
import inspect
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import (
    Any,
    cast,
)

from ._contracts import (
    _MAX_HOST_TIMER_DELAY_MS,
    CancellationInfo,
    Failure,
)
from ._failures import (
    _FailureFence,
    _ProducedFailure,
    _RunAbandoned,
    _RunCancelled,
)


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


class _CallbackController:
    """Owns callback permits and their concurrency accounting."""

    def __init__(self, limit: int, cancellation: _CancellationSource) -> None:
        self._gate = _CallbackGate(limit, cancellation)
        self.active = 0
        self.peak = 0

    async def acquire(
        self,
        *,
        ready_callback: bool,
        cancellation: _CancellationSource,
        scope_id: int | None = None,
    ) -> None:
        await self._gate.acquire(
            ready_callback=ready_callback,
            cancellation=cancellation,
            scope_id=scope_id,
        )
        self.active += 1
        self.peak = max(self.peak, self.active)

    def release(self) -> None:
        if self.active <= 0:
            raise RuntimeError("callback accounting lost its owner")
        self.active -= 1
        self._gate.release()


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


class _RunCancellation:
    """Owns the run deadline and the controlling cancellation fence."""

    def __init__(self, source, deadline, observer) -> None:
        self.source = source
        self.deadline = deadline
        self.observer = observer

    def commit_deadline_if_due(self) -> None:
        if (
            not self.source.cancelled
            and self.deadline is not None
            and self.deadline.due()
        ):
            self.source.cancel("deadline_exceeded", deadline=True)

    def check(self, suppressed=()) -> None:
        if self.observer.failure_fence is not None:
            raise self.observer.failure_fence
        self.commit_deadline_if_due()
        if self.source.cancelled:
            self.observer._publish_run_cancellation_if_needed()
            raise _RunCancelled(suppressed)

    def check_scope(self, scope, suppressed=()) -> None:
        self.check(suppressed)
        if not scope.cancellation.cancelled:
            return
        reason = scope.cancellation.reason
        if isinstance(reason, _FailureFence):
            raise reason.produced
        raise _RunCancelled(suppressed)


def _consume_callback_completion(task: asyncio.Task[_CallbackCompletion]) -> None:
    try:
        task.result()
    except BaseException:
        pass


@dataclass(frozen=True, slots=True)
class _CallbackCompletion:
    result: object
    error: BaseException | None
    settled_ns: int


class _CallbackExecutor:
    """Owns callback races, deadlines, cancellation grace, and abandonment."""

    def __init__(self, cancellation, options, run_cancellation, observer) -> None:
        self.cancellation = cancellation
        self.options = options
        self.run_deadline = run_cancellation.deadline
        self.run_cancellation = run_cancellation
        self.observer = observer

    def _check_cancelled(self, suppressed=()) -> None:
        self.run_cancellation.check(suppressed)

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
        except BaseException as error:
            return _CallbackCompletion(None, error, time.monotonic_ns())

    async def _wait_until(self, deadline: _Deadline) -> None:
        while True:
            remaining = deadline.remaining_ms()
            if remaining == 0:
                return
            await asyncio.sleep(min(remaining, _MAX_HOST_TIMER_DELAY_MS) / 1_000)

    async def _await_lifecycle_callback(
        self,
        context: Any,
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
            self.observer._publish_attempt_timeout(context, failure)
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
                self.observer._publish_attempt_timeout(context, timeout_primary)

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
                    if self.observer.failure_fence is not None:
                        raise _RunAbandoned(
                            self.observer.failure_fence.failure,
                            self.observer.failure_fence.suppressed,
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
                if self.observer.failure_fence is not None:
                    raise _RunAbandoned(
                        self.observer.failure_fence.failure,
                        self.observer.failure_fence.suppressed,
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
            if self.observer.failure_fence is not None:
                raise fenced_produced(self.observer.failure_fence, completion)
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
