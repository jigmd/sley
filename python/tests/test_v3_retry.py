from __future__ import annotations

import time
import unittest
from typing import Any, cast
from unittest.mock import patch

from caskada import (
    Context,
    Failure,
    Flow,
    InvalidOutcomeDetail,
    RetryPolicy,
    node,
)


class RetryAndRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_reuses_input_and_state_but_discards_failed_buffers(
        self,
    ) -> None:
        payload = object()
        states: list[dict[str, Any]] = []
        inputs: list[object] = []
        policy_failures: list[Failure] = []
        delay_calls: list[tuple[int, Failure]] = []

        def handle(context: Context[dict[str, Any], object]) -> None:
            states.append(context.state)
            inputs.append(context.input)
            context.state["calls"] = cast(int, context.state.get("calls", 0)) + 1
            context.end(f"attempt-{context.attempt}")
            if context.attempt != 3:
                raise LookupError(f"failed-{context.attempt}")

        def should_retry(failure: Failure) -> bool:
            policy_failures.append(failure)
            return True

        def delay_ms(attempt: int, failure: Failure) -> int:
            delay_calls.append((attempt, failure))
            return 0

        worker = node(
            handle,
            retry=RetryPolicy(
                max_attempts=3,
                should_retry=should_retry,
                delay_ms=delay_ms,
            ),
        )
        dispatch = node(lambda context: context.emit("work", payload))
        dispatch.link(worker, "work")
        result = await Flow(dispatch).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.state, {"calls": 3})
        self.assertEqual(
            [terminal.output for terminal in result.terminals], ["attempt-3"]
        )
        self.assertEqual(result.stats.attempts, 4)
        self.assertEqual(result.stats.retries, 2)
        self.assertEqual(result.stats.transitions, 2)
        self.assertEqual(inputs, [payload, payload, payload])
        self.assertIs(states[0], states[1])
        self.assertIs(states[1], states[2])
        self.assertEqual([failure.attempt for failure in policy_failures], [1, 2])
        self.assertIsNone(policy_failures[0].previous)
        self.assertIs(policy_failures[1].previous, policy_failures[0])
        self.assertEqual(
            delay_calls, [(1, policy_failures[0]), (2, policy_failures[1])]
        )

    async def test_exhaustion_skips_policy_and_passes_exact_packet_to_recovery(
        self,
    ) -> None:
        policy_calls: list[Failure] = []
        delay_calls: list[Failure] = []
        recovered: list[Failure] = []

        def handle(_context: Context[dict[str, Any]]) -> None:
            raise RuntimeError("failed")

        def should_retry(failure: Failure) -> bool:
            policy_calls.append(failure)
            return True

        def delay_ms(_attempt: int, failure: Failure) -> int:
            delay_calls.append(failure)
            return 0

        def recover(context: Context[dict[str, Any]], failure: Failure) -> None:
            recovered.append(failure)
            self.assertIsNone(context.attempt)

        worker = node(
            handle,
            retry=RetryPolicy(
                max_attempts=2,
                should_retry=should_retry,
                delay_ms=delay_ms,
            ),
            recover=recover,
        )
        result = await Flow(worker).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("zero-emission recovery must propagate its packet")
        self.assertEqual(len(policy_calls), 1)
        self.assertEqual(len(delay_calls), 1)
        self.assertEqual(len(recovered), 1)
        self.assertIs(result.failure, recovered[0])
        self.assertEqual(result.failure.attempt, 2)
        self.assertIs(result.failure.previous, policy_calls[0])
        self.assertEqual(result.stats.attempts, 2)
        self.assertEqual(result.stats.retries, 1)

    async def test_false_predicate_skips_delay_and_enters_recovery(self) -> None:
        cause = ValueError("declined")
        delay_called = False
        recovered: list[Failure] = []

        def handle(_context: Context[dict[str, Any]]) -> None:
            raise cause

        def delay_ms(_attempt: int, _failure: Failure) -> int:
            nonlocal delay_called
            delay_called = True
            return 0

        def recover(context: Context[dict[str, Any]], failure: Failure) -> None:
            recovered.append(failure)
            context.end("recovered")

        worker = node(
            handle,
            retry=RetryPolicy(
                max_attempts=3,
                should_retry=lambda _failure: False,
                delay_ms=delay_ms,
            ),
            recover=recover,
        )
        result = await Flow(worker).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertFalse(delay_called)
        self.assertEqual(len(recovered), 1)
        self.assertIs(recovered[0].cause, cause)
        self.assertEqual(
            [terminal.output for terminal in result.terminals], ["recovered"]
        )
        self.assertEqual(result.stats.attempts, 1)
        self.assertEqual(result.stats.retries, 0)

    async def test_recovery_emission_consumes_packet_and_keeps_activation_data(
        self,
    ) -> None:
        payload = {"job": 7}
        handler_state: list[dict[str, Any]] = []
        recovery_state: list[dict[str, Any]] = []
        recovered: list[Failure] = []

        def handle(context: Context[dict[str, Any], object]) -> None:
            handler_state.append(context.state)
            context.state["attempted"] = True
            raise OSError("temporary")

        def recover(context: Context[dict[str, Any], object], failure: Failure) -> None:
            recovery_state.append(context.state)
            recovered.append(failure)
            self.assertIs(context.input, payload)
            self.assertIsNone(context.attempt)
            context.emit("resume", 9)

        def resume(context: Context[dict[str, Any], int]) -> None:
            context.state["value"] = context.input
            context.end()

        worker = node(handle, recover=recover)
        worker.link(node(resume), "resume")
        dispatch = node(lambda context: context.emit("work", payload))
        dispatch.link(worker, "work")
        result = await Flow(dispatch).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.state, {"attempted": True, "value": 9})
        self.assertIs(handler_state[0], recovery_state[0])
        self.assertEqual(recovered[0].kind, "handler")
        self.assertEqual(result.stats.attempts, 3)
        self.assertEqual(result.stats.transitions, 3)

    async def test_policy_failures_are_unrecoverable_replacements(self) -> None:
        policy_cause = ArithmeticError("policy")
        recovery_called = False

        def handle(_context: Context[dict[str, Any]]) -> None:
            raise LookupError("handler")

        def fail_policy(_failure: Failure) -> bool:
            raise policy_cause

        def recover(_context: Context[dict[str, Any]], _failure: Failure) -> None:
            nonlocal recovery_called
            recovery_called = True

        worker = node(
            handle,
            retry=RetryPolicy(max_attempts=2, should_retry=fail_policy),
            recover=recover,
        )
        result = await Flow(worker).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("policy failure must fail the run")
        self.assertFalse(recovery_called)
        self.assertEqual(result.failure.kind, "retry_policy")
        self.assertIs(result.failure.cause, policy_cause)
        self.assertEqual(result.failure.attempt, 1)
        self.assertIsNotNone(result.failure.previous)
        self.assertEqual(result.failure.previous.kind, "handler")  # type: ignore[union-attr]
        self.assertEqual(result.stats.retries, 0)

    async def test_invalid_policy_values_are_not_coerced(self) -> None:
        async def asynchronous_answer() -> bool:
            return True

        cases: tuple[RetryPolicy, ...] = (
            RetryPolicy(max_attempts=2, should_retry=lambda _failure: 1),  # type: ignore[arg-type,return-value]
            RetryPolicy(
                max_attempts=2,
                should_retry=lambda _failure: True,
                delay_ms=lambda _attempt, _failure: True,  # type: ignore[arg-type,return-value]
            ),
            RetryPolicy(
                max_attempts=2,
                should_retry=lambda _failure: asynchronous_answer(),  # type: ignore[arg-type,return-value]
            ),
        )

        for policy in cases:
            with self.subTest(policy=policy):
                worker = node(
                    lambda _context: (_ for _ in ()).throw(RuntimeError("handler")),
                    retry=policy,
                )
                result = await Flow(worker).start({}).result()
                self.assertEqual(result.status, "failed")
                if result.status != "failed":
                    self.fail("invalid policy result must fail")
                self.assertEqual(result.failure.kind, "retry_policy")
                self.assertIsNone(result.failure.cause)
                self.assertEqual(result.failure.attempt, 1)
                self.assertEqual(result.failure.previous.kind, "handler")  # type: ignore[union-attr]

    async def test_callback_delay_is_applied_before_readmission(self) -> None:
        calls = 0

        def handle(context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("retry")
            context.end()

        worker = node(
            handle,
            retry=RetryPolicy(
                max_attempts=2,
                delay_ms=lambda _attempt, _failure: 10,
            ),
        )
        started = time.monotonic()
        result = await Flow(worker).start({}).result()
        elapsed = time.monotonic() - started

        self.assertEqual(result.status, "completed")
        self.assertGreaterEqual(elapsed, 0.005)
        self.assertEqual(result.stats.retries, 1)

    async def test_large_delay_is_chunked_without_shortening(self) -> None:
        calls = 0

        def handle(context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("retry")
            context.end()

        timeouts: list[float] = []

        async def expire(awaitable: Any, *, timeout: float) -> None:
            awaitable.close()
            timeouts.append(timeout)
            raise TimeoutError

        worker = node(
            handle,
            retry=RetryPolicy(
                max_attempts=2,
                delay_ms=lambda _attempt, _failure: 4_294_967_295,
            ),
        )
        with patch("caskada._timing.asyncio.wait_for", new=expire):
            result = await Flow(worker).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            timeouts,
            [2_147_483.647, 2_147_483.647, 0.001],
        )

    async def test_recovery_failures_replace_the_handler_packet(self) -> None:
        recovery_cause = RuntimeError("recovery")

        def handle(_context: Context[dict[str, Any]]) -> None:
            raise LookupError("handler")

        def recover(_context: Context[dict[str, Any]], _failure: Failure) -> None:
            raise recovery_cause

        result = await Flow(node(handle, recover=recover)).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("recovery throw must fail")
        self.assertEqual(result.failure.kind, "node_recovery")
        self.assertIs(result.failure.cause, recovery_cause)
        self.assertIsNone(result.failure.attempt)
        self.assertEqual(result.failure.previous.kind, "handler")  # type: ignore[union-attr]

        def wrong_recovery(
            _context: Context[dict[str, Any]], _failure: Failure
        ) -> object:
            return object()

        wrong = (
            await Flow(
                node(handle, recover=wrong_recovery),  # type: ignore[arg-type]
            )
            .start({})
            .result()
        )
        self.assertEqual(wrong.status, "failed")
        if wrong.status != "failed":
            self.fail("wrong recovery return must fail")
        self.assertEqual(wrong.failure.kind, "invalid_outcome")
        self.assertEqual(
            wrong.failure.detail,
            InvalidOutcomeDetail("wrong_return_type"),
        )
        self.assertIsNone(wrong.failure.attempt)
        self.assertEqual(wrong.failure.previous.kind, "handler")  # type: ignore[union-attr]

    async def test_invalid_outcomes_bypass_recovery_and_recovery_preflight_replaces(
        self,
    ) -> None:
        recovery_called = False

        def invalid_handler(_context: Context[dict[str, Any]]) -> object:
            return object()

        def must_not_recover(
            _context: Context[dict[str, Any]], _failure: Failure
        ) -> None:
            nonlocal recovery_called
            recovery_called = True

        invalid = (
            await Flow(
                node(
                    invalid_handler,  # type: ignore[arg-type]
                    recover=must_not_recover,
                )
            )
            .start({})
            .result()
        )
        self.assertEqual(invalid.status, "failed")
        self.assertFalse(recovery_called)
        if invalid.status != "failed":
            self.fail("invalid outcome must fail")
        self.assertEqual(invalid.failure.kind, "invalid_outcome")

        def handler(_context: Context[dict[str, Any]]) -> None:
            raise RuntimeError("handler")

        def missing_route(context: Context[dict[str, Any]], _failure: Failure) -> None:
            context.emit("missing")

        preflight = await Flow(node(handler, recover=missing_route)).start({}).result()
        self.assertEqual(preflight.status, "failed")
        if preflight.status != "failed":
            self.fail("recovery preflight must fail")
        self.assertEqual(preflight.failure.kind, "unknown_action")
        self.assertIsNone(preflight.failure.attempt)
        self.assertEqual(preflight.failure.previous.kind, "handler")  # type: ignore[union-attr]
        self.assertEqual(preflight.stats.transitions, 0)


if __name__ == "__main__":
    unittest.main()
