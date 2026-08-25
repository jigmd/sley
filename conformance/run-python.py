from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sley import (
    CompiledDescription,
    Context,
    Flow,
    RetryPolicy,
    RunResult,
    ScopeFailure,
    ScopeResult,
    node,
)


def terminal_snapshot(terminal: Any) -> dict[str, Any]:
    return {
        "type": terminal.type,
        "action": terminal.action if terminal.type == "exit" else None,
        "has_output": terminal.has_output,
        "output": terminal.output if terminal.has_output else None,
        "sequence": terminal.sequence,
        "source_activation_id": terminal.source_activation_id,
    }


def result_snapshot(result: RunResult[Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "status": result.status,
        "state": result.state,
        "terminals": [terminal_snapshot(item) for item in result.terminals],
    }
    if result.status == "failed":
        snapshot["failure"] = {
            "kind": result.failure.kind,
            "attempt": result.failure.attempt,
            "previous_kind": (
                None
                if result.failure.previous is None
                else result.failure.previous.kind
            ),
        }
    return snapshot


def case_snapshot(result: RunResult[Any] | CompiledDescription) -> Any:
    return result if isinstance(result, dict) else result_snapshot(result)


async def compiled_description() -> CompiledDescription:
    entry = node(
        lambda _context: None,
        name="entry",
        retry=RetryPolicy(max_attempts=3),
    )
    child_entry = node(
        lambda _context: None,
        name="child entry",
        retry=RetryPolicy(max_attempts=2),
    )
    child = Flow(
        child_entry,
        name="child",
        exits=("done",),
        concurrency=3,
        max_activations=5,
    )
    finish = node(lambda _context: None, name="finish")
    entry.link(child, "nested")
    child.link(finish)
    return (
        Flow(
            entry,
            name="root",
            exits=("abort",),
            concurrency=2,
        )
        .compile()
        .describe()
    )


async def implicit_link() -> RunResult[Any]:
    def first(context: Context[dict[str, Any]]) -> None:
        context.state["count"] = 1

    def second(context: Context[dict[str, Any]]) -> None:
        context.state["count"] += 1

    first_node = node(first)
    first_node.link(node(second))
    return await Flow(first_node).start({"count": 0}).result()


async def named_input() -> RunResult[Any]:
    source = node(lambda context: context.emit("work", 7))
    source.link(
        node(lambda context: context.state.__setitem__("seen", context.input)),
        "work",
    )
    return await Flow(source).start({}).result()


async def unlabelled_input() -> RunResult[Any]:
    def produce(context: Context[dict[str, Any]]) -> None:
        context.emit(input=9)

    source = node(produce)
    source.link(node(lambda context: context.state.__setitem__("seen", context.input)))
    return await Flow(source).start({}).result()


async def fanout_ends() -> RunResult[Any]:
    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", 1)
        context.emit("work", 2)

    source = node(dispatch)
    source.link(node(lambda context: context.end(context.input * 10)), "work")
    return await Flow(source).start({}).result()


async def output_presence() -> RunResult[Any]:
    def finish(context: Context[dict[str, Any]]) -> None:
        context.end()
        context.end(None)

    return await Flow(node(finish)).start({}).result()


async def combine_preserve() -> RunResult[Any]:
    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", 1)
        context.emit("work", 2)

    def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
        context.state["total"] = sum(result.outputs)

    source = node(dispatch)
    source.link(node(lambda context: context.end(context.input)), "work")
    return await Flow(source, combine=combine).start({}).result()


async def nested_combine() -> RunResult[Any]:
    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("work", 2)
        context.emit("work", 3)

    def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
        context.emit(input=sum(result.outputs))

    source = node(dispatch)
    source.link(node(lambda context: context.end(context.input * 10)), "work")
    child = Flow(source, combine=combine)
    child.link(node(lambda context: context.state.__setitem__("total", context.input)))
    return await Flow(child).start({}).result()


async def declared_exit() -> RunResult[Any]:
    source = node(lambda context: context.emit("done", 4))
    return await Flow(source, exits=("done",)).start({}).result()


async def unknown_action() -> RunResult[Any]:
    source = node(lambda context: context.emit("missing"))
    return await Flow(source).start({}).result()


async def atomic_unknown() -> RunResult[Any]:
    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("valid", 1)
        context.emit("missing", 2)

    source = node(dispatch)
    source.link(
        node(lambda context: context.state.__setitem__("ran", context.input)),
        "valid",
    )
    return await Flow(source).start({}).result()


async def retry() -> RunResult[Any]:
    calls = 0

    def work(context: Context[dict[str, Any]]) -> None:
        nonlocal calls
        calls += 1
        context.state["calls"] = calls
        context.end(f"attempt-{calls}")
        if calls < 3:
            raise ValueError("retry")

    return await Flow(node(work, retry=RetryPolicy(max_attempts=3))).start({}).result()


async def node_recovery() -> RunResult[Any]:
    def fail(_context: Context[dict[str, Any]]) -> None:
        raise ValueError("failed")

    def recover(context: Context[dict[str, Any]], _failure: object) -> None:
        context.end("recovered")

    return await Flow(node(fail, recover=recover)).start({}).result()


async def flow_recovery() -> RunResult[Any]:
    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit("done", 1)
        context.emit("fail", 2)
        context.emit("late", 3)

    def fail(_context: Context[dict[str, Any]]) -> None:
        raise ValueError("failed")

    def recover(context: Context[dict[str, Any]], failure: ScopeFailure) -> None:
        context.state["settled"] = [item.output for item in failure.terminals]
        context.end("replacement")

    source = node(dispatch)
    source.link(node(lambda context: context.end(context.input)), "done")
    source.link(node(fail), "fail")
    source.link(node(lambda context: context.state.__setitem__("late", True)), "late")
    return await Flow(source, recover=recover).start({}).result()


async def combine_recovery() -> RunResult[Any]:
    def combine(_context: object, _result: ScopeResult) -> None:
        raise ValueError("combine")

    def recover(context: Context[dict[str, Any]], failure: ScopeFailure) -> None:
        context.state["combine_outputs"] = list(failure.result.outputs)  # type: ignore[union-attr]
        context.end(sum(failure.result.outputs))  # type: ignore[union-attr,arg-type]

    return (
        await Flow(
            node(lambda context: context.end(4)),
            combine=combine,
            recover=recover,
        )
        .start({})
        .result()
    )


async def invalid_return() -> RunResult[Any]:
    invalid = lambda _context: 42
    return await Flow(node(invalid)).start({}).result()  # type: ignore[arg-type]


async def activation_limit() -> RunResult[Any]:
    looping = node(lambda _context: None)
    looping.link(looping)
    return await Flow(looping, max_activations=3).start({}).result()


async def local_concurrency() -> RunResult[Any]:
    active = 0
    gate = asyncio.Event()

    def dispatch(context: Context[dict[str, Any]]) -> None:
        for value in range(4):
            context.emit("work", value)

    async def work(context: Context[dict[str, Any]]) -> None:
        nonlocal active
        active += 1
        context.state["peak"] = max(context.state.get("peak", 0), active)
        if active == 2:
            gate.set()
        await gate.wait()
        active -= 1

    source = node(dispatch)
    source.link(node(work), "work")
    return await Flow(source, concurrency=2).start({}).result()


async def nested_end() -> RunResult[Any]:
    child = Flow(node(lambda context: context.end(7)))
    child.link(node(lambda context: context.state.__setitem__("ran", True)))
    return await Flow(child).start({}).result()


async def nested_failure_terminals() -> RunResult[Any]:
    def dispatch(context: Context[dict[str, Any]]) -> None:
        context.emit(input=1)
        context.emit(input=2)

    def work(context: Context[dict[str, Any], int]) -> None:
        if context.input == 1:
            context.end(context.input)
        else:
            raise ValueError("failed")

    def recover(context: Context[dict[str, Any]], failure: ScopeFailure) -> None:
        context.state["settled"] = [item.output for item in failure.terminals]

    source = node(dispatch)
    source.link(node(work))
    return await Flow(Flow(source), recover=recover).start({}).result()


CASES = {
    "compiled_description": compiled_description,
    "implicit_link": implicit_link,
    "named_input": named_input,
    "unlabelled_input": unlabelled_input,
    "fanout_ends": fanout_ends,
    "output_presence": output_presence,
    "combine_preserve": combine_preserve,
    "nested_combine": nested_combine,
    "declared_exit": declared_exit,
    "unknown_action": unknown_action,
    "atomic_unknown": atomic_unknown,
    "retry": retry,
    "node_recovery": node_recovery,
    "flow_recovery": flow_recovery,
    "combine_recovery": combine_recovery,
    "invalid_return": invalid_return,
    "activation_limit": activation_limit,
    "local_concurrency": local_concurrency,
    "nested_end": nested_end,
    "nested_failure_terminals": nested_failure_terminals,
}


async def main() -> None:
    requested = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["cases"]
    ids = [case["id"] for case in requested]
    if set(ids) != set(CASES):
        raise ValueError("Python adapter case ids do not match fixture ids")
    snapshots = [
        {"id": case_id, "snapshot": case_snapshot(await CASES[case_id]())}
        for case_id in ids
    ]
    concurrent = next(
        item["snapshot"] for item in snapshots if item["id"] == "local_concurrency"
    )
    concurrent["terminals"].sort(key=lambda item: item["output"])
    for terminal in concurrent["terminals"]:
        terminal.pop("sequence")
    print(json.dumps(snapshots, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
