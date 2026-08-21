from __future__ import annotations

import asyncio
import time
import unittest
from typing import Any, cast

from caskada import (
    RUN_EVENT_SCHEMA_VERSION,
    CallbackFinishedEvent,
    CallbackOutcomeDisposition,
    Context,
    EndTransition,
    Flow,
    Observer,
    RetryPolicy,
    RoutedTransition,
    RunEvent,
    RunOptions,
    ScopeFinishedEvent,
    TerminalCommittedEvent,
    TransitionCommittedEvent,
    node,
)


class RunEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_trace_has_exact_opening_and_terminal_order(self) -> None:
        events: list[RunEvent] = []

        @node
        def first(context: Context[dict[str, Any]]) -> None:
            context.emit("next", 7)

        @node
        def second(context: Context[dict[str, Any]]) -> None:
            context.end(context.input)

        first.link(second, "next")
        result = (
            await Flow(first)
            .start({}, options=RunOptions(observer=events.append, run_id="events"))
            .result()
        )

        self.assertEqual(RUN_EVENT_SCHEMA_VERSION, 1)
        self.assertEqual(result.status, "completed")
        self.assertEqual([event.sequence for event in events], list(range(1, 12)))
        self.assertEqual({event.run_id for event in events}, {"events"})
        self.assertEqual(
            [event.kind for event in events],
            [
                "run_started",
                "scope_started",
                "callback_started",
                "callback_finished",
                "transition_committed",
                "callback_started",
                "callback_finished",
                "transition_committed",
                "terminal_committed",
                "scope_finished",
                "run_finished",
            ],
        )
        route = cast(TransitionCommittedEvent, events[4]).payload.transition
        self.assertIsInstance(route, RoutedTransition)
        self.assertEqual(route.destination.type, "activation")
        end = cast(TransitionCommittedEvent, events[7]).payload.transition
        self.assertIsInstance(end, EndTransition)
        terminal = cast(TerminalCommittedEvent, events[8]).payload
        self.assertEqual(terminal.terminal_sequence, end.destination.sequence)

    async def test_fanout_bundle_drains_before_observer_cancellation(self) -> None:
        events: list[RunEvent] = []
        handle: Any = None

        @node
        def fanout(context: Context[dict[str, Any]]) -> None:
            context.end(1)
            context.end(2)

        def observe(event: RunEvent) -> None:
            events.append(event)
            if event.kind == "transition_committed" and event.payload.branch_index == 0:
                handle.cancel("observer")

        handle = Flow(fanout).start({}, options=RunOptions(observer=observe))
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        kinds = [event.kind for event in events]
        first_transition = kinds.index("transition_committed")
        cancellation = kinds.index("cancellation_fenced")
        self.assertEqual(
            kinds[first_transition:cancellation],
            [
                "transition_committed",
                "terminal_committed",
                "transition_committed",
                "terminal_committed",
            ],
        )
        finished = cast(CallbackFinishedEvent, events[first_transition - 1])
        disposition = cast(CallbackOutcomeDisposition, finished.payload.disposition)
        self.assertEqual(disposition.outcome, "fanout")

    async def test_nested_combine_closes_with_precombine_terminal_ids(self) -> None:
        events: list[RunEvent] = []

        @node
        def worker(context: Context[dict[str, Any]]) -> None:
            context.end(1)

        def combine(context: Context[dict[str, Any]], result: Any) -> None:
            context.emit(input=list(result.outputs))

        child = Flow(worker, combine=combine)

        @node
        def finish(context: Context[dict[str, Any]]) -> None:
            context.end(context.input)

        child.link(finish)
        result = (
            await Flow(child)
            .start({}, options=RunOptions(observer=events.append))
            .result()
        )

        self.assertEqual(result.status, "completed")
        child_finished = next(
            cast(ScopeFinishedEvent, event)
            for event in events
            if event.kind == "scope_finished" and event.payload.scope_id == 2
        )
        self.assertEqual(child_finished.payload.terminal_sequences, (1,))
        child_finish_index = events.index(child_finished)
        boundary = cast(TransitionCommittedEvent, events[child_finish_index - 1])
        self.assertEqual(boundary.payload.scope_id, 1)
        self.assertEqual(boundary.payload.transition.kind, "forward_exit")

    async def test_failure_and_retry_events_reference_one_failure(self) -> None:
        events: list[RunEvent] = []
        attempts = 0

        def handler(_context: Context[dict[str, Any]]) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ValueError("retry")

        retried = node(handler, retry=RetryPolicy(max_attempts=2))
        result = (
            await Flow(retried)
            .start({}, options=RunOptions(observer=events.append))
            .result()
        )

        self.assertEqual(result.status, "completed")
        kinds = [event.kind for event in events]
        self.assertLess(
            kinds.index("failure_recorded"), kinds.index("callback_finished")
        )
        self.assertLess(
            kinds.index("callback_finished"), kinds.index("retry_scheduled")
        )
        failure_event = next(
            event for event in events if event.kind == "failure_recorded"
        )
        retry_event = next(event for event in events if event.kind == "retry_scheduled")
        self.assertEqual(
            retry_event.payload.failure_id,
            failure_event.payload.failure.failure_id,
        )

    async def test_callback_start_observer_can_skip_invocation(self) -> None:
        events: list[RunEvent] = []
        calls = 0
        handle: Any = None

        def handler(_context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1

        def observe(event: RunEvent) -> None:
            events.append(event)
            if event.kind == "callback_started":
                handle.cancel("stop")

        handle = Flow(node(handler)).start({}, options=RunOptions(observer=observe))
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(calls, 0)
        self.assertEqual(
            [event.kind for event in events],
            [
                "run_started",
                "scope_started",
                "callback_started",
                "cancellation_fenced",
                "callback_finished",
                "scope_finished",
                "run_finished",
            ],
        )

    async def test_cancel_publishes_before_return_and_is_noop_after_terminal(
        self,
    ) -> None:
        events: list[RunEvent] = []
        entered = asyncio.Event()
        handle: Any = None

        async def handler(context: Context[dict[str, Any]]) -> None:
            entered.set()
            await context.cancellation.wait()

        def observe(event: RunEvent) -> None:
            events.append(event)
            if event.kind == "run_finished":
                handle.cancel("too_late")

        handle = Flow(node(handler)).start({}, options=RunOptions(observer=observe))
        await entered.wait()
        handle.cancel("caller")
        self.assertEqual(events[-1].kind, "cancellation_fenced")
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(events[-1].kind, "run_finished")
        self.assertEqual(
            sum(event.kind == "cancellation_fenced" for event in events),
            1,
        )

    async def test_throwing_observer_is_disabled_and_diagnostic_is_retained(
        self,
    ) -> None:
        cause = KeyboardInterrupt()
        calls = 0

        def observe(_event: RunEvent) -> None:
            nonlocal calls
            calls += 1
            raise cause

        result = (
            await Flow(node(lambda _context: None))
            .start({}, options=RunOptions(observer=observe))
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, 1)
        self.assertEqual(len(result.diagnostics), 1)
        self.assertEqual(result.diagnostics[0].event_sequence, 1)
        self.assertEqual(result.diagnostics[0].message, "Observer raised")
        self.assertIs(result.diagnostics[0].cause, cause)

    async def test_async_observer_result_is_closed_and_disabled(self) -> None:
        calls = 0
        body_ran = False

        async def asynchronous_observer(_event: RunEvent) -> None:
            nonlocal body_ran
            body_ran = True

        def observe(event: RunEvent) -> object:
            nonlocal calls
            calls += 1
            return asynchronous_observer(event)

        result = (
            await Flow(node(lambda _context: None))
            .start({}, options=RunOptions(observer=cast(Observer, observe)))
            .result()
        )

        await asyncio.sleep(0)
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, 1)
        self.assertFalse(body_ran)
        self.assertEqual(
            result.diagnostics[0].message,
            "Observer must return synchronously",
        )

    async def test_terminal_observer_time_is_excluded_from_duration(self) -> None:
        def observe(event: RunEvent) -> None:
            if event.kind == "run_finished":
                time.sleep(0.05)

        started = time.monotonic()
        result = (
            await Flow(node(lambda _context: None))
            .start({}, options=RunOptions(observer=observe))
            .result()
        )
        elapsed_ms = (time.monotonic() - started) * 1_000

        self.assertEqual(result.status, "completed")
        self.assertGreaterEqual(elapsed_ms, 45)
        self.assertGreaterEqual(elapsed_ms - result.stats.duration_ms, 35)


if __name__ == "__main__":
    unittest.main()
