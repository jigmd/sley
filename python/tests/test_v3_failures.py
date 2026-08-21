from __future__ import annotations

import unittest
from typing import Any

from caskada import (
    Context,
    Failed,
    Flow,
    InvalidCombinationDetail,
    InvalidOutcomeDetail,
    RunError,
    UnknownActionDetail,
    node,
)


class UnformattableError(Exception):
    def __str__(self) -> str:
        raise AssertionError("Failure construction must not format its cause")

    def __repr__(self) -> str:
        raise AssertionError("Failure repr must not render its cause")


class FailureNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_handler_exception_is_data_with_exact_cause(self) -> None:
        cause = UnformattableError()

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise cause

        handle = Flow(node(fail)).start({})
        result = await handle.result()

        self.assertTrue(handle.done())
        self.assertIsInstance(result, Failed)
        if result.status != "failed":
            self.fail("handler exception must fail the run")
        self.assertEqual(result.terminals, ())
        self.assertEqual(result.suppressed, ())
        self.assertEqual(result.diagnostics, ())
        self.assertEqual(result.failure.failure_id, 1)
        self.assertEqual(result.failure.kind, "handler")
        self.assertEqual(result.failure.message, "Node handler raised")
        self.assertIs(result.failure.cause, cause)
        self.assertEqual(result.failure.scope_id, 1)
        self.assertEqual(result.failure.activation_id, 2)
        self.assertEqual(result.failure.element_id, 2)
        self.assertEqual(result.failure.attempt, 1)
        self.assertIsNone(result.failure.detail)
        self.assertIsNone(result.failure.previous)
        self.assertNotIn("Unformattable", repr(result.failure))

    async def test_unsignalled_base_exception_is_a_handler_failure(self) -> None:
        cause = KeyboardInterrupt()

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise cause

        result = await Flow(node(fail)).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("BaseException must settle the callback")
        self.assertEqual(result.failure.kind, "handler")
        self.assertIs(result.failure.cause, cause)

    async def test_run_raises_one_error_with_its_exact_failed_result(self) -> None:
        cause = ValueError("application")
        calls = 0

        def fail(_context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1
            raise cause

        with self.assertRaisesRegex(RunError, r"^Caskada run failed$") as raised:
            await Flow(node(fail)).run({})

        self.assertEqual(calls, 1)
        self.assertEqual(raised.exception.result.status, "failed")
        self.assertIs(raised.exception.result.failure.cause, cause)
        self.assertIs(raised.exception.__cause__, cause)

    async def test_wrong_returns_have_phase_specific_details(self) -> None:
        def wrong_handler(_context: Context[dict[str, Any]]) -> object:
            return object()

        handler_result = await Flow(node(wrong_handler)).start({}).result()  # type: ignore[arg-type]
        self.assertEqual(handler_result.status, "failed")
        if handler_result.status != "failed":
            self.fail("wrong handler return must fail")
        self.assertEqual(handler_result.failure.kind, "invalid_outcome")
        self.assertEqual(
            handler_result.failure.detail,
            InvalidOutcomeDetail("wrong_return_type"),
        )
        self.assertIsNone(handler_result.failure.cause)

        def wrong_combine(_context: Context[dict[str, Any]], _result: object) -> int:
            return 1

        combine_result = (
            await Flow(
                node(lambda _context: None),
                combine=wrong_combine,  # type: ignore[arg-type]
            )
            .start({})
            .result()
        )
        self.assertEqual(combine_result.status, "failed")
        if combine_result.status != "failed":
            self.fail("wrong combine return must fail")
        self.assertEqual(combine_result.failure.kind, "invalid_combination")
        self.assertEqual(
            combine_result.failure.detail,
            InvalidCombinationDetail("wrong_return_type"),
        )
        self.assertEqual(combine_result.failure.activation_id, 1)
        self.assertEqual(combine_result.failure.element_id, 1)
        self.assertIsNone(combine_result.failure.attempt)

    async def test_uncaught_control_misuse_is_portable(self) -> None:
        def invalid_action(context: Context[dict[str, Any]]) -> None:
            context.emit("")

        action_result = await Flow(node(invalid_action)).start({}).result()
        self.assertEqual(action_result.status, "failed")
        if action_result.status != "failed":
            self.fail("invalid action must fail")
        self.assertEqual(action_result.failure.kind, "invalid_outcome")
        self.assertEqual(
            action_result.failure.detail,
            InvalidOutcomeDetail("invalid_action"),
        )
        self.assertIsNone(action_result.failure.cause)

    async def test_flow_combine_exception_has_flow_provenance(self) -> None:
        cause = RuntimeError("combine")

        def combine(_context: Context[dict[str, Any]], _result: object) -> None:
            raise cause

        result = (
            await Flow(
                node(lambda _context: None),
                combine=combine,  # type: ignore[arg-type]
            )
            .start({})
            .result()
        )

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("combine exception must fail")
        self.assertEqual(result.failure.kind, "flow_combine")
        self.assertEqual(result.failure.message, "Flow combine raised")
        self.assertIs(result.failure.cause, cause)
        self.assertEqual(result.failure.scope_id, 1)
        self.assertEqual(result.failure.activation_id, 1)
        self.assertEqual(result.failure.element_id, 1)
        self.assertIsNone(result.failure.attempt)

    async def test_unknown_action_is_structured_and_commits_no_transition(self) -> None:
        def route(context: Context[dict[str, Any]]) -> None:
            context.emit("missing")

        result = await Flow(node(route)).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("unknown action must fail")
        self.assertEqual(result.failure.kind, "unknown_action")
        self.assertEqual(result.failure.message, "Unknown action")
        self.assertEqual(result.failure.detail, UnknownActionDetail("missing"))
        self.assertIsNone(result.failure.cause)
        self.assertEqual(result.failure.attempt, 1)
        self.assertEqual(result.stats.transitions, 0)

    async def test_committed_root_terminals_survive_a_later_failure(self) -> None:
        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("finish", 1)
            context.emit("fail", 2)

        def finish(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input)

        def fail(_context: Context[dict[str, Any], int]) -> None:
            raise LookupError("later")

        dispatcher = node(dispatch)
        dispatcher.link(node(finish), "finish")
        dispatcher.link(node(fail), "fail")

        result = await Flow(dispatcher).start({}).result()

        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.terminals), 1)
        self.assertEqual(result.terminals[0].output, 1)


if __name__ == "__main__":
    unittest.main()
