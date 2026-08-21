from __future__ import annotations

import asyncio
import unittest
from typing import Any

from caskada import (
    Cancellation,
    Cancelled,
    Context,
    Failure,
    Flow,
    RetryPolicy,
    ScopeFailure,
    node,
)


class CooperativeCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_before_admission_skips_application_code(self) -> None:
        called = False

        def handler(_context: Context[dict[str, Any]]) -> None:
            nonlocal called
            called = True

        handle = Flow(node(handler)).start({})
        handle.cancel()
        result = await handle.result()

        self.assertIsInstance(result, Cancelled)
        self.assertEqual(result.status, "cancelled")
        if result.status != "cancelled":
            self.fail("caller cancellation must cancel")
        self.assertFalse(called)
        self.assertEqual(result.cancellation.reason, "cancelled")
        self.assertFalse(result.cancellation.deadline)
        self.assertEqual(result.terminals, ())
        self.assertEqual(result.suppressed, ())
        self.assertEqual(result.stats.attempts, 0)

    async def test_first_cancel_reason_wins_and_later_calls_are_noops(self) -> None:
        first_reason = object()
        handle = Flow(node(lambda _context: None)).start({})
        handle.cancel(first_reason)
        handle.cancel("later")
        result = await handle.result()
        handle.cancel("after settlement")

        self.assertTrue(handle.done())
        self.assertEqual(result.status, "cancelled")
        if result.status != "cancelled":
            self.fail("caller cancellation must cancel")
        self.assertIs(result.cancellation.reason, first_reason)

    async def test_context_exposes_metadata_and_a_durable_cooperative_token(
        self,
    ) -> None:
        started = asyncio.Event()
        observed: dict[str, object] = {}
        retained: list[Cancellation] = []

        async def handler(context: Context[dict[str, Any]]) -> None:
            retained.append(context.cancellation)
            observed.update(
                run_id=context.run_id,
                scope_id=context.scope_id,
                activation_id=context.activation_id,
                parent_activation_id=context.parent_activation_id,
                attempt=context.attempt,
                phase=context.phase,
                remaining=context.remaining_ms(),
                cancelled=context.cancellation.cancelled,
                reason=context.cancellation.reason,
            )
            started.set()
            await context.cancellation.wait()
            context.cancellation.raise_if_cancelled()

        handle = Flow(node(handler)).start({})
        await started.wait()
        reason = {"shutdown": True}
        handle.cancel(reason)
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        self.assertRegex(str(observed["run_id"]), r"^run-[1-9][0-9]*$")
        self.assertEqual(observed["scope_id"], 1)
        self.assertEqual(observed["activation_id"], 2)
        self.assertEqual(observed["parent_activation_id"], 1)
        self.assertEqual(observed["attempt"], 1)
        self.assertEqual(observed["phase"], "handle")
        self.assertIsNone(observed["remaining"])
        self.assertFalse(observed["cancelled"])
        self.assertIsNone(observed["reason"])
        self.assertTrue(retained[0].cancelled)
        self.assertIs(retained[0].reason, reason)
        with self.assertRaises(asyncio.CancelledError):
            retained[0].raise_if_cancelled()

    async def test_return_after_signal_discards_the_callback_buffer(self) -> None:
        started = asyncio.Event()

        async def handler(context: Context[dict[str, Any]]) -> None:
            context.end("must-not-commit")
            started.set()
            await context.cancellation.wait()

        handle = Flow(node(handler)).start({})
        await started.wait()
        handle.cancel("stop")
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.terminals, ())
        self.assertEqual(result.stats.transitions, 0)

    async def test_unrelated_error_after_signal_is_suppressed(self) -> None:
        started = asyncio.Event()
        cause = RuntimeError("after signal")

        async def handler(context: Context[dict[str, Any]]) -> None:
            started.set()
            await context.cancellation.wait()
            raise cause

        handle = Flow(node(handler)).start({})
        await started.wait()
        handle.cancel()
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        if result.status != "cancelled":
            self.fail("caller cancellation must remain controlling")
        self.assertEqual(len(result.suppressed), 1)
        self.assertEqual(result.suppressed[0].kind, "handler")
        self.assertIs(result.suppressed[0].cause, cause)
        self.assertEqual(result.suppressed[0].attempt, 1)

    async def test_prior_terminal_survives_and_ready_work_is_discarded(self) -> None:
        waiting = asyncio.Event()

        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("done", 1)
            context.emit("wait", 2)
            context.emit("late", 3)

        def done(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input)

        async def wait(context: Context[dict[str, Any], int]) -> None:
            waiting.set()
            await context.cancellation.wait()

        def late(context: Context[dict[str, Any], int]) -> None:
            context.state["late"] = context.input

        source = node(dispatch)
        source.link(node(done), "done")
        source.link(node(wait), "wait")
        source.link(node(late), "late")
        handle = Flow(source).start({})
        await waiting.wait()
        handle.cancel()
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(len(result.terminals), 1)
        self.assertEqual(result.terminals[0].output, 1)
        self.assertNotIn("late", result.state)

    async def test_cancellation_wakes_a_retry_delay_and_retains_its_packet(
        self,
    ) -> None:
        scheduled = asyncio.Event()

        def handler(_context: Context[dict[str, Any]]) -> None:
            raise RuntimeError("retry")

        def delay(_attempt: int, _failure: Failure) -> int:
            scheduled.set()
            return 4_294_967_295

        worker = node(
            handler,
            retry=RetryPolicy(
                max_attempts=2,
                delay_ms=delay,
            ),
        )
        handle = Flow(worker).start({})
        await scheduled.wait()
        handle.cancel()
        result = await asyncio.wait_for(handle.result(), timeout=1)

        self.assertEqual(result.status, "cancelled")
        if result.status != "cancelled":
            self.fail("retry cancellation must cancel")
        self.assertEqual(len(result.suppressed), 1)
        self.assertEqual(result.suppressed[0].kind, "handler")
        self.assertEqual(result.stats.attempts, 1)
        self.assertEqual(result.stats.retries, 1)

    async def test_node_and_flow_recovery_keep_active_packets_on_cancel(self) -> None:
        for layer in ("node", "flow"):
            with self.subTest(layer=layer):
                started = asyncio.Event()

                def fail(_context: Context[dict[str, Any]]) -> None:
                    raise RuntimeError("handler")

                async def node_recover(
                    context: Context[dict[str, Any]],
                    _failure: Failure,
                    started_event: asyncio.Event = started,
                ) -> None:
                    started_event.set()
                    await context.cancellation.wait()
                    context.cancellation.raise_if_cancelled()

                async def flow_recover(
                    context: Context[dict[str, Any], object],
                    _failure: ScopeFailure,
                    started_event: asyncio.Event = started,
                ) -> None:
                    started_event.set()
                    await context.cancellation.wait()
                    context.cancellation.raise_if_cancelled()

                flow = (
                    Flow(node(fail, recover=node_recover))
                    if layer == "node"
                    else Flow(node(fail), recover=flow_recover)
                )
                handle = flow.start({})
                await started.wait()
                handle.cancel()
                result = await handle.result()

                self.assertEqual(result.status, "cancelled")
                if result.status != "cancelled":
                    self.fail("recovery cancellation must cancel")
                self.assertEqual(len(result.suppressed), 1)
                self.assertEqual(result.suppressed[0].kind, "handler")

    async def test_unsignalled_cancelled_error_is_an_ordinary_failure(self) -> None:
        cause = asyncio.CancelledError()

        def handler(_context: Context[dict[str, Any]]) -> None:
            raise cause

        result = await Flow(node(handler)).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("unsignalled CancelledError must fail")
        self.assertEqual(result.failure.kind, "handler")
        self.assertIs(result.failure.cause, cause)

    async def test_cancelling_flow_run_rethrows_without_injecting_its_callback(
        self,
    ) -> None:
        started = asyncio.Event()
        cooperated = asyncio.Event()

        async def handler(context: Context[dict[str, Any]]) -> None:
            started.set()
            await context.cancellation.wait()
            cooperated.set()

        task = asyncio.create_task(Flow(node(handler)).run({}))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cooperated.wait(), timeout=1)


if __name__ == "__main__":
    unittest.main()
