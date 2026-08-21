from __future__ import annotations

from collections.abc import Awaitable
from typing import NotRequired, TypedDict, assert_type

from caskada import Context, Flow, ScopeResult, node


class State(TypedDict):
    count: int
    outputs: NotRequired[list[object]]


class Job(TypedDict):
    value: int


def handler(context: Context[State, Job]) -> None:
    assert_type(context.state, State)
    assert_type(context.input, Job)
    context.emit()
    context.emit(input={"value": 1})
    context.emit("next")
    context.emit("next", {"value": 2})
    context.end()
    context.end(None)
    context.emit(None)  # type: ignore[call-overload]


def combine(context: Context[State], result: ScopeResult) -> None:
    context.state["outputs"] = list(result.outputs)


entry = node(handler)
flow = Flow(entry, combine=combine)
assert_type(flow, Flow[State])
pending: Awaitable[State] = flow.compile().run({"count": 0})
