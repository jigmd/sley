from typing import Any

from caskada import Context, Flow, ScopeFailure, ScopeResult, node


def handler(context: Context[dict[str, Any], int]) -> None:
    context.end(context.input)


def combine(context: Context[dict[str, Any], object], result: ScopeResult) -> None:
    context.state["count"] = len(result.outputs)


def recover(context: Context[dict[str, Any], object], failure: ScopeFailure) -> None:
    if failure.result is not None:
        context.end(len(failure.result.outputs))
    elif failure.failing_activation_id is not None:
        context.end(failure.primary.failure_id)


flow: Flow[dict[str, Any]] = Flow(
    node(handler),
    combine=combine,
    recover=recover,
)
