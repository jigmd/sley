from __future__ import annotations

import json
import unittest
from collections.abc import Iterator, Mapping
from typing import Any

from caskada import Context, Flow, OptionValidationError, ScopeResult, node


class ExplodingStr(str):
    hash_calls = 0

    def __hash__(self) -> int:
        type(self).hash_calls += 1
        raise AssertionError("a rejected str subclass must not be hashed")


class RecordingMapping(Mapping[object, object]):
    def __init__(self, keys: list[object], values: dict[str, object]) -> None:
        self._keys = keys
        self._values = values
        self.reads: list[object] = []

    def __len__(self) -> int:
        return len(self._keys)

    def __iter__(self) -> Iterator[object]:
        return iter(self._keys)

    def __getitem__(self, key: object) -> object:
        self.reads.append(key)
        return self._values[str(key)]


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

    async def test_nonexact_keys_fail_before_hash_and_update_is_incremental(
        self,
    ) -> None:
        bad = ExplodingStr("bad")
        ExplodingStr.hash_calls = 0

        def misuse(context: Context[dict[str, Any]]) -> None:
            state = context.state
            operations = (
                lambda: state[bad],
                lambda: state.get(bad),
                lambda: bad in state,
                lambda: state.setdefault(bad, 1),
                lambda: state.pop(bad, None),
                lambda: state.__setitem__(bad, 1),
                lambda: state.__delitem__(bad),
            )
            for operation in operations:
                with self.assertRaises(TypeError):
                    operation()
            with self.assertRaises(TypeError):
                state.update([("kept", 1), (bad, 2), ("unreached", 3)])

        state = await Flow(node(misuse)).run({})

        self.assertEqual(ExplodingStr.hash_calls, 0)
        self.assertEqual(state, {"kept": 1})

    async def test_initial_mapping_capture_checks_keys_before_values(self) -> None:
        bad = ExplodingStr("bad")
        invalid = RecordingMapping(["first", bad, "later"], {"first": 1})
        flow = Flow(node(lambda _context: None))

        with self.assertRaises(OptionValidationError):
            await flow.run(invalid)  # type: ignore[arg-type]

        self.assertEqual(invalid.reads, ["first"])
        self.assertEqual(ExplodingStr.hash_calls, 0)

        duplicate = RecordingMapping(
            ["same", "same"],
            {"same": 1},
        )
        with self.assertRaises(OptionValidationError):
            await flow.run(duplicate)  # type: ignore[arg-type]
        self.assertEqual(duplicate.reads, ["same"])

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
