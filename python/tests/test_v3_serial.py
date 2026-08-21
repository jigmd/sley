from __future__ import annotations

import unittest
from typing import Any

from caskada import Context, Flow, RunOptions, ScopeResult, node


class SerialExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_implicit_route_shares_run_owned_state(self) -> None:
        initial_state = {"count": 0, "nested": []}
        seen_state: list[dict[str, Any]] = []

        def first(context: Context[dict[str, Any]]) -> None:
            seen_state.append(context.state)
            context.state["count"] = 1

        async def second(context: Context[dict[str, Any]]) -> None:
            seen_state.append(context.state)
            context.state["count"] += 1
            context.state["nested"].append("shared")

        first_node = node(first)
        second_node = node(second)
        first_node.link(second_node)

        state = await Flow(first_node).run(initial_state)

        self.assertEqual(state, {"count": 2, "nested": ["shared"]})
        self.assertIs(state, seen_state[0])
        self.assertIs(state, seen_state[1])
        self.assertIsNot(state, initial_state)
        self.assertEqual(initial_state, {"count": 0, "nested": ["shared"]})

    async def test_explicit_and_forwarded_branch_input(self) -> None:
        seen: list[object] = []

        def produce(context: Context[dict[str, Any]]) -> None:
            context.emit("work", {"value": 7})

        def forward(context: Context[dict[str, Any], object]) -> None:
            seen.append(context.input)
            context.emit()

        def consume(context: Context[dict[str, Any], object]) -> None:
            seen.append(context.input)
            context.state["seen"] = context.input

        producer = node(produce)
        forwarding = node(forward)
        consumer = node(consume)
        producer.link(forwarding, "work")
        forwarding.link(consumer)

        state = await Flow(producer).run({})

        self.assertEqual(state["seen"], {"value": 7})
        self.assertIs(seen[0], seen[1])

    async def test_hard_end_bypasses_link_and_preserves_output_presence(self) -> None:
        observed: list[ScopeResult] = []

        def finish(context: Context[dict[str, Any]]) -> None:
            context.end()
            context.end(None)

        def must_not_run(context: Context[dict[str, Any]]) -> None:
            context.state["ran"] = True

        def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
            observed.append(result)
            context.state["outputs"] = list(result.outputs)

        finishing = node(finish)
        finishing.link(node(must_not_run))

        state = await Flow(finishing, combine=combine).run({})

        self.assertNotIn("ran", state)
        self.assertEqual(state["outputs"], [None])
        first, second = observed[0].terminals
        self.assertEqual(
            (first.type, first.has_output, first.output), ("end", False, None)
        )
        self.assertEqual(
            (second.type, second.has_output, second.output), ("end", True, None)
        )
        self.assertEqual((first.sequence, second.sequence), (1, 2))
        self.assertEqual(
            (first.source_activation_id, second.source_activation_id), (2, 2)
        )

    async def test_fanout_and_zero_emission_combine_preserve_terminals(self) -> None:
        combined: list[ScopeResult] = []

        def dispatch(context: Context[dict[str, Any]]) -> None:
            for value in (1, 2, 3):
                context.emit("work", value)

        def worker(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input * 10)

        def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
            combined.append(result)
            context.state["total"] = sum(result.outputs)  # type: ignore[arg-type]

        dispatcher = node(dispatch)
        dispatcher.link(node(worker), "work")

        state = await Flow(dispatcher, combine=combine).run({})

        self.assertEqual(state["total"], 60)
        self.assertEqual(combined[0].outputs, (10, 20, 30))
        self.assertEqual(
            [terminal.sequence for terminal in combined[0].terminals], [1, 2, 3]
        )

    async def test_combine_replacement_continues_after_nested_flow(self) -> None:
        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("work", 1)
            context.emit("work", 2)

        def worker(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input * 10)

        def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
            context.emit(input=list(result.outputs))

        def consume(context: Context[dict[str, Any], object]) -> None:
            context.state["values"] = context.input

        dispatcher = node(dispatch)
        dispatcher.link(node(worker), "work")
        mapper = Flow(dispatcher, combine=combine)
        mapper.link(node(consume))

        state = await Flow(mapper).run({})

        self.assertEqual(state["values"], [10, 20])

    async def test_declared_named_exit_completes(self) -> None:
        def ask(context: Context[dict[str, Any]]) -> None:
            context.emit("needs_input", {"question": "name?"})

        state = await Flow(node(ask), exits=("needs_input",)).run({"kept": True})
        self.assertEqual(state, {"kept": True})

    async def test_context_closes_but_obtained_state_alias_remains_live(self) -> None:
        contexts: list[Context[dict[str, Any]]] = []
        aliases: list[dict[str, Any]] = []

        def retain(context: Context[dict[str, Any]]) -> None:
            contexts.append(context)
            aliases.append(context.state)

        state = await Flow(node(retain)).run({})
        with self.assertRaises(RuntimeError):
            _ = contexts[0].state
        aliases[0]["late"] = True
        self.assertIs(aliases[0], state)
        self.assertTrue(state["late"])

    async def test_deep_nested_execution_is_iterative(self) -> None:
        def leaf(context: Context[dict[str, Any]]) -> None:
            context.state["visited"] = True

        nested: Flow[dict[str, Any]] = Flow(node(leaf))
        for _ in range(1_500):
            nested = Flow(nested)

        state = await nested.compile().run({}, options=RunOptions(max_depth=1_501))

        self.assertEqual(state, {"visited": True})


if __name__ == "__main__":
    unittest.main()
