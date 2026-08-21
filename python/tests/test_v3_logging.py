from __future__ import annotations

import asyncio
import logging
import unittest
from typing import Any

from caskada import Context, Flow, RetryPolicy, RunOptions, node
from caskada_logging import logging_observer


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _ExplodingHandler(logging.Handler):
    def emit(self, _record: logging.LogRecord) -> None:
        raise RuntimeError("sink failed")


class _Unformattable:
    def __str__(self) -> str:
        raise AssertionError("application data must not be formatted")


class LoggingAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_forwards_exact_events_without_buffering_or_formatting(
        self,
    ) -> None:
        capture = _CaptureHandler()
        logger = logging.getLogger(f"caskada-test-{id(capture)}")
        logger.handlers = [capture]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        attempts = 0

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal attempts
            attempts += 1
            context.report("payload", _Unformattable())
            if attempts == 1:
                raise ValueError("retry")

        result = (
            await Flow(node(handler, retry=RetryPolicy(max_attempts=2)))
            .start(
                {},
                options=RunOptions(observer=logging_observer(logger)),
            )
            .result()
        )
        events = [record.caskada_event for record in capture.records]

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            [record.caskada_sequence for record in capture.records],
            list(range(1, len(capture.records) + 1)),
        )
        self.assertTrue(
            all(
                record.caskada_event is event
                for record, event in zip(capture.records, events)
            )
        )
        self.assertEqual(
            next(
                record
                for record in capture.records
                if record.caskada_event_kind == "failure_recorded"
            ).levelno,
            logging.ERROR,
        )
        self.assertEqual(
            next(
                record
                for record in capture.records
                if record.caskada_event_kind == "retry_scheduled"
            ).levelno,
            logging.INFO,
        )
        self.assertEqual(
            next(
                record
                for record in capture.records
                if record.caskada_event_kind == "report"
            ).levelno,
            logging.INFO,
        )
        self.assertEqual(
            next(
                record
                for record in capture.records
                if record.caskada_event_kind == "callback_started"
            ).levelno,
            logging.DEBUG,
        )
        for record in capture.records:
            self.assertEqual(
                record.getMessage(), f"Caskada event: {record.caskada_event_kind}"
            )

    async def test_logger_failure_becomes_one_observer_diagnostic(self) -> None:
        logger = logging.getLogger(f"caskada-test-exploding-{id(self)}")
        logger.handlers = [_ExplodingHandler()]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

        result = (
            await Flow(node(lambda _context: None))
            .start({}, options=RunOptions(observer=logging_observer(logger)))
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.diagnostics), 1)
        self.assertEqual(result.diagnostics[0].message, "Observer raised")
        self.assertEqual(result.diagnostics[0].event_sequence, 1)
        self.assertIsInstance(result.diagnostics[0].cause, RuntimeError)

    async def test_cancellation_fence_is_logged_as_a_warning(self) -> None:
        capture = _CaptureHandler()
        logger = logging.getLogger(f"caskada-test-cancel-{id(capture)}")
        logger.handlers = [capture]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        entered = asyncio.Event()

        async def handler(context: Context[dict[str, Any]]) -> None:
            entered.set()
            await context.cancellation.wait()

        handle = Flow(node(handler)).start(
            {}, options=RunOptions(observer=logging_observer(logger))
        )
        await entered.wait()
        handle.cancel("test")
        await handle.result()

        fence = next(
            record
            for record in capture.records
            if record.caskada_event_kind == "cancellation_fenced"
        )
        self.assertEqual(fence.levelno, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
