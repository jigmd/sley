from __future__ import annotations

import json
import unittest
from typing import Any

from caskada import Context, Flow, OptionValidationError, ScopeResult, node


class StateCarrierTests(unittest.IsolatedAsyncioTestCase):
    async def test_carrier_supports_normal_dict_instance_operations(self) -> None:
        retained: dict[str, object] = {}

        def mutate(context: Context[dict[str, Any]]) -> None:
            state = context.state
            state.update({"updated": 2})
            state.update([("sequence", 3)])
            state.setdefault("defaulted", 4)
            state |= {"unioned": 5}
            state["temporary"] = 6
            self.assertEqual(state.pop("temporary"), 6)
            state["delete"] = 7
            del state["delete"]
            retained["alias"] = state
            retained["keys"] = state.keys()
            retained["iterator"] = iter(state)
            retained["copy"] = state.copy()
            retained["union"] = state | {"right": 8}
            retained["reverse"] = list(reversed(state))
            retained["json"] = json.loads(json.dumps(state))

        state = await Flow(node(mutate)).run({"initial": 1})

        self.assertIs(type(state), dict)
        self.assertEqual(
            state,
            {
                "initial": 1,
                "updated": 2,
                "sequence": 3,
                "defaulted": 4,
                "unioned": 5,
            },
        )
        self.assertEqual(retained["copy"], state)
        self.assertEqual(retained["union"], {**state, "right": 8})
        self.assertEqual(retained["json"], state)
        self.assertEqual(retained["reverse"], list(reversed(state)))
        state["after"] = 9
        self.assertIn("after", retained["keys"])  # type: ignore[operator]
        with self.assertRaises(RuntimeError):
            list(retained["iterator"])  # type: ignore[arg-type]

    async def test_initial_state_requires_a_mapping_with_string_keys(self) -> None:
        flow = Flow(node(lambda _context: None))

        with self.assertRaises(OptionValidationError):
            await flow.run([])  # type: ignore[arg-type]
        with self.assertRaises(OptionValidationError):
            await flow.run({1: "invalid"})  # type: ignore[dict-item]

    async def test_copy_is_shallow_and_preserves_source_self_reference(self) -> None:
        nested: list[str] = []
        initial: dict[str, Any] = {"nested": nested}
        initial["self"] = initial

        def mutate(context: Context[dict[str, Any]]) -> None:
            context.state["nested"].append("shared")
            context.state["added"] = True

        state = await Flow(node(mutate)).run(initial)

        self.assertIsNot(state, initial)
        self.assertIs(state["nested"], nested)
        self.assertIs(state["self"], initial)
        self.assertEqual(nested, ["shared"])
        self.assertNotIn("added", initial)

    async def test_state_may_be_exact_branch_input_and_terminal_output(self) -> None:
        identities: list[bool] = []

        def produce(context: Context[dict[str, Any]]) -> None:
            context.emit(input=context.state)

        def consume(context: Context[dict[str, Any], object]) -> None:
            identities.append(context.input is context.state)
            context.end(context.state)

        def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
            identities.append(result.outputs[0] is context.state)

        producer = node(produce)
        producer.link(node(consume))
        state = await Flow(producer, combine=combine).run({})

        self.assertEqual(identities, [True, True])
        self.assertIsInstance(state, dict)

    async def test_separate_runs_own_distinct_top_level_carriers(self) -> None:
        flow = Flow(node(lambda _context: None)).compile()
        initial: dict[str, Any] = {"nested": []}

        first = await flow.run(initial)
        second = await flow.run(initial)

        self.assertIsNot(first, second)
        self.assertIsNot(first, initial)
        self.assertIs(first["nested"], second["nested"])


if __name__ == "__main__":
    unittest.main()
