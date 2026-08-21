from __future__ import annotations

from typing import assert_type

from caskada import (
    CallbackFinishedEvent,
    Context,
    Flow,
    RunEvent,
    RunOptions,
    node,
)


def observe(event: RunEvent) -> None:
    assert_type(event.sequence, int)
    assert_type(event.run_id, str)
    if isinstance(event, CallbackFinishedEvent):
        assert_type(event.payload.activation_id, int)


def handler(_context: Context[dict[str, object]]) -> None:
    return None


flow = Flow(node(handler))
handle = flow.start({}, options=RunOptions(observer=observe, run_id="typed"))
assert_type(handle.done(), bool)
