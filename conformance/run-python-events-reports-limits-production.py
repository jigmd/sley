from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from caskada import (
    Context,
    Flow,
    RunEvent,
    RunOptions,
    TerminalCommittedEvent,
    TransitionCommittedEvent,
    node,
)

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "events-reports-limits.json"


async def _successful_trace() -> dict[str, object]:
    events: list[RunEvent] = []

    def first(context: Context[dict[str, Any]]) -> None:
        context.emit("next", 7)

    def second(context: Context[dict[str, Any], int]) -> None:
        context.end(context.input)

    source = node(first, name="first")
    source.link(node(second, name="second"), "next")
    result = (
        await Flow(source)
        .start({}, options=RunOptions(observer=events.append, run_id="fixture-events"))
        .result()
    )
    transitions = [
        cast(TransitionCommittedEvent, event)
        for event in events
        if event.kind == "transition_committed"
    ]
    terminal = next(
        cast(TerminalCommittedEvent, event)
        for event in events
        if event.kind == "terminal_committed"
    )
    return {
        "status": result.status,
        "run_ids": sorted({event.run_id for event in events}),
        "sequences": [event.sequence for event in events],
        "kinds": [event.kind for event in events],
        "route_destination": transitions[0].payload.transition.destination.type,
        "end_terminal_sequence": transitions[1].payload.transition.destination.sequence,
        "committed_terminal_sequence": terminal.payload.terminal_sequence,
    }


async def _observer_skip() -> dict[str, object]:
    events: list[RunEvent] = []
    calls = 0
    handle: Any = None

    def handler(_context: Context[dict[str, Any]]) -> None:
        nonlocal calls
        calls += 1

    def observe(event: RunEvent) -> None:
        events.append(event)
        if event.kind == "callback_started":
            handle.cancel("observer")

    handle = Flow(node(handler, name="work")).start(
        {}, options=RunOptions(observer=observe)
    )
    result = await handle.result()
    return {
        "status": result.status,
        "calls": calls,
        "kinds": [event.kind for event in events],
        "attempts": result.stats.attempts,
    }


