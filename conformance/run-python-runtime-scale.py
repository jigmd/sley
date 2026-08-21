from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from caskada import Context, Flow, GraphElement, RunOptions, node

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "runtime-scale.json"


async def _run(fixture: dict[str, Any]) -> dict[str, object]:
    size = fixture["size"]
    kind = fixture["kind"]
    if kind == "node_chain":
        nodes = [
            node(lambda _context: None, name=f"node-{index}") for index in range(size)
        ]
        for index in range(size - 1):
            nodes[index].link(nodes[index + 1])
        result = (
            await Flow(nodes[0])
            .start(
                {},
                options=RunOptions(
                    max_activations=size + 1,
                    max_attempts=size,
                    max_transitions=size,
                    max_ready=size,
                ),
            )
            .result()
        )
        return _result_snapshot(result)
    if kind == "nested_flows":
        entry: GraphElement[dict[str, Any]] = node(lambda _context: None, name="leaf")
        for index in range(size):
            entry = Flow(entry, name=f"nested-{index}")
        result = (
            await Flow(entry, name="root")
            .start(
                {},
                options=RunOptions(
                    max_depth=size + 1,
                    max_activations=size + 2,
                    max_attempts=1,
                    max_transitions=(size * 2) + 1,
                ),
            )
            .result()
        )
        return _result_snapshot(result)
    if kind == "wide_fanout":

        def dispatch(context: Context[dict[str, Any]]) -> None:
            for index in range(size):
                context.emit("work", index)

        def work(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input)

        source = node(dispatch, name="dispatch")
        source.link(node(work, name="work"), "work")
        result = (
            await Flow(source)
            .start(
                {},
                options=RunOptions(
                    max_activations=size + 2,
                    max_attempts=size + 1,
                    max_transitions=size * 2,
                    max_ready=size,
                ),
            )
            .result()
        )
        snapshot = _result_snapshot(result)
        snapshot["first_output"] = result.terminals[0].output
        snapshot["last_output"] = result.terminals[-1].output
        return snapshot
    if kind == "concurrent_reuse":

        async def work(context: Context[dict[str, Any]]) -> None:
            await asyncio.sleep(0)
            context.state["value"] = context.state["seed"]

        compiled = Flow(node(work, name="work")).compile()
        states = await asyncio.gather(
            *(compiled.run({"seed": index}) for index in range(size))
        )
        return {
            "runs": len(states),
            "unique_state_carriers": len({id(state) for state in states}),
            "first_value": states[0]["value"],
            "last_value": states[-1]["value"],
        }
    if kind == "nested_cancel":
        started = asyncio.Event()

        async def wait_for_cancellation(context: Context[dict[str, Any]]) -> None:
            started.set()
            await context.cancellation.wait()

        entry: GraphElement[dict[str, Any]] = node(
            wait_for_cancellation,
            name="leaf",
        )
        for index in range(size):
            entry = Flow(entry, name=f"nested-{index}")
        handle = Flow(entry, name="root").start(
            {},
            options=RunOptions(
                max_depth=size + 1,
                max_activations=size + 2,
                max_attempts=1,
                max_transitions=size * 2 + 1,
            ),
        )
        await started.wait()
        handle.cancel("fixture-cancel")
        return _result_snapshot(await handle.result())
    raise AssertionError(f"unknown runtime-scale kind {kind!r}")


def _result_snapshot(result: Any) -> dict[str, object]:
    return {
        "status": result.status,
        "activations": result.stats.activations,
        "attempts": result.stats.attempts,
        "transitions": result.stats.transitions,
        "scopes": result.stats.scopes,
        "peak_ready": result.stats.peak_ready,
        "terminal_count": len(result.terminals),
    }


async def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    observed = []
    for fixture in collection["fixtures"]:
        snapshot = await _run(fixture)
        if snapshot != fixture["expect"]:
            raise AssertionError(
                f"{fixture['id']} mismatch: expected={fixture['expect']}, actual={snapshot}"
            )
        observed.append({"id": fixture["id"], "snapshot": snapshot})
    print(
        json.dumps(
            {"schema_version": 1, "fixtures": observed},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
