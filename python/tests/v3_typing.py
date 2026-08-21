from __future__ import annotations

from typing import TypedDict, assert_type

from caskada import (
    Completed,
    Context,
    Failed,
    Flow,
    RetryPolicy,
    RunResult,
    ScopeFailure,
    ScopeResult,
    node,
)


class State(TypedDict, total=False):
    total: int


@node
def source(context: Context[State]) -> None:
    assert_type(context.state, State)
    assert_type(context.input, object)
    context.emit("work", 1)
    context.end()
    context.end(None)


async def worker(context: Context[State, int]) -> None:
    assert_type(context.input, int)
    context.end(context.input * 2)


worker_node = node(worker, retry=RetryPolicy(max_attempts=2))


def combine(context: Context[State], result: ScopeResult) -> None:
    assert_type(result.outputs, tuple[object, ...])
    context.state["total"] = sum(
        value for value in result.outputs if isinstance(value, int)
    )


def recover(context: Context[State], failure: ScopeFailure) -> None:
    assert_type(failure.primary.message, str)
    context.end()


source.link(worker_node, "work")
flow = Flow(source, combine=combine, recover=recover)
compiled = flow.compile()
handle = compiled.start(State())
assert_type(handle.done(), bool)


async def inspect_result() -> None:
    result = await handle.result()
    assert_type(result, Completed[State] | Failed[State])
    assert_type(result, RunResult[State])
    state = await compiled.run(State())
    assert_type(state, State)
