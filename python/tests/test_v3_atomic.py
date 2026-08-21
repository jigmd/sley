from __future__ import annotations

import unittest
from typing import Any

from caskada import Context, Flow, ScopeResult, node


class AtomicSettlementTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_invalid_arm_rejects_the_complete_handler_batch(self) -> None:
        def source(context: Context[dict[str, Any]]) -> None:
            context.state["written"] = True
            context.emit("valid", 1)
            context.emit("missing", 2)

        def must_not_run(context: Context[dict[str, Any], int]) -> None:
            context.state["ran"] = context.input

        source_node = node(source)
        source_node.link(node(must_not_run), "valid")

        result = await Flow(source_node).start({}).result()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, {"written": True})
        self.assertEqual(result.terminals, ())
        self.assertEqual(result.stats.activations, 2)
        self.assertEqual(result.stats.attempts, 1)
        self.assertEqual(result.stats.transitions, 0)
        self.assertEqual(result.stats.peak_ready, 1)

    async def test_handler_throw_discards_its_complete_buffer(self) -> None:
        cause = RuntimeError("after emit")

        def source(context: Context[dict[str, Any]]) -> None:
            context.emit("valid")
            raise cause

        source_node = node(source)
        source_node.link(
            node(lambda context: context.state.__setitem__("ran", True)),
            "valid",
        )

        result = await Flow(source_node).start({}).result()

        self.assertEqual(result.status, "failed")
        self.assertNotIn("ran", result.state)
        self.assertEqual(result.stats.transitions, 0)
        if result.status != "failed":
            self.fail("handler throw must fail")
        self.assertIs(result.failure.cause, cause)

    async def test_caught_semantic_misuse_leaves_prior_intents_intact(self) -> None:
        def source(context: Context[dict[str, Any]]) -> None:
            context.emit("valid", 3)
            try:
                context.emit("")
            except TypeError:
                pass

        def consume(context: Context[dict[str, Any], int]) -> None:
            context.state["value"] = context.input

        source_node = node(source)
        source_node.link(node(consume), "valid")

        state = await Flow(source_node).run({})

        self.assertEqual(state, {"value": 3})

    async def test_rejected_combine_batch_preserves_original_terminals(self) -> None:
        def combine(_context: Context[dict[str, Any]], _result: ScopeResult) -> None:
            _context.end("replacement")
            _context.emit("missing")

        result = (
            await Flow(
                node(lambda context: context.end("original")),
                combine=combine,
            )
            .start({})
            .result()
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.terminals), 1)
        self.assertEqual(result.terminals[0].output, "original")
        self.assertEqual(result.stats.transitions, 1)


if __name__ == "__main__":
    unittest.main()
