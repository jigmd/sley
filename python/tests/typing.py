from __future__ import annotations

from typing import TypedDict, assert_type

from sley import (
    CompiledDescription,
    Completed,
    Context,
    DescriptionElement,
    DescriptionFlow,
    DescriptionLink,
    DescriptionNode,
    DescriptionRoot,
    DescriptionScope,
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
description = compiled.describe()
assert_type(description, CompiledDescription)
assert_type(description["root"], DescriptionRoot)
assert_type(description["scopes"][0], DescriptionScope)
element = description["elements"][0]
assert_type(element, DescriptionElement)
assert_type(element["links"][0], DescriptionLink)
if element["kind"] == "node":
    assert_type(element, DescriptionNode)
    assert_type(element["max_attempts"], int)
else:
    assert_type(element, DescriptionFlow)
    assert_type(element["owned_scope_id"], int)
handle = compiled.start(State())
assert_type(handle.done(), bool)


async def inspect_result() -> None:
    result = await handle.result()
    assert_type(result, Completed[State] | Failed[State])
    assert_type(result, RunResult[State])
    state = await compiled.run(State())
    assert_type(state, State)
