from __future__ import annotations

import logging
from collections.abc import Mapping

from caskada import Observer, RunEvent

_EVENT_LEVELS: Mapping[str, int] = {
    "failure_recorded": logging.ERROR,
    "failure_fenced": logging.ERROR,
    "cancellation_fenced": logging.WARNING,
    "run_started": logging.INFO,
    "run_finished": logging.INFO,
    "retry_scheduled": logging.INFO,
    "report": logging.INFO,
}


def logging_observer(logger: logging.Logger) -> Observer:
    """Create a synchronous observer that forwards each event to ``logger``."""

    def observe(event: RunEvent) -> None:
        logger.log(
            _EVENT_LEVELS.get(event.kind, logging.DEBUG),
            "Caskada event: %s",
            event.kind,
            extra={
                "caskada_event": event,
                "caskada_event_kind": event.kind,
                "caskada_run_id": event.run_id,
                "caskada_sequence": event.sequence,
            },
        )

    return observe
