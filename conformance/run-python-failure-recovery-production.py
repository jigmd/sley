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
    RunEvent,
    RunOptions,
    ScopeFailure,
    ScopeResult,
    Terminal,
    node,
)

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "failure-recovery.json"


class FixtureError(Exception):
    pass


class FixtureRuntime:
    def __init__(self, program: dict[str, Any]) -> None:
        self.program = program
        self.events: list[RunEvent] = []

    def build(self) -> Flow[dict[str, Any]]:
        worker = node(
            self._handle,
            name="worker",
            retry=RetryPolicy(max_attempts=self.program["retry_max_attempts"]),
            recover=self._node_recover
            if self.program["node_recovery"] != "none"
            else None,
        )
        topology = self.program["topology"]
        if topology == "root_node":
            return Flow(worker, name="root")
        if topology == "node_after_source":
            source = node(self._source, name="source")
            source.link(worker)
            return Flow(source, name="root")
        if topology == "nested_flow":
            child = Flow(
                worker,
                name="child",
                recover=self._flow_recover,
            )
            source = node(self._source, name="source")
            source.link(child)
            return Flow(source, name="root")
        if topology == "combine":
            return Flow(
                worker,
                name="root",
                combine=self._combine,
                recover=self._flow_recover,
            )
        raise AssertionError(f"unknown topology {topology!r}")

    def _source(self, context: Context[dict[str, Any]]) -> None:
        context.emit(input=self.program["input"])

    def _handle(self, context: Context[dict[str, Any]]) -> None:
        attempts = int(context.state.get("handler_attempts", 0)) + 1
        context.state["handler_attempts"] = attempts
        mode = self.program["handler"]
        if mode == "fail" or (mode == "fail_once_then_end" and attempts == 1):
            raise FixtureError("handler")
        if mode == "end":
            context.end(self.program["input"])
        else:
            context.end(self.program["output"])

    def _node_recover(
        self,
        context: Context[dict[str, Any]],
        failure: Failure,
    ) -> None:
        observation: dict[str, object] = {
            "failure_id": failure.failure_id,
            "kind": failure.kind,
        }
        if self.program["topology"] == "node_after_source":
            observation["input"] = context.input
        context.state["node_recovery"] = observation
        mode = self.program["node_recovery"]
        if mode == "end":
            context.end(self.program["output"])
        elif mode == "throw":
            raise FixtureError("node_recovery")

    def _combine(
        self,
        _context: Context[dict[str, Any]],
        _result: ScopeResult,
    ) -> None:
        raise FixtureError("combine")

    def _flow_recover(
        self,
        context: Context[dict[str, Any]],
        failure: ScopeFailure,
    ) -> None:
        settled_outputs = [
            terminal.output
            for terminal in failure.settled_before_fence
            if terminal.has_output
        ]
        observation: dict[str, object] = {
            "failure_id": failure.primary.failure_id,
            "kind": failure.primary.kind,
            "failing_activation_id": failure.failing_activation_id,
            "settled_outputs": settled_outputs,
            "result_outputs": None
            if failure.result is None
            else list(failure.result.outputs),
        }
        if self.program["topology"] == "nested_flow":
            observation["input"] = context.input
        context.state["flow_recovery"] = observation
        mode = self.program["flow_recovery"]
        if mode == "end":
            context.end(self.program["output"])
        elif mode == "throw":
            raise FixtureError("flow_recovery")


async def run_fixture(fixture: dict[str, Any]) -> dict[str, object]:
    runtime = FixtureRuntime(fixture["program"])
    compiled = runtime.build().compile()
    names = {
        element["element_id"]: element["name"]
        for element in compiled.describe()["elements"]
    }
    result = await compiled.start(
        {}, options=RunOptions(observer=runtime.events.append)
    ).result()
    normalized_result: dict[str, object] = {
        "status": result.status,
        "state": dict(result.state),
        "terminals": [normalize_terminal(terminal) for terminal in result.terminals],
    }
    if result.status == "failed":
        normalized_result["failure"] = normalize_failure(result.failure, names)
        normalized_result["suppressed"] = [
            normalize_failure(failure, names) for failure in result.suppressed
        ]
    failures = [
        normalize_failure(event.payload.failure, names)
        for event in runtime.events
        if event.kind == "failure_recorded"
    ]
    retries = [
        {
            "failure_id": event.payload.failure_id,
            "failed_attempt": event.payload.failed_attempt,
            "next_attempt": event.payload.next_attempt,
            "delay_ms": event.payload.delay_ms,
        }
        for event in runtime.events
        if event.kind == "retry_scheduled"
    ]
    return {
        "id": fixture["id"],
        "snapshot": {
            "result": normalized_result,
            "trace": {"failures": failures, "retries": retries},
            "stats": {
                "activations": result.stats.activations,
                "attempts": result.stats.attempts,
                "transitions": result.stats.transitions,
                "retries": result.stats.retries,
                "scopes": result.stats.scopes,
            },
        },
    }


def normalize_failure(
    failure: Failure,
    names: dict[int, str],
) -> dict[str, object]:
    if failure.element_id is None:
        raise AssertionError("fixture Failure must have an element")
    return {
        "failure_id": failure.failure_id,
        "kind": failure.kind,
        "message": failure.message,
        "source": names[failure.element_id],
        "attempt": failure.attempt,
        "previous_failure_id": None
        if failure.previous is None
        else failure.previous.failure_id,
    }


def normalize_terminal(terminal: Terminal) -> dict[str, object]:
    normalized: dict[str, object] = {
        "type": terminal.type,
        "has_output": terminal.has_output,
    }
    if terminal.type == "exit":
        normalized["action"] = terminal.action
    if terminal.has_output:
        normalized["output"] = terminal.output
    return normalized


async def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures = [await run_fixture(fixture) for fixture in collection["fixtures"]]
    print(
        json.dumps(
            {"schema_version": 1, "fixtures": fixtures},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
