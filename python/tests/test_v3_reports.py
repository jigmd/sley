from __future__ import annotations

import asyncio
import time
import unittest
from typing import Any, cast

from caskada import (
    Context,
    Flow,
    LimitDetail,
    ReportEvent,
    RunEvent,
    RunOptions,
    ScopeFailure,
    ScopeResult,
    node,
)


class ReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_preserves_omission_and_explicit_none(self) -> None:
        events: list[RunEvent] = []

        def handler(context: Context[dict[str, Any]]) -> None:
            context.report("started")
            context.report("value", None)

        result = (
            await Flow(node(handler))
            .start({}, options=RunOptions(observer=events.append))
            .result()
        )
        reports = [
            cast(ReportEvent, event) for event in events if event.kind == "report"
        ]

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.stats.reports, 2)
        self.assertEqual(
            [event.payload.name for event in reports], ["started", "value"]
        )
        self.assertFalse(reports[0].payload.has_data)
        self.assertIsNone(reports[0].payload.data)
        self.assertTrue(reports[1].payload.has_data)
        self.assertIsNone(reports[1].payload.data)

    async def test_report_is_counted_without_an_observer(self) -> None:
        def handler(context: Context[dict[str, Any]]) -> None:
            context.report("progress", {"step": 1})

        result = await Flow(node(handler)).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.stats.reports, 1)

    async def test_invalid_report_name_is_uncharged_and_normalizes_if_uncaught(
        self,
    ) -> None:
        events: list[RunEvent] = []

        def caught(context: Context[dict[str, Any]]) -> None:
            with self.assertRaises(TypeError):
                context.report("")
            context.report("valid")

        caught_result = (
            await Flow(node(caught))
            .start({}, options=RunOptions(max_reports=1, observer=events.append))
            .result()
        )
        self.assertEqual(caught_result.status, "completed")
        self.assertEqual(caught_result.stats.reports, 1)
        self.assertEqual(sum(event.kind == "report" for event in events), 1)

        def uncaught(context: Context[dict[str, Any]]) -> None:
            context.report(1)  # type: ignore[arg-type]

        failed = await Flow(node(uncaught)).start({}).result()
        self.assertEqual(failed.status, "failed")
        if failed.status != "failed":
            self.fail("invalid report name must fail")
        self.assertEqual(failed.failure.kind, "invalid_outcome")
        self.assertEqual(failed.failure.detail.reason, "report_name")  # type: ignore[union-attr]
        self.assertEqual(failed.stats.reports, 0)

    async def test_report_overflow_commits_one_unrecoverable_limit(self) -> None:
        events: list[RunEvent] = []
        caught = 0

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal caught
            context.report("first")
            for name in ("overflow", "already_fenced"):
                try:
                    context.report(name)
                except asyncio.CancelledError:
                    caught += 1

        result = (
            await Flow(node(handler))
            .start(
                {},
                options=RunOptions(max_reports=1, observer=events.append),
            )
            .result()
        )

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("report overflow must fail")
        self.assertEqual(result.failure.kind, "limit")
        self.assertEqual(result.failure.detail, LimitDetail("max_reports"))
        self.assertEqual(result.failure.attempt, 1)
        self.assertEqual(result.stats.reports, 1)
        self.assertEqual(caught, 2)
        self.assertEqual(sum(event.kind == "report" for event in events), 1)
        self.assertEqual(sum(event.kind == "failure_fenced" for event in events), 1)

    async def test_reentrant_report_disables_the_observer_without_publication(
        self,
    ) -> None:
        events: list[RunEvent] = []
        active: Context[dict[str, Any]] | None = None

        def observer(event: RunEvent) -> None:
            events.append(event)
            if event.kind == "report":
                assert active is not None
                active.report("nested")

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal active
            active = context
            context.report("outer")

        result = (
            await Flow(node(handler))
            .start({}, options=RunOptions(observer=observer))
            .result()
        )
        reports = [event for event in events if event.kind == "report"]

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.stats.reports, 1)
        self.assertEqual(len(reports), 1)
        self.assertEqual(len(result.diagnostics), 1)
        self.assertEqual(
            result.diagnostics[0].message,
            "Observer reentrancy disabled",
        )
        self.assertEqual(result.diagnostics[0].event_sequence, reports[0].sequence)

    async def test_report_observer_cancellation_prevents_callback_resumption(
        self,
    ) -> None:
        events: list[RunEvent] = []
        resumed = False
        handle: Any = None

        def observer(event: RunEvent) -> None:
            events.append(event)
            if event.kind == "report":
                handle.cancel("observer")

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal resumed
            context.report("checkpoint")
            resumed = True

        handle = Flow(node(handler)).start({}, options=RunOptions(observer=observer))
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        self.assertFalse(resumed)
        report_index = next(
            i for i, event in enumerate(events) if event.kind == "report"
        )
        self.assertEqual(events[report_index + 1].kind, "cancellation_fenced")

    async def test_report_observer_time_can_trigger_attempt_timeout(self) -> None:
        resumed = False

        def observer(event: RunEvent) -> None:
            if event.kind == "report":
                time.sleep(0.6)

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal resumed
            context.report("slow")
            resumed = True

        result = (
            await Flow(node(handler, timeout_ms=500))
            .start(
                {},
                options=RunOptions(observer=observer, cancel_grace_ms=100),
            )
            .result()
        )

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("observer time must count against the attempt timeout")
        self.assertEqual(result.failure.kind, "handler_timeout")
        self.assertEqual(result.stats.reports, 1)
        self.assertFalse(resumed)

    async def test_report_observer_time_publishes_a_new_run_deadline_fence(
        self,
    ) -> None:
        events: list[RunEvent] = []
        resumed = False

        def observer(event: RunEvent) -> None:
            events.append(event)
            if event.kind == "report":
                time.sleep(0.6)

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal resumed
            context.report("slow")
            resumed = True

        result = (
            await Flow(node(handler))
            .start(
                {},
                options=RunOptions(
                    observer=observer,
                    deadline_ms=500,
                    cancel_grace_ms=100,
                ),
            )
            .result()
        )

        self.assertEqual(result.status, "cancelled")
        self.assertFalse(resumed)
        report_index = next(
            i for i, event in enumerate(events) if event.kind == "report"
        )
        fence = events[report_index + 1]
        self.assertEqual(fence.kind, "cancellation_fenced")
        if fence.kind == "cancellation_fenced":
            self.assertTrue(fence.payload.deadline)

    async def test_report_is_available_in_recovery_and_combine_callbacks(self) -> None:
        names: list[str] = []

        def observer(event: RunEvent) -> None:
            if event.kind == "report":
                names.append(event.payload.name)

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise ValueError("failed")

        def node_recover(context: Context[dict[str, Any]], _failure: object) -> None:
            context.report("node_recover")
            context.end("node")

        node_result = (
            await Flow(node(fail, recover=node_recover))
            .start({}, options=RunOptions(observer=observer))
            .result()
        )

        def flow_recover(
            context: Context[dict[str, Any]], _failure: ScopeFailure
        ) -> None:
            context.report("flow_recover")
            context.end("flow")

        flow_result = (
            await Flow(node(fail), recover=flow_recover)
            .start({}, options=RunOptions(observer=observer))
            .result()
        )

        def combine(context: Context[dict[str, Any]], _result: ScopeResult) -> None:
            context.report("flow_combine")

        combine_result = (
            await Flow(node(lambda context: context.end()), combine=combine)
            .start({}, options=RunOptions(observer=observer))
            .result()
        )

        self.assertEqual(node_result.status, "completed")
        self.assertEqual(flow_result.status, "completed")
        self.assertEqual(combine_result.status, "completed")
        self.assertEqual(names, ["node_recover", "flow_recover", "flow_combine"])

    async def test_report_capability_closes_with_context(self) -> None:
        retained: Context[dict[str, Any]] | None = None

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal retained
            retained = context

        result = await Flow(node(handler)).start({}).result()

        self.assertEqual(result.status, "completed")
        assert retained is not None
        with self.assertRaises(RuntimeError):
            retained.report("late")


if __name__ == "__main__":
    unittest.main()
