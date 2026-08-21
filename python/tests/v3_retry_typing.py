from typing import Any

from caskada import Context, Failure, Flow, RetryPolicy, node


def handler(context: Context[dict[str, Any], int]) -> None:
    assert context.attempt is not None
    context.end(context.input)


def should_retry(failure: Failure) -> bool:
    return failure.kind == "handler"


def retry_delay(failed_attempt: int, failure: Failure) -> int:
    return failed_attempt if failure.attempt is not None else 0


def recover(context: Context[dict[str, Any], int], failure: Failure) -> None:
    assert context.attempt is None
    context.end(failure.failure_id)


worker = node(
    handler,
    retry=RetryPolicy(
        max_attempts=3,
        should_retry=should_retry,
        delay_ms=retry_delay,
    ),
    recover=recover,
)
flow: Flow[dict[str, Any]] = Flow(worker)
