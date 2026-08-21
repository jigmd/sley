from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from caskada import (
    Context,
    Failure,
    Flow,
    RetryPolicy,
    RunOptions,
    RunResult,
    ScopeFailure,
    node,
)

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "scheduling-cancellation.json"
CANCEL_REASON = "fixture-cancel"


class FixtureError(Exception):
    pass


async def _gated_width(
    width: int,
    *,
    nested: bool,
    max_concurrency: int | None,
) -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    active = 0
    peak = 0
    threshold = width if max_concurrency is None else max_concurrency
    started = asyncio.Event()
    release = asyncio.Event()

    def dispatch(context: Context[dict[str, Any]]) -> None:
        for index in range(width):
            context.emit("work", index)

    async def work(_context: Context[dict[str, Any], int]) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == threshold:
            started.set()
        await release.wait()
        active -= 1

    source = node(dispatch, name="dispatch")
    source.link(node(work, name="work"), "work")
    flow = Flow(source, name="parallel", concurrency=width)
    if nested:
        flow = Flow(flow, name="root", concurrency=1)
    options = (
        None if max_concurrency is None else RunOptions(max_concurrency=max_concurrency)
    )
    handle = flow.start({}, options=options)
    await asyncio.wait_for(started.wait(), 1)
    release.set()
    return await asyncio.wait_for(handle.result(), 1), {"peak": peak}


async def _retry_ready_priority() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    order: list[str] = []
    blocker_started = asyncio.Event()
    retry_scheduled = asyncio.Event()
    release_blocker = asyncio.Event()

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "retry")
        context.emit("work", "blocker")
        context.emit("work", "new")

    def delay(_attempt: int, _failure: Failure) -> int:
        retry_scheduled.set()
        return 1

    async def work(context: Context[dict[str, Any], str]) -> None:
        order.append(f"{context.input}:{context.attempt}")
        if context.input == "retry" and context.attempt == 1:
            raise FixtureError("retry")
        if context.input == "blocker":
            blocker_started.set()
            await release_blocker.wait()

    source = node(dispatch, name="dispatch")
    source.link(
        node(
            work,
            name="work",
            retry=RetryPolicy(max_attempts=2, delay_ms=delay),
        ),
        "work",
    )
    handle = Flow(source, concurrency=3).start(
        {}, options=RunOptions(max_concurrency=1)
    )
    await asyncio.wait_for(blocker_started.wait(), 1)
    await asyncio.wait_for(retry_scheduled.wait(), 1)
    await asyncio.sleep(0.01)
    release_blocker.set()
    return await asyncio.wait_for(handle.result(), 1), {"order": order}


async def _fair_scope_rotation() -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    order: list[list[object]] = []

    def root_dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("batch", "A")
        context.emit("batch", "B")

    def child_dispatch(context: Context[dict[str, Any], str]) -> None:
        for index in range(3):
            context.emit("work", [context.input, index])

    async def work(context: Context[dict[str, Any], list[object]]) -> None:
        order.append(context.input)
        await asyncio.sleep(0)

    root = node(root_dispatch, name="root_dispatch")
    child_entry = node(child_dispatch, name="child_dispatch")
    child_entry.link(node(work, name="work"), "work")
    root.link(Flow(child_entry, name="child", concurrency=3), "batch")
    result = (
        await Flow(root, concurrency=2)
        .start({}, options=RunOptions(max_concurrency=1))
        .result()
    )
    b0 = order.index(["B", 0])
    a2 = order.index(["A", 2])
    return result, {
        "work_count": len(order),
        "b0_before_a2": b0 < a2,
    }


