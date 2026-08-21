from __future__ import annotations

from collections.abc import Awaitable
from typing import TypedDict, assert_type

from caskada import Completed, Context, Flow, RunHandle, RunResult, node


class State(TypedDict):
    answer: str


def answer(context: Context[State]) -> None:
    context.state["answer"] = "done"


flow = Flow(node(answer))
handle: RunHandle[State] = flow.start({"answer": "pending"})
pending: Awaitable[RunResult[State]] = handle.result()


async def inspect_result() -> None:
    result = await pending
    if result.status == "completed":
        assert_type(result, Completed[State])
        assert_type(result.state, State)
    assert_type(await flow.run({"answer": "pending"}), State)
