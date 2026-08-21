from __future__ import annotations

import asyncio
import json
import sys
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

    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", "failure")
        context.emit("work", "sibling")

    async def work(context: Context[dict[str, Any], str]) -> None:
        nonlocal sibling_signalled
        if context.input == "failure":
            await asyncio.sleep(0)
            raise FixtureError("failure")
        await context.cancellation.wait()
        sibling_signalled = context.cancellation.cancelled

    def recover(
        context: Context[dict[str, Any]],
        _failure: ScopeFailure,
    ) -> None:
        context.state["recovered"] = True
        context.end()

    source = node(dispatch, name="dispatch")
    source.link(node(work, name="work"), "work")
    result = await Flow(source, concurrency=2, recover=recover).start({}).result()
    return result, {"sibling_signalled": sibling_signalled}


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