async def _sibling_signal() -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    sibling_signalled = False
    scope_reason: object = None

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "failure")
        context.emit("work", "sibling")

    async def work(context: Context[dict[str, Any], str]) -> None:
        nonlocal scope_reason, sibling_signalled
        if context.input == "failure":
            await asyncio.sleep(0)
            raise FixtureError("failure")
        await context.cancellation.wait()
        sibling_signalled = context.cancellation.cancelled
        scope_reason = context.cancellation.reason

    def recover(
        context: Context[dict[str, Any]],
        _failure: ScopeFailure,
    ) -> None:
        context.state["recovered"] = True
        context.end()

    source = node(dispatch, name="dispatch")
    source.link(node(work, name="work"), "work")
    result = await Flow(source, concurrency=2, recover=recover).start({}).result()
    return result, {
        "scope_reason": (
            scope_reason
            if isinstance(scope_reason, (str, int, float, bool))
            or scope_reason is None
            else type(scope_reason).__name__
        ),
        "sibling_signalled": sibling_signalled,
    }


async def _parked_retry_packet() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    retry_scheduled = asyncio.Event()
    parked_cause = FixtureError("parked")
    controller_cause = FixtureError("controller")

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "parked")
        context.emit("work", "controller")

    def should_retry(failure: Failure) -> bool:
        return failure.cause is parked_cause

    def delay(_attempt: int, _failure: Failure) -> int:
        retry_scheduled.set()
        return 4_294_967_295

    async def work(context: Context[dict[str, Any], str]) -> None:
        if context.input == "parked":
            raise parked_cause
        await retry_scheduled.wait()
        raise controller_cause

    source = node(dispatch, name="dispatch")
    source.link(
        node(
            work,
            name="work",
            retry=RetryPolicy(
                max_attempts=2,
                should_retry=should_retry,
                delay_ms=delay,
            ),
        ),
        "work",
    )
    result = (
        await Flow(source, concurrency=2)
        .start({}, options=RunOptions(max_concurrency=2))
        .result()
    )
    return result, {
        "primary_is_controller": (
            result.status == "failed" and result.failure.cause is controller_cause
        ),
        "suppressed_is_parked": (
            len(getattr(result, "suppressed", ())) == 1
            and result.suppressed[0].cause is parked_cause  # type: ignore[union-attr]
        ),
    }


async def _attempt_limit_before_permit() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    calls: list[str] = []

    def dispatch(context: Context[dict[str, Any]]) -> None:
        calls.append("source")
        context.emit("work", "first")
        context.emit("work", "second")

    async def work(context: Context[dict[str, Any], str]) -> None:
        calls.append(context.input)
        await context.cancellation.wait()
        context.cancellation.raise_if_cancelled()

    source = node(dispatch, name="dispatch")
    source.link(node(work, name="work"), "work")
    result = (
        await Flow(source, concurrency=2)
        .start(
            {},
            options=RunOptions(
                max_attempts=2,
                max_concurrency=2,
            ),
        )
        .result()
    )
    detail = result.failure.detail if result.status == "failed" else None
    return result, {"calls": calls, "limit": getattr(detail, "limit", None)}


async def _retry_priority(
    *, observer_delay: bool
) -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    order: list[str] = []

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "retry")
        context.emit("work", "peer")

    def work(context: Context[dict[str, Any], str]) -> None:
        order.append(f"{context.input}:{context.attempt}")
        if context.input == "retry" and context.attempt == 1:
            raise FixtureError("retry")

    def observe(event: Any) -> None:
        if observer_delay and event.kind == "retry_scheduled":
            time.sleep(0.01)

    source = node(dispatch, name="dispatch")
    source.link(
        node(
            work,
            name="work",
            retry=RetryPolicy(
                max_attempts=2,
                delay_ms=1 if observer_delay else 0,
            ),
        ),
        "work",
    )
    result = (
        await Flow(source, concurrency=2)
        .start(
            {},
            options=RunOptions(
                max_concurrency=1,
                observer=observe if observer_delay else None,
            ),
        )
        .result()
    )
    return result, {"order": order}


