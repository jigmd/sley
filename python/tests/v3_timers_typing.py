from typing import Any

from caskada import Abandoned, Context, Flow, RunOptions, RunResult, node


async def handler(context: Context[dict[str, Any]]) -> None:
    remaining: int | None = context.remaining_ms()
    if remaining == 0:
        context.cancellation.raise_if_cancelled()


flow = Flow(node(handler, timeout_ms=10))
options = RunOptions(deadline_ms=20, cancel_grace_ms=5, run_id="typed-run")
handle = flow.start({}, options=options)


async def inspect_result() -> None:
    result: RunResult[dict[str, Any]] = await handle.result()
    if result.status == "abandoned":
        abandoned: Abandoned[dict[str, Any]] = result
        assert abandoned.cause is not None
