from __future__ import annotations

import asyncio
import unittest
from typing import Any

from caskada import Context, Flow, RunOptions, RunStats, node


class RunStatsTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_nested_run_has_exact_committed_counts(self) -> None:
        child = Flow(node(lambda _context: None))
        result = await Flow(child).start({}).result()

        self.assertEqual(result.status, "completed")
        self._assert_stats(
            result.stats,
            activations=3,
            attempts=1,
            transitions=2,
            retries=0,
            reports=0,
            scopes=2,
            peak_ready=1,
            peak_callbacks=1,
        )

    async def test_failed_run_keeps_committed_attempt_only(self) -> None:
        def fail(_context: Context[dict[str, Any]]) -> None:
            raise ValueError("failed")

        result = await Flow(node(fail)).start({}).result()

        self.assertEqual(result.status, "failed")
        self._assert_stats(
            result.stats,
            activations=2,
            attempts=1,
            transitions=0,
            retries=0,
            reports=0,
            scopes=1,
            peak_ready=1,
            peak_callbacks=1,
        )

    async def test_pre_admission_cancellation_counts_opening_facts_only(self) -> None:
        calls = 0

        def handler(_context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1

        handle = Flow(node(handler)).start({})
        handle.cancel("stop")
        result = await handle.result()

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(calls, 0)
        self._assert_stats(
            result.stats,
            activations=2,
            attempts=0,
            transitions=0,
            retries=0,
            reports=0,
            scopes=1,
            peak_ready=1,
            peak_callbacks=0,
        )

    async def test_abandonment_freezes_stats_before_late_work_finishes(self) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def stubborn(_context: Context[dict[str, Any]]) -> None:
            entered.set()
            await release.wait()

        handle = Flow(node(stubborn)).start(
            {},
            options=RunOptions(cancel_grace_ms=0),
        )
        await entered.wait()
        handle.cancel("stop")
        result = await handle.result()

        self.assertEqual(result.status, "abandoned")
        self._assert_stats(
            result.stats,
            activations=2,
            attempts=1,
            transitions=0,
            retries=0,
            reports=0,
            scopes=1,
            peak_ready=1,
            peak_callbacks=1,
        )
        terminal_duration = result.stats.duration_ms
        release.set()
        await asyncio.sleep(0.01)
        self.assertEqual(result.stats.duration_ms, terminal_duration)

    def _assert_stats(
        self,
        stats: RunStats,
        *,
        activations: int,
        attempts: int,
        transitions: int,
        retries: int,
        reports: int,
        scopes: int,
        peak_ready: int,
        peak_callbacks: int,
    ) -> None:
        self.assertEqual(
            (
                stats.activations,
                stats.attempts,
                stats.transitions,
                stats.retries,
                stats.reports,
                stats.scopes,
                stats.peak_ready,
                stats.peak_callbacks,
            ),
            (
                activations,
                attempts,
                transitions,
                retries,
                reports,
                scopes,
                peak_ready,
                peak_callbacks,
            ),
        )
        self.assertGreaterEqual(stats.duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
