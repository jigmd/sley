from __future__ import annotations

import asyncio
import unittest
from typing import Any

from caskada import Context, Flow, RetryPolicy, RunOptions, node


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_topology_auto_reaches_root_scope_width(self) -> None:
        peak, result = await self._gated_fanout(8)

        self.assertEqual(peak, 8)
        self.assertEqual(result.stats.peak_callbacks, 8)

    async def test_serial_parent_does_not_throttle_parallel_child(self) -> None:
        peak, result = await self._gated_fanout(8, nested=True)

        self.assertEqual(peak, 8)
        self.assertEqual(result.stats.peak_callbacks, 8)

    async def test_explicit_global_ceiling_throttles_local_scope(self) -> None:
        peak, result = await self._gated_fanout(8, max_concurrency=3)

        self.assertEqual(peak, 3)
        self.assertEqual(result.stats.peak_callbacks, 3)

    async def test_all_serial_scopes_never_overlap_callbacks(self) -> None:
        active = 0
        peak = 0

        async def first(_context: Context[dict[str, Any]]) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1

        async def second(_context: Context[dict[str, Any]]) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1

        first_node = node(first)
        second_node = node(second)
        first_node.link(second_node)
        inner = Flow(first_node, concurrency=1)
        result = (
            await Flow(inner, concurrency=1)
            .start({}, options=RunOptions(max_concurrency=8))
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(peak, 1)
        self.assertEqual(result.stats.peak_callbacks, 1)

    async def test_retry_delay_releases_the_only_callback_permit(self) -> None:
        order: list[str] = []

        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("work", "retry")
            context.emit("work", "peer")

        async def work(context: Context[dict[str, Any], str]) -> None:
            order.append(f"{context.input}:{context.attempt}")
            if context.input == "retry" and context.attempt == 1:
                raise ValueError("retry once")

        dispatch_node = node(dispatch)
        work_node = node(
            work,
            retry=RetryPolicy(
                max_attempts=2,
                should_retry=lambda _failure: True,
                delay_ms=10,
            ),
        )
        dispatch_node.link(work_node, "work")

        result = (
            await Flow(dispatch_node, concurrency=2)
            .start({}, options=RunOptions(max_concurrency=1))
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(order, ["retry:1", "peer:1", "retry:2"])
        self.assertEqual(result.stats.peak_callbacks, 1)

    async def test_due_retry_precedes_a_waiting_new_activation(self) -> None:
        order: list[str] = []
        blocker_started = asyncio.Event()
        release_blocker = asyncio.Event()

        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("work", "retry")
            context.emit("work", "blocker")
            context.emit("work", "new")

        async def work(context: Context[dict[str, Any], str]) -> None:
            order.append(f"{context.input}:{context.attempt}")
            if context.input == "retry" and context.attempt == 1:
                raise ValueError("retry once")
            if context.input == "blocker":
                blocker_started.set()
                await release_blocker.wait()

        dispatch_node = node(dispatch)
        work_node = node(
            work,
            retry=RetryPolicy(
                max_attempts=2,
                should_retry=lambda _failure: True,
                delay_ms=10,
            ),
        )
        dispatch_node.link(work_node, "work")
        handle = Flow(dispatch_node, concurrency=3).start(
            {},
            options=RunOptions(max_concurrency=1),
        )

        await asyncio.wait_for(blocker_started.wait(), 1)
        await asyncio.sleep(0.02)
        release_blocker.set()
        result = await asyncio.wait_for(handle.result(), 1)

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            order,
            ["retry:1", "blocker:1", "retry:2", "new:1"],
        )

    async def test_new_callbacks_rotate_between_eligible_scopes(self) -> None:
        order: list[tuple[str, int]] = []

        def root_dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("batch", "A")
            context.emit("batch", "B")

        def child_dispatch(context: Context[dict[str, Any], str]) -> None:
            for index in range(3):
                context.emit("work", (context.input, index))

        async def work(
            context: Context[dict[str, Any], tuple[str, int]],
        ) -> None:
            order.append(context.input)
            await asyncio.sleep(0)

        root_node = node(root_dispatch)
        child_node = node(child_dispatch)
        work_node = node(work)
        child_node.link(work_node, "work")
        child = Flow(child_node, concurrency=3)
        root_node.link(child, "batch")

        result = (
            await Flow(root_node, concurrency=2)
            .start({}, options=RunOptions(max_concurrency=1))
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertLess(order.index(("B", 0)), order.index(("A", 2)))

    async def test_scope_failure_signals_sibling_before_recovery(self) -> None:
        sibling_signalled = False

        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("work", "failure")
            context.emit("work", "sibling")

        async def work(context: Context[dict[str, Any], str]) -> None:
            nonlocal sibling_signalled
            if context.input == "failure":
                await asyncio.sleep(0)
                raise ValueError("failed")
            await context.cancellation.wait()
            sibling_signalled = context.cancellation.cancelled

        def recover(context: Context[dict[str, Any]], _failure: object) -> None:
            context.state["recovered"] = True
            context.end()

        dispatch_node = node(dispatch)
        work_node = node(work)
        dispatch_node.link(work_node, "work")

        result = (
            await Flow(
                dispatch_node,
                concurrency=2,
                recover=recover,
            )
            .start({})
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertTrue(result.state["recovered"])
        self.assertTrue(sibling_signalled)
        self.assertEqual(result.stats.peak_callbacks, 2)

    async def _gated_fanout(
        self,
        width: int,
        *,
        nested: bool = False,
        max_concurrency: int | None = None,
    ) -> tuple[int, Any]:
        active = 0
        peak = 0
        threshold = width if max_concurrency is None else max_concurrency
        started = asyncio.Event()
        release = asyncio.Event()

        def dispatch(context: Context[dict[str, Any]]) -> None:
            for index in range(width):
                context.emit("work", index)

        async def work(_context: Context[dict[str, Any], int]) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == threshold:
                started.set()
            await release.wait()
            active -= 1

        dispatch_node = node(dispatch)
        work_node = node(work)
        dispatch_node.link(work_node, "work")
        flow = Flow(dispatch_node, concurrency=width)
        if nested:
            flow = Flow(flow, concurrency=1)
        options = (
            None
            if max_concurrency is None
            else RunOptions(max_concurrency=max_concurrency)
        )
        handle = flow.start({}, options=options)
        await asyncio.wait_for(started.wait(), 1)
        release.set()
        result = await asyncio.wait_for(handle.result(), 1)
        return peak, result


if __name__ == "__main__":
    unittest.main()