async def _node_recovery_priority() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    order: list[str] = []

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "bad")
        context.emit("work", "peer")

    def work(context: Context[dict[str, Any], str]) -> None:
        order.append(f"handle:{context.input}")
        if context.input == "bad":
            raise FixtureError("bad")

    def recover(
        context: Context[dict[str, Any], str],
        _failure: Failure,
    ) -> None:
        order.append(f"recover:{context.input}")
        context.end("recovered")

    source = node(dispatch, name="dispatch")
    source.link(node(work, name="work", recover=recover), "work")
    result = (
        await Flow(source, concurrency=2)
        .start({}, options=RunOptions(max_concurrency=1))
        .result()
    )
    return result, {"order": order}


async def _ready_waiter_capacity() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    calls: list[str] = []

    def dispatch(context: Context[dict[str, Any]]) -> None:
        calls.append("dispatch")
        context.emit("run", "active")
        context.emit("run", "waiting")

    async def work(context: Context[dict[str, Any], str]) -> None:
        calls.append(context.input)
        if context.input == "active":
            await asyncio.sleep(0)
            context.emit("child", 1)
            context.emit("child", 2)

    source = node(dispatch, name="dispatch")
    worker = node(work, name="work")
    worker.link(node(lambda _context: None, name="child"), "child")
    source.link(worker, "run")
    result = (
        await Flow(source, concurrency=2)
        .start(
            {},
            options=RunOptions(
                max_concurrency=1,
                max_ready=2,
            ),
        )
        .result()
    )
    detail = result.failure.detail if result.status == "failed" else None
    return result, {"calls": calls, "limit": getattr(detail, "limit", None)}


async def _cancel_before_admission() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    called = False

    def handler(_context: Context[dict[str, Any]]) -> None:
        nonlocal called
        called = True

    handle = Flow(node(handler, name="work")).start({})
    handle.cancel(CANCEL_REASON)
    return await handle.result(), {"called": called}


async def _cancel_after_buffer() -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    started = asyncio.Event()

    async def handler(context: Context[dict[str, Any]]) -> None:
        context.end("discarded")
        started.set()
        await context.cancellation.wait()

    handle = Flow(node(handler, name="work")).start({})
    await asyncio.wait_for(started.wait(), 1)
    handle.cancel(CANCEL_REASON)
    return await handle.result(), {}


async def _post_signal_suppression() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    started = asyncio.Event()

    async def handler(context: Context[dict[str, Any]]) -> None:
        started.set()
        await context.cancellation.wait()
        raise FixtureError("after signal")

    handle = Flow(node(handler, name="work")).start({})
    await asyncio.wait_for(started.wait(), 1)
    handle.cancel(CANCEL_REASON)
    return await handle.result(), {}


async def _prior_terminal_ready_discard() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    waiting = asyncio.Event()

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("done", 1)
        context.emit("wait", 2)
        context.emit("late", 3)

    def done(context: Context[dict[str, Any], int]) -> None:
        context.end(context.input)

    async def wait(context: Context[dict[str, Any], int]) -> None:
        waiting.set()
        await context.cancellation.wait()

    def late(context: Context[dict[str, Any], int]) -> None:
        context.state["late"] = context.input

    source = node(dispatch, name="dispatch")
    source.link(node(done, name="done"), "done")
    source.link(node(wait, name="wait"), "wait")
    source.link(node(late, name="late"), "late")
    handle = Flow(source).start({})
    await asyncio.wait_for(waiting.wait(), 1)
    handle.cancel(CANCEL_REASON)
    result = await handle.result()
    return result, {"late_present": "late" in result.state}


async def _cancel_retry_delay() -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    scheduled = asyncio.Event()

    def handler(_context: Context[dict[str, Any]]) -> None:
        raise FixtureError("retry")

    def delay(_attempt: int, _failure: Failure) -> int:
        scheduled.set()
        return 4_294_967_295

    worker = node(
        handler,
        name="work",
        retry=RetryPolicy(max_attempts=2, delay_ms=delay),
    )
    handle = Flow(worker).start({})
    await asyncio.wait_for(scheduled.wait(), 1)
    handle.cancel(CANCEL_REASON)
    return await asyncio.wait_for(handle.result(), 1), {}


