from __future__ import annotations

import asyncio
import unittest
from collections.abc import Iterator, Mapping
from typing import Any

from caskada import Completed, Context, Flow, OptionValidationError, node


class ExplodingMapping(Mapping[str, object]):
    def __len__(self) -> int:
        raise AssertionError("initial state must not be read without a running loop")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("initial state must not be read without a running loop")

    def __getitem__(self, key: str) -> object:
        raise AssertionError("initial state must not be read without a running loop")


class StartPreflightTests(unittest.TestCase):
    def test_start_requires_running_loop_before_other_preflight(self) -> None:
        flow = Flow(node(lambda _context: None))

        with self.assertRaisesRegex(
            RuntimeError,
            r"^Caskada start\(\) requires a running asyncio event loop$",
        ):
            flow.start(ExplodingMapping(), options=object())  # type: ignore[arg-type]


class SuccessfulResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_defers_callbacks_and_settles_one_result(self) -> None:
        calls = 0

        def handle(context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1
            context.state["handled"] = True

        flow = Flow(node(handle))
        handle_ref = flow.start({})

        self.assertFalse(handle_ref.done())
        self.assertEqual(calls, 0)
        first = await handle_ref.result()
        second = await handle_ref.result()

        self.assertTrue(handle_ref.done())
        self.assertIs(first, second)
        self.assertIsInstance(first, Completed)
        self.assertEqual(first.status, "completed")
        self.assertEqual(first.state, {"handled": True})
        self.assertEqual(calls, 1)
        handle_ref.cancel()

    async def test_completed_preserves_terminal_identity_and_plurality(self) -> None:
        first_output = {"value": 1}
        second_output = {"value": 2}

        def finish(context: Context[dict[str, Any]]) -> None:
            context.end(first_output)
            context.end()
            context.end(second_output)

        result = await Flow(node(finish)).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.terminals), 3)
        self.assertTrue(result.terminals[0].has_output)
        self.assertIs(result.terminals[0].output, first_output)
        self.assertFalse(result.terminals[1].has_output)
        self.assertIsNone(result.terminals[1].output)
        self.assertIs(result.terminals[2].output, second_output)
        self.assertEqual(
            [terminal.sequence for terminal in result.terminals],
            [1, 2, 3],
        )
        self.assertNotIn("value", repr(result))
        self.assertIs(result, result)

    async def test_run_projects_same_execution_to_exact_state(self) -> None:
        calls = 0
        callback_state: dict[str, Any] | None = None

        def mutate(context: Context[dict[str, Any]]) -> None:
            nonlocal calls, callback_state
            calls += 1
            callback_state = context.state
            context.state["value"] = 3

        state = await Flow(node(mutate)).run({})

        self.assertEqual(calls, 1)
        self.assertIs(state, callback_state)
        self.assertEqual(state, {"value": 3})

    async def test_stats_count_committed_serial_work(self) -> None:
        first = node(lambda _context: None)
        second = node(lambda _context: None)
        first.link(second)

        result = await Flow(first).start({}).result()

        self.assertEqual(result.stats.activations, 3)
        self.assertEqual(result.stats.attempts, 2)
        self.assertEqual(result.stats.transitions, 2)
        self.assertEqual(result.stats.retries, 0)
        self.assertEqual(result.stats.reports, 0)
        self.assertEqual(result.stats.scopes, 1)
        self.assertEqual(result.stats.peak_ready, 1)
        self.assertEqual(result.stats.peak_callbacks, 1)
        self.assertGreaterEqual(result.stats.duration_ms, 0)

    async def test_waiter_cancellation_does_not_cancel_the_run(self) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def wait(context: Context[dict[str, Any]]) -> None:
            entered.set()
            await release.wait()
            context.state["finished"] = True

        handle = Flow(node(wait)).start({})
        await entered.wait()
        waiter = asyncio.create_task(handle.result())
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter

        self.assertFalse(handle.done())
        release.set()
        result = await handle.result()
        self.assertEqual(result.state, {"finished": True})

    async def test_compiled_start_reuses_snapshot_and_captures_each_state(self) -> None:
        compiled = Flow(node(lambda _context: None)).compile()

        first = await compiled.start({"run": 1}).result()
        second = await compiled.start({"run": 2}).result()

        self.assertEqual(first.state, {"run": 1})
        self.assertEqual(second.state, {"run": 2})
        self.assertIsNot(first.state, second.state)

    async def test_start_preflight_errors_create_no_callback(self) -> None:
        calls = 0

        def handle(_context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1

        with self.assertRaises(OptionValidationError):
            Flow(node(handle)).start({}, options=object())
        await asyncio.sleep(0)
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
