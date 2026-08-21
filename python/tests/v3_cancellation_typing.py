from typing import Any

from caskada import Cancellation, Cancelled, Context, Flow, RunResult, node


async def handler(context: Context[dict[str, Any]]) -> None:
    token: Cancellation = context.cancellation
    if not token.cancelled:
        await token.wait()
    token.raise_if_cancelled()


flow = Flow(node(handler))
handle = flow.start({})
handle.cancel("stop")


async def inspect_result() -> None:
    result: RunResult[dict[str, Any]] = await handle.result()
    if result.status == "cancelled":
        cancelled: Cancelled[dict[str, Any]] = result
        assert cancelled.cancellation.deadline is False