async def _cancel_recovery(
    layer: str,
) -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    started = asyncio.Event()

    def fail(_context: Context[dict[str, Any]]) -> None:
        raise FixtureError("handler")

    async def node_recovery(
        context: Context[dict[str, Any]],
        _failure: Failure,
    ) -> None:
        started.set()
        await context.cancellation.wait()
        context.cancellation.raise_if_cancelled()

    async def flow_recovery(
        context: Context[dict[str, Any]],
        _failure: ScopeFailure,
    ) -> None:
        started.set()
        await context.cancellation.wait()
        context.cancellation.raise_if_cancelled()

    entry = node(
        fail,
        name="work",
        recover=node_recovery if layer == "node" else None,
    )
    flow = Flow(entry, recover=flow_recovery if layer == "flow" else None)
    handle = flow.start({})
    await asyncio.wait_for(started.wait(), 1)
    handle.cancel(CANCEL_REASON)
    return await handle.result(), {}


def _fence_observer(fences: list[str]) -> Any:
    def observe(event: Any) -> None:
        if event.kind in {"failure_fenced", "cancellation_fenced"}:
            fences.append(f"{event.kind}:{event.payload.target.kind}")
        elif event.kind == "run_finished":
            fences.append(f"run_finished:{event.payload.status}")

    return observe


async def _failure_grace_abandonment() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    sibling_started = asyncio.Event()
    release_sibling = asyncio.Event()
    fences: list[str] = []
    recovery_called = False

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "sibling")
        context.emit("work", "failure")

    async def work(context: Context[dict[str, Any], str]) -> None:
        if context.input == "sibling":
            sibling_started.set()
            await release_sibling.wait()
            return
        await sibling_started.wait()
        raise FixtureError("failure")

    def recover(
        context: Context[dict[str, Any]],
        _failure: ScopeFailure,
    ) -> None:
        nonlocal recovery_called
        recovery_called = True
        context.end()

    source = node(dispatch, name="dispatch")
    source.link(node(work, name="work"), "work")
    try:
        result = (
            await Flow(source, concurrency=2, recover=recover)
            .start(
                {},
                options=RunOptions(
                    max_concurrency=2,
                    cancel_grace_ms=0,
                    observer=_fence_observer(fences),
                ),
            )
            .result()
        )
    finally:
        release_sibling.set()
        await asyncio.sleep(0)
    return result, {"fences": fences, "recovery_called": recovery_called}


async def _retry_suppression_unique() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    late_attempt_one = FixtureError("late attempt one")
    second_attempt = FixtureError("second attempt")

    async def work(context: Context[dict[str, Any]]) -> None:
        if context.attempt == 1:
            await context.cancellation.wait()
            raise late_attempt_one
        raise second_attempt

    result = (
        await Flow(
            node(
                work,
                name="work",
                timeout_ms=1,
                retry=RetryPolicy(max_attempts=2),
            )
        )
        .start({}, options=RunOptions(cancel_grace_ms=100))
        .result()
    )
    primary = result.failure if result.status == "failed" else None
    suppressed = getattr(result, "suppressed", ())
    return result, {
        "primary_is_second_attempt": (
            primary is not None
            and primary.kind == "handler"
            and primary.attempt == 2
            and primary.cause is second_attempt
        ),
        "previous_is_timeout": (
            primary is not None
            and primary.previous is not None
            and primary.previous.kind == "handler_timeout"
        ),
        "suppression_is_unique": (
            len(suppressed) == 1
            and suppressed[0].kind == "handler"
            and suppressed[0].attempt == 1
            and suppressed[0].cause is late_attempt_one
        ),
    }


