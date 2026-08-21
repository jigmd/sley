from __future__ import annotations

import asyncio
import unittest
from typing import Any

from caskada import (
    Context,
    Failed,
    Flow,
    LimitDetail,
    OptionValidationError,
    RetryPolicy,
    RunOptions,
    RunResult,
    node,
)


class ResourceLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_options_accept_limits_and_require_root_capacity(self) -> None:
        result = (
            await Flow(node(lambda _context: None))
            .start(
                {},
                options=RunOptions(
                    max_concurrency=1,
                    max_activations=2,
                    max_attempts=1,
                    max_transitions=1,
                    max_ready=1,
                    max_reports=1,
                    max_depth=1,
                ),
            )
            .result()
        )

        self.assertEqual(result.status, "completed")
        with self.assertRaises(OptionValidationError):
            RunOptions(max_activations=1)

    async def test_caught_emit_overflow_fences_and_discards_the_buffer(self) -> None:
        caught = False

        def source(context: Context[dict[str, Any]]) -> None:
            nonlocal caught
            context.emit("next", 1)
            try:
                context.emit("next", 2)
            except asyncio.CancelledError:
                caught = True

        source_node = node(source)
        source_node.link(node(lambda _context: None), "next")

        result = (
            await Flow(source_node)
            .start({}, options=RunOptions(max_transitions=1))
            .result()
        )

        self.assertTrue(caught)
        self._assert_limit(result, "max_transitions")
        self.assertEqual(result.stats.transitions, 0)
        self.assertEqual(result.stats.activations, 2)
        self.assertEqual(result.terminals, ())

    async def test_synthetic_default_consumes_transition_capacity(self) -> None:
        source_node = node(lambda _context: None)
        source_node.link(node(lambda _context: None))

        result = (
            await Flow(source_node)
            .start({}, options=RunOptions(max_transitions=1))
            .result()
        )

        self._assert_limit(result, "max_transitions")
        self.assertEqual(result.stats.transitions, 1)
        self.assertEqual(result.stats.activations, 3)
        self.assertEqual(result.stats.attempts, 2)

    async def test_run_activation_limit_rejects_a_complete_batch(self) -> None:
        source_node = node(lambda context: context.emit("next"))
        source_node.link(node(lambda _context: None), "next")

        result = (
            await Flow(source_node)
            .start({}, options=RunOptions(max_activations=2))
            .result()
        )

        self._assert_limit(result, "max_activations")
        self.assertEqual(result.stats.activations, 2)
        self.assertEqual(result.stats.transitions, 0)
        self.assertEqual(result.stats.peak_ready, 1)

    async def test_scope_activation_limit_is_fresh_and_direct(self) -> None:
        source_node = node(lambda context: context.emit("next"))
        source_node.link(node(lambda _context: None), "next")

        result = await Flow(source_node, max_activations=1).start({}).result()

        self._assert_limit(result, "scope_max_activations")
        self.assertEqual(result.failure.scope_id, 1)
        self.assertEqual(result.stats.activations, 2)
        self.assertEqual(result.stats.transitions, 0)

    async def test_ready_limit_rejects_fanout_atomically(self) -> None:
        def source(context: Context[dict[str, Any]]) -> None:
            context.emit("left")
            context.emit("right")

        source_node = node(source)
        source_node.link(node(lambda _context: None), "left")
        source_node.link(node(lambda _context: None), "right")

        result = (
            await Flow(source_node).start({}, options=RunOptions(max_ready=1)).result()
        )

        self._assert_limit(result, "max_ready")
        self.assertEqual(result.stats.activations, 2)
        self.assertEqual(result.stats.transitions, 0)
        self.assertEqual(result.stats.peak_ready, 1)

    async def test_batch_capacity_uses_normative_priority(self) -> None:
        source_node = node(lambda context: context.emit("next"))
        source_node.link(node(lambda _context: None), "next")

        result = (
            await Flow(source_node, max_activations=1)
            .start(
                {},
                options=RunOptions(
                    max_activations=2,
                    max_ready=1,
                ),
            )
            .result()
        )

        self._assert_limit(result, "max_activations")

    async def test_nested_depth_failure_allocates_no_child_scope(self) -> None:
        source_node = node(lambda context: context.emit("child"))
        child = Flow(node(lambda _context: None))
        source_node.link(child, "child")

        result = (
            await Flow(source_node).start({}, options=RunOptions(max_depth=1)).result()
        )

        self._assert_limit(result, "max_depth")
        self.assertEqual(result.failure.scope_id, 1)
        self.assertEqual(result.failure.activation_id, 3)
        self.assertEqual(result.stats.activations, 3)
        self.assertEqual(result.stats.transitions, 1)
        self.assertEqual(result.stats.scopes, 1)

    async def test_initial_attempt_exhaustion_invokes_no_more_callbacks(self) -> None:
        calls: list[str] = []

        def source(context: Context[dict[str, Any]]) -> None:
            calls.append("source")
            context.emit("next")

        def target(_context: Context[dict[str, Any]]) -> None:
            calls.append("target")

        source_node = node(source)
        source_node.link(node(target), "next")

        result = (
            await Flow(source_node)
            .start({}, options=RunOptions(max_attempts=1))
            .result()
        )

        self._assert_limit(result, "max_attempts")
        self.assertEqual(calls, ["source"])
        self.assertIsNone(result.failure.attempt)
        self.assertIsNone(result.failure.previous)
        self.assertEqual(result.stats.attempts, 1)
        self.assertEqual(result.stats.transitions, 1)

    async def test_retry_exhaustion_replaces_packet_before_delay_or_recovery(
        self,
    ) -> None:
        calls: list[object] = []

        def should_retry(_failure: object) -> bool:
            calls.append("policy")
            return True

        def delay(_attempt: int, _failure: object) -> int:
            calls.append("delay")
            return 0

        def handler(context: Context[dict[str, Any]]) -> None:
            calls.append(context.attempt)
            raise ValueError("failed")

        def recover(_context: Context[dict[str, Any]], _failure: object) -> None:
            calls.append("recover")

        worker = node(
            handler,
            retry=RetryPolicy(
                max_attempts=2,
                should_retry=should_retry,
                delay_ms=delay,
            ),
            recover=recover,
        )

        result = (
            await Flow(worker).start({}, options=RunOptions(max_attempts=1)).result()
        )

        self._assert_limit(result, "max_attempts")
        self.assertEqual(calls, [1, "policy"])
        self.assertIsNone(result.failure.attempt)
        self.assertIsNotNone(result.failure.previous)
        self.assertEqual(result.failure.previous.kind, "handler")  # type: ignore[union-attr]
        self.assertEqual(result.stats.attempts, 1)
        self.assertEqual(result.stats.retries, 0)

    async def test_forwarded_terminal_consumes_transition_capacity(self) -> None:
        source_node = node(lambda context: context.emit("child"))
        child = Flow(node(lambda context: context.end("done")))
        source_node.link(child, "child")

        result = (
            await Flow(source_node)
            .start({}, options=RunOptions(max_transitions=2))
            .result()
        )

        self._assert_limit(result, "max_transitions")
        self.assertEqual(result.stats.transitions, 2)
        self.assertEqual(result.terminals, ())

    async def test_batch_limit_retains_inherited_packet_suppression(self) -> None:
        async def source(context: Context[dict[str, Any]]) -> None:
            if context.attempt == 1:
                await context.cancellation.wait()
                raise ValueError("post-timeout")
            context.emit("next")

        source_node = node(
            source,
            retry=RetryPolicy(max_attempts=2),
            timeout_ms=5,
        )
        source_node.link(node(lambda _context: None), "next")

        result = (
            await Flow(source_node)
            .start(
                {},
                options=RunOptions(
                    max_activations=2,
                    cancel_grace_ms=100,
                ),
            )
            .result()
        )

        self._assert_limit(result, "max_activations")
        self.assertEqual(result.failure.previous.kind, "handler_timeout")  # type: ignore[union-attr]
        self.assertEqual([failure.kind for failure in result.suppressed], ["handler"])

    async def test_committed_limit_fence_beats_later_caller_cancellation(self) -> None:
        handle: Any = None

        def source(context: Context[dict[str, Any]]) -> None:
            context.emit()
            try:
                context.emit()
            except asyncio.CancelledError:
                pass
            handle.cancel("later")

        handle = Flow(node(source)).start(
            {},
            options=RunOptions(max_transitions=1),
        )
        result = await handle.result()

        self._assert_limit(result, "max_transitions")

    def _assert_limit(
        self,
        result: RunResult[dict[str, Any]],
        limit: str,
    ) -> None:
        self.assertIsInstance(result, Failed)
        if result.status != "failed":
            self.fail("expected a failed run")
        self.assertEqual(result.failure.kind, "limit")
        self.assertEqual(result.failure.message, "Run limit exceeded")
        self.assertIsNone(result.failure.cause)
        self.assertIsInstance(result.failure.detail, LimitDetail)
        if not isinstance(result.failure.detail, LimitDetail):
            self.fail("limit failure must carry LimitDetail")
        self.assertEqual(result.failure.detail.limit, limit)


if __name__ == "__main__":
    unittest.main()