async def _observer_throw() -> dict[str, object]:
    calls = 0

    def observe(_event: RunEvent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("observer")

    result = (
        await Flow(node(lambda _context: None, name="work"))
        .start({}, options=RunOptions(observer=observe))
        .result()
    )
    diagnostic = result.diagnostics[0]
    return {
        "status": result.status,
        "calls": calls,
        "diagnostic_count": len(result.diagnostics),
        "diagnostic": {
            "event_sequence": diagnostic.event_sequence,
            "message": diagnostic.message,
        },
    }


async def _report_presence() -> dict[str, object]:
    events: list[RunEvent] = []

    def handler(context: Context[dict[str, Any]]) -> None:
        context.report("started")
        context.report("value", None)

    result = (
        await Flow(node(handler, name="work"))
        .start({}, options=RunOptions(observer=events.append))
        .result()
    )
    reports: list[dict[str, object]] = []
    for event in events:
        if event.kind != "report":
            continue
        report: dict[str, object] = {
            "name": event.payload.name,
            "has_data": event.payload.has_data,
        }
        if event.payload.has_data:
            report["data"] = event.payload.data
        reports.append(report)
    return {
        "status": result.status,
        "reports": reports,
        "report_count": result.stats.reports,
    }


async def _report_reentrant() -> dict[str, object]:
    events: list[RunEvent] = []
    active: Context[dict[str, Any]] | None = None

    def observe(event: RunEvent) -> None:
        events.append(event)
        if event.kind == "report":
            assert active is not None
            active.report("nested")

    def handler(context: Context[dict[str, Any]]) -> None:
        nonlocal active
        active = context
        context.report("outer")

    result = (
        await Flow(node(handler, name="work"))
        .start({}, options=RunOptions(observer=observe))
        .result()
    )
    diagnostic = result.diagnostics[0]
    reports = [event for event in events if event.kind == "report"]
    return {
        "status": result.status,
        "published_reports": len(reports),
        "report_count": result.stats.reports,
        "diagnostic": {
            "event_sequence": diagnostic.event_sequence,
            "message": diagnostic.message,
        },
    }


async def _report_overflow() -> dict[str, object]:
    events: list[RunEvent] = []
    caught = 0

    def handler(context: Context[dict[str, Any]]) -> None:
        nonlocal caught
        context.report("first")
        for name in ("overflow", "already_fenced"):
            try:
                context.report(name)
            except asyncio.CancelledError:
                caught += 1

    result = (
        await Flow(node(handler, name="work"))
        .start({}, options=RunOptions(max_reports=1, observer=events.append))
        .result()
    )
    return _normalize_limit(
        result,
        observations={
            "caught": caught,
            "published_reports": sum(event.kind == "report" for event in events),
            "failure_fences": sum(event.kind == "failure_fenced" for event in events),
        },
    )


async def _transition_overflow() -> dict[str, object]:
    events: list[RunEvent] = []
    caught = False
    caught_kinds: list[str] = []

    def control_kinds() -> list[str]:
        selected = {
            "callback_finished",
            "cancellation_fenced",
            "failure_fenced",
            "failure_recorded",
            "run_finished",
        }
        return [
            (
                f"{event.kind}:{event.payload.target.kind}"
                if event.kind in {"failure_fenced", "cancellation_fenced"}
                else event.kind
            )
            for event in events
            if event.kind in selected
        ]

    def source(context: Context[dict[str, Any]]) -> None:
        nonlocal caught, caught_kinds
        context.emit("next", 1)
        try:
            context.emit("next", 2)
        except asyncio.CancelledError:
            caught = True
            caught_kinds = control_kinds()

    source_node = node(source, name="source")
    source_node.link(node(lambda _context: None, name="target"), "next")
    result = (
        await Flow(source_node)
        .start({}, options=RunOptions(max_transitions=1, observer=events.append))
        .result()
    )
    return _normalize_limit(
        result,
        observations={
            "caught": caught,
            "caught_kinds": caught_kinds,
            "control_order": control_kinds(),
        },
    )


async def _capacity_priority() -> dict[str, object]:
    source = node(lambda context: context.emit("next"), name="source")
    source.link(node(lambda _context: None, name="target"), "next")
    result = (
        await Flow(source, max_activations=1)
        .start(
            {},
            options=RunOptions(max_activations=2, max_ready=1),
        )
        .result()
    )
    return _normalize_limit(result)


async def _depth_limit() -> dict[str, object]:
    source = node(lambda context: context.emit("child"), name="source")
    source.link(Flow(node(lambda _context: None, name="entry"), name="child"), "child")
    result = await Flow(source).start({}, options=RunOptions(max_depth=1)).result()
    return _normalize_limit(result)


async def _attempt_limit() -> dict[str, object]:
    calls: list[str] = []

    def source(context: Context[dict[str, Any]]) -> None:
        calls.append("source")
        context.emit("next")

    def target(_context: Context[dict[str, Any]]) -> None:
        calls.append("target")

    source_node = node(source, name="source")
    source_node.link(node(target, name="target"), "next")
    result = (
        await Flow(source_node).start({}, options=RunOptions(max_attempts=1)).result()
    )
    return _normalize_limit(result, observations={"calls": calls})


def _normalize_limit(
    result: Any,
    *,
    observations: dict[str, object] | None = None,
) -> dict[str, object]:
    if result.status != "failed":
        raise AssertionError("limit fixture must fail")
    detail = result.failure.detail
    return {
        "status": result.status,
        "failure": {
            "kind": result.failure.kind,
            "limit": detail.limit,
            "attempt": result.failure.attempt,
            "scope_id": result.failure.scope_id,
            "activation_id": result.failure.activation_id,
        },
        "terminal_count": len(result.terminals),
        "observations": {} if observations is None else observations,
        "stats": {
            "activations": result.stats.activations,
            "attempts": result.stats.attempts,
            "transitions": result.stats.transitions,
            "reports": result.stats.reports,
            "peak_ready": result.stats.peak_ready,
            "scopes": result.stats.scopes,
        },
    }


async def run_program(scenario: str) -> dict[str, object]:
    runners = {
        "successful_trace": _successful_trace,
        "observer_skip": _observer_skip,
        "observer_throw": _observer_throw,
        "report_presence": _report_presence,
        "report_reentrant": _report_reentrant,
        "report_overflow": _report_overflow,
        "transition_overflow": _transition_overflow,
        "capacity_priority": _capacity_priority,
        "depth_limit": _depth_limit,
        "attempt_limit": _attempt_limit,
    }
    try:
        runner = runners[scenario]
    except KeyError as error:
        raise AssertionError(
            f"unknown events/reports/limits scenario {scenario!r}"
        ) from error
    return await runner()


async def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures = []
    for fixture in collection["fixtures"]:
        fixtures.append(
            {
                "id": fixture["id"],
                "snapshot": await run_program(fixture["program"]["scenario"]),
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