async def _concurrent_cancel_abandonment() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    active = 0
    both_started = asyncio.Event()
    release_stuck = asyncio.Event()
    fences: list[str] = []

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "cooperative")
        context.emit("work", "stuck")

    async def work(context: Context[dict[str, Any], str]) -> None:
        nonlocal active
        active += 1
        if active == 2:
            both_started.set()
        if context.input == "stuck":
            await release_stuck.wait()
            return
        await context.cancellation.wait()
        context.cancellation.raise_if_cancelled()

    source = node(dispatch, name="dispatch")
    source.link(node(work, name="work"), "work")
    handle = Flow(source, concurrency=2).start(
        {},
        options=RunOptions(
            max_concurrency=2,
            cancel_grace_ms=0,
            observer=_fence_observer(fences),
        ),
    )
    await both_started.wait()
    handle.cancel(CANCEL_REASON)
    try:
        result = await handle.result()
    finally:
        release_stuck.set()
        await asyncio.sleep(0)
    return result, {"fences": fences}


async def _sync_retry_policy_grace() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    handle: Any = None
    recorded_failure_kinds: list[str] = []

    def observe(event: Any) -> None:
        if event.kind == "failure_recorded":
            recorded_failure_kinds.append(event.payload.failure.kind)

    def should_retry(_failure: Failure) -> bool:
        handle.cancel(CANCEL_REASON)
        time.sleep(0.01)
        raise FixtureError("late retry policy")

    def fail(_context: Context[dict[str, Any]]) -> None:
        raise FixtureError("handler")

    worker = node(
        fail,
        name="work",
        retry=RetryPolicy(max_attempts=2, should_retry=should_retry),
    )
    handle = Flow(worker).start(
        {},
        options=RunOptions(cancel_grace_ms=0, observer=observe),
    )
    result = await handle.result()
    return result, {"recorded_failure_kinds": recorded_failure_kinds}


async def _route_packet_cancellation() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    handle: Any = None

    def observe(event: Any) -> None:
        if (
            event.kind == "callback_finished"
            and event.payload.phase == "handle"
            and event.payload.attempt == 2
        ):
            handle.cancel(CANCEL_REASON)

    async def work(context: Context[dict[str, Any]]) -> None:
        if context.attempt == 1:
            await context.cancellation.wait()
            raise FixtureError("after timeout")
        context.end("discarded")

    worker = node(
        work,
        name="work",
        timeout_ms=1,
        retry=RetryPolicy(max_attempts=2),
    )
    handle = Flow(worker).start(
        {},
        options=RunOptions(cancel_grace_ms=100, observer=observe),
    )
    return await handle.result(), {}


async def _nested_scope_failure_status() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    scope_finishes: list[str] = []

    def observe(event: Any) -> None:
        if event.kind == "scope_finished":
            scope_finishes.append(f"{event.payload.scope_id}:{event.payload.status}")

    def combine(_context: Context[dict[str, Any]], _result: Any) -> None:
        raise FixtureError("combine")

    def recover(
        context: Context[dict[str, Any]],
        _failure: ScopeFailure,
    ) -> None:
        context.state["recovered"] = True
        context.end()

    child = Flow(
        node(lambda context: context.end(), name="leaf"),
        name="child",
        combine=combine,
    )
    result = (
        await Flow(child, name="root", concurrency=2, recover=recover)
        .start({}, options=RunOptions(observer=observe))
        .result()
    )
    return result, {"scope_finishes": scope_finishes}


async def _opening_observer_deadline() -> tuple[
    RunResult[dict[str, Any]], dict[str, object]
]:
    called = False

    def work(_context: Context[dict[str, Any]]) -> None:
        nonlocal called
        called = True

    def observe(event: Any) -> None:
        if event.kind == "run_started":
            time.sleep(0.01)

    handle = Flow(node(work, name="work")).start(
        {},
        options=RunOptions(
            deadline_ms=1,
            cancel_grace_ms=100,
            observer=observe,
        ),
    )
    done_on_return = handle.done()
    return await handle.result(), {
        "called": called,
        "done_on_return": done_on_return,
    }


