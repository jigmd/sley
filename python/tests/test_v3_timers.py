from __future__ import annotations

import asyncio
import unittest
from typing import Any

from caskada import (
    Abandoned,
    Cancelled,
    Context,
    Failure,
    Flow,
    GraphDefinitionError,
    OptionValidationError,
    RetryPolicy,
    RunError,
    RunOptions,
    node,
)


class TimerAndAbandonmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_options_validate_and_preserve_an_explicit_run_id(self) -> None:
        options = RunOptions(deadline_ms=None, cancel_grace_ms=0, run_id="timer-run")
        seen: list[str] = []

        def handler(context: Context[dict[str, Any]]) -> None:
            seen.append(context.run_id)

        result = await Flow(node(handler)).start({}, options=options).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(seen, ["timer-run"])
        with self.assertRaises(OptionValidationError):
            RunOptions(deadline_ms=-1)
        with self.assertRaises(OptionValidationError):
            RunOptions(cancel_grace_ms=True)  # type: ignore[arg-type]
        with self.assertRaises(OptionValidationError):
            RunOptions(max_activations=4_294_967_295)

    async def test_zero_deadline_wins_before_callback_invocation(self) -> None:
        called = False

        def handler(_context: Context[dict[str, Any]]) -> None:
            nonlocal called
            called = True

        result = (
            await Flow(node(handler))
            .start({}, options=RunOptions(deadline_ms=0, cancel_grace_ms=0))
            .result()
        )

        self.assertIsInstance(result, Cancelled)
        self.assertFalse(called)
        if result.status != "cancelled":
            self.fail("zero deadline must cancel")
        self.assertEqual(result.cancellation.reason, "deadline_exceeded")
        self.assertTrue(result.cancellation.deadline)
        self.assertEqual(result.stats.attempts, 0)

    async def test_deadline_signals_cooperative_work_and_settles_cancelled(
        self,
    ) -> None:
        async def handler(context: Context[dict[str, Any]]) -> None:
            await context.cancellation.wait()
            context.cancellation.raise_if_cancelled()

        result = (
            await Flow(node(handler))
            .start({}, options=RunOptions(deadline_ms=5, cancel_grace_ms=100))
            .result()
        )

        self.assertEqual(result.status, "cancelled")
        if result.status != "cancelled":
            self.fail("deadline must control")
        self.assertTrue(result.cancellation.deadline)
        self.assertEqual(result.suppressed, ())

    async def test_caller_cancel_abandons_uncooperative_work_after_grace(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        late_control_closed = asyncio.Event()

        async def handler(context: Context[dict[str, Any]]) -> None:
            started.set()
            await release.wait()
            with self.assertRaises(RuntimeError):
                context.end("late")
            late_control_closed.set()

        handle = Flow(node(handler)).start({}, options=RunOptions(cancel_grace_ms=0))
        await started.wait()
        handle.cancel("shutdown")
        result = await handle.result()

        self.assertIsInstance(result, Abandoned)
        if result.status != "abandoned":
            self.fail("uncooperative callback must abandon")
        self.assertEqual(result.cause.reason, "shutdown")  # type: ignore[union-attr]
        self.assertEqual(result.terminals, ())
        release.set()
        await asyncio.wait_for(late_control_closed.wait(), timeout=1)

    async def test_zero_grace_wins_when_callback_returns_after_self_cancel(
        self,
    ) -> None:
        handle: Any = None

        def handler(_context: Context[dict[str, Any]]) -> None:
            handle.cancel("self")

        handle = Flow(node(handler)).start({}, options=RunOptions(cancel_grace_ms=0))
        result = await handle.result()

        self.assertEqual(result.status, "abandoned")
        if result.status != "abandoned":
            self.fail("zero grace must win equality")
        self.assertEqual(result.cause.reason, "self")  # type: ignore[union-attr]

    async def test_run_deadline_abandons_uncooperative_work(self) -> None:
        release = asyncio.Event()

        async def handler(_context: Context[dict[str, Any]]) -> None:
            await release.wait()

        result = (
            await Flow(node(handler))
            .start({}, options=RunOptions(deadline_ms=5, cancel_grace_ms=0))
            .result()
        )

        self.assertEqual(result.status, "abandoned")
        if result.status != "abandoned":
            self.fail("uncooperative deadline must abandon")
        self.assertNotIsInstance(result.cause, Failure)
        self.assertTrue(result.cause.deadline)
        release.set()
        await asyncio.sleep(0)

    async def test_node_timeout_must_be_positive(self) -> None:
        with self.assertRaises(GraphDefinitionError):
            node(lambda _context: None, timeout_ms=0)

    async def test_attempt_timeout_enters_recovery_with_a_fresh_token(self) -> None:
        recovered: list[Failure] = []

        async def handler(context: Context[dict[str, Any]]) -> None:
            await context.cancellation.wait()
            context.cancellation.raise_if_cancelled()

        def recover(context: Context[dict[str, Any]], failure: Failure) -> None:
            recovered.append(failure)
            self.assertFalse(context.cancellation.cancelled)
            context.end("recovered")

        result = (
            await Flow(node(handler, timeout_ms=5, recover=recover))
            .start({}, options=RunOptions(cancel_grace_ms=100))
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(recovered[0].kind, "handler_timeout")
        self.assertEqual(result.terminals[0].output, "recovered")

    async def test_timed_out_attempt_settles_before_retry_and_never_overlaps(
        self,
    ) -> None:
        live = 0
        peak = 0

        async def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            if context.attempt == 1:
                await context.cancellation.wait()
                live -= 1
                context.cancellation.raise_if_cancelled()
            live -= 1
            context.end("second")

        worker = node(
            handler,
            timeout_ms=5,
            retry=RetryPolicy(max_attempts=2),
        )
        result = (
            await Flow(worker)
            .start({}, options=RunOptions(cancel_grace_ms=100))
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(peak, 1)
        self.assertEqual(result.stats.attempts, 2)
        self.assertEqual(result.stats.retries, 1)

    async def test_attempt_timeout_abandons_uncooperative_work(self) -> None:
        release = asyncio.Event()

        async def handler(_context: Context[dict[str, Any]]) -> None:
            await release.wait()

        result = (
            await Flow(node(handler, timeout_ms=5))
            .start({}, options=RunOptions(cancel_grace_ms=0))
            .result()
        )

        self.assertEqual(result.status, "abandoned")
        if result.status != "abandoned":
            self.fail("attempt timeout must abandon")
        self.assertIsInstance(result.cause, Failure)
        self.assertEqual(result.cause.kind, "handler_timeout")
        release.set()
        await asyncio.sleep(0)

    async def test_post_timeout_error_is_suppressed_behind_timeout_primary(
        self,
    ) -> None:
        cause = RuntimeError("after timeout")

        async def handler(context: Context[dict[str, Any]]) -> None:
            await context.cancellation.wait()
            raise cause

        result = (
            await Flow(node(handler, timeout_ms=5))
            .start({}, options=RunOptions(cancel_grace_ms=100))
            .result()
        )

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("timeout must remain primary")
        self.assertEqual(result.failure.kind, "handler_timeout")
        self.assertEqual(len(result.suppressed), 1)
        self.assertEqual(result.suppressed[0].kind, "handler")
        self.assertIs(result.suppressed[0].cause, cause)
        self.assertIs(result.suppressed[0].previous, result.failure)

    async def test_remaining_ms_tracks_attempt_then_grace(self) -> None:
        seen: list[int | None] = []

        async def handler(context: Context[dict[str, Any]]) -> None:
            seen.append(context.remaining_ms())
            await context.cancellation.wait()
            seen.append(context.remaining_ms())
            context.cancellation.raise_if_cancelled()

        result = (
            await Flow(node(handler, timeout_ms=20))
            .start({}, options=RunOptions(deadline_ms=1_000, cancel_grace_ms=100))
            .result()
        )

        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(seen[0])
        self.assertLessEqual(seen[0] or 0, 20)
        self.assertIsNotNone(seen[1])
        self.assertLessEqual(seen[1] or 0, 100)

    async def test_run_deadline_wins_a_zero_timeout_tie(self) -> None:
        called = False

        def handler(_context: Context[dict[str, Any]]) -> None:
            nonlocal called
            called = True

        result = (
            await Flow(node(handler, timeout_ms=1))
            .start({}, options=RunOptions(deadline_ms=0, cancel_grace_ms=0))
            .result()
        )

        self.assertEqual(result.status, "cancelled")
        self.assertFalse(called)
        if result.status != "cancelled":
            self.fail("run deadline must win")
        self.assertTrue(result.cancellation.deadline)
        self.assertEqual(result.suppressed, ())

    async def test_run_projection_raises_the_exact_abandoned_result(self) -> None:
        async def handler(_context: Context[dict[str, Any]]) -> None:
            await asyncio.Future()

        with self.assertRaises(RunError) as raised:
            await Flow(node(handler)).run(
                {}, options=RunOptions(deadline_ms=5, cancel_grace_ms=0)
            )

        self.assertEqual(raised.exception.result.status, "abandoned")
        self.assertEqual(str(raised.exception), "Caskada run abandoned")


if __name__ == "__main__":
    unittest.main()
