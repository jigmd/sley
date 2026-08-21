from __future__ import annotations

from typing import assert_type

from caskada import (
    Context,
    ReportEvent,
    ReportWithDataPayload,
    ReportWithoutDataPayload,
    RunEvent,
)


def handler(context: Context[dict[str, object]]) -> None:
    assert_type(context.report("started"), None)
    assert_type(context.report("value", None), None)


def observer(event: RunEvent) -> None:
    if isinstance(event, ReportEvent):
        assert_type(event.payload.name, str)
        assert_type(event.payload.has_data, bool)
        if isinstance(event.payload, ReportWithDataPayload):
            assert_type(event.payload.data, object)
        else:
            assert_type(event.payload, ReportWithoutDataPayload)
            assert_type(event.payload.data, None)