async def run_program(
    program: dict[str, Any],
) -> tuple[RunResult[dict[str, Any]], dict[str, object]]:
    scenario = program["scenario"]
    if scenario in {"auto_width", "nested_auto_width", "global_ceiling"}:
        return await _gated_width(
            program["width"],
            nested=scenario == "nested_auto_width",
            max_concurrency=program.get("max_concurrency"),
        )
    if scenario == "retry_ready_priority":
        return await _retry_ready_priority()
    if scenario == "fair_scope_rotation":
        return await _fair_scope_rotation()
    if scenario == "sibling_signal_before_recovery":
        return await _sibling_signal()
    if scenario == "parked_retry_packet":
        return await _parked_retry_packet()
    if scenario == "attempt_limit_before_permit":
        return await _attempt_limit_before_permit()
    if scenario == "zero_delay_retry_priority":
        return await _retry_priority(observer_delay=False)
    if scenario == "observer_retry_delay":
        return await _retry_priority(observer_delay=True)
    if scenario == "node_recovery_priority":
        return await _node_recovery_priority()
    if scenario == "ready_waiter_capacity":
        return await _ready_waiter_capacity()
    if scenario == "cancel_before_admission":
        return await _cancel_before_admission()
    if scenario == "cancel_after_buffer":
        return await _cancel_after_buffer()
    if scenario == "post_signal_suppression":
        return await _post_signal_suppression()
    if scenario == "prior_terminal_ready_discard":
        return await _prior_terminal_ready_discard()
    if scenario == "cancel_retry_delay":
        return await _cancel_retry_delay()
    if scenario == "cancel_node_recovery":
        return await _cancel_recovery("node")
    if scenario == "cancel_flow_recovery":
        return await _cancel_recovery("flow")
    if scenario == "failure_grace_abandonment":
        return await _failure_grace_abandonment()
    if scenario == "retry_suppression_unique":
        return await _retry_suppression_unique()
    if scenario == "concurrent_cancel_abandonment":
        return await _concurrent_cancel_abandonment()
    if scenario == "sync_retry_policy_grace":
        return await _sync_retry_policy_grace()
    if scenario == "route_packet_cancellation":
        return await _route_packet_cancellation()
    if scenario == "nested_scope_failure_status":
        return await _nested_scope_failure_status()
    if scenario == "opening_observer_deadline":
        return await _opening_observer_deadline()
    raise AssertionError(f"unknown scheduling/cancellation scenario {scenario!r}")


def normalize(
    result: RunResult[dict[str, Any]],
    observations: dict[str, object],
) -> dict[str, object]:
    normalized_result: dict[str, object] = {
        "status": result.status,
        "state": dict(result.state),
        "terminal_count": len(result.terminals),
        "outputs": [
            terminal.output for terminal in result.terminals if terminal.has_output
        ],
        "suppressed": [
            {"kind": failure.kind, "attempt": failure.attempt}
            for failure in getattr(result, "suppressed", ())
        ],
    }
    if result.status == "cancelled":
        normalized_result["cancellation"] = {
            "reason": result.cancellation.reason,
            "deadline": result.cancellation.deadline,
        }
    elif result.status == "abandoned":
        if isinstance(result.cause, Failure):
            normalized_result["cause"] = {
                "type": "failure",
                "kind": result.cause.kind,
                "attempt": result.cause.attempt,
            }
        else:
            normalized_result["cause"] = {
                "type": "cancellation",
                "reason": result.cause.reason,
                "deadline": result.cause.deadline,
            }
    return {
        "result": normalized_result,
        "observations": observations,
        "stats": {
            "activations": result.stats.activations,
            "attempts": result.stats.attempts,
            "transitions": result.stats.transitions,
            "retries": result.stats.retries,
            "scopes": result.stats.scopes,
            "peak_callbacks": result.stats.peak_callbacks,
        },
    }


async def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures = []
    for fixture in collection["fixtures"]:
        result, observations = await run_program(fixture["program"])
        fixtures.append(
            {
                "id": fixture["id"],
                "snapshot": normalize(result, observations),
            }
        )
    print(
        json.dumps(
            {"schema_version": 1, "fixtures": fixtures},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
