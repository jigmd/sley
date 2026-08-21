from __future__ import annotations

import unittest
from typing import Any, Literal

from caskada import (
    CompiledFlow,
    Flow,
    GraphDefinitionError,
    GraphElement,
    node,
)


def handler(_context: object) -> None:
    pass


class ForeignElement(GraphElement[dict[str, Any]]):
    def __init__(self) -> None:
        super().__init__("foreign")

    @property
    def _caskada_kind(self) -> Literal["node"]:
        return "node"


class CompileTests(unittest.TestCase):
    def test_nested_compile_uses_normative_breadth_first_ids(self) -> None:
        parent_entry = node(handler, name="parent_entry")
        child_first = node(handler, name="child_first")
        child_second = node(handler, name="child_second")
        after = node(handler, name="after")
        child = Flow(child_first, name="child", concurrency=2)
        parent_entry.link(child)
        child.link(after)
        child_first.link(child_second)

        actual = Flow(parent_entry, name="root").compile().describe()
        self.assertEqual(actual, _nested_description())

    def test_one_definition_gets_one_placement_per_scope(self) -> None:
        start = node(handler, name="start")
        shared = node(handler, name="shared")
        child = Flow(shared, name="child", concurrency=2)
        sibling = Flow(shared, name="sibling", concurrency=3)
        start.link(child, "first")
        start.link(child, "second")
        start.link(sibling, "third")

        description = Flow(start, name="root").compile().describe()
        elements = description["elements"]
        self.assertEqual(
            [element["element_id"] for element in elements], [1, 2, 3, 4, 5, 6]
        )
        self.assertEqual(
            [
                element["parent_scope_definition_id"]
                for element in elements
                if element["name"] == "shared"
            ],
            [2, 3],
        )
        start_links = elements[1]["links"]
        self.assertEqual([link["target_element_id"] for link in start_links], [3, 3, 4])
        self.assertEqual(description["auto_max_concurrency"], 3)

    def test_ordinary_cycles_compile_but_containment_recursion_fails(self) -> None:
        first = node(handler, name="first")
        second = node(handler, name="second")
        first.link(second)
        second.link(first)
        description = Flow(first).compile().describe()
        self.assertEqual(len(description["elements"]), 3)
        self.assertEqual(description["elements"][2]["links"][0]["target_element_id"], 2)

        recursive_entry = node(handler, name="recursive-entry")
        recursive = Flow(recursive_entry, name="recursive")
        recursive_entry.link(recursive)
        with self.assertRaises(GraphDefinitionError):
            recursive.compile()

    def test_unknown_elements_and_flow_subclasses_are_rejected(self) -> None:
        entry = node(handler)
        entry.link(ForeignElement())
        with self.assertRaises(GraphDefinitionError):
            Flow(entry).compile()

        class DerivedFlow(Flow[dict[str, Any]]):
            pass

        with self.assertRaises(GraphDefinitionError):
            DerivedFlow(node(handler)).compile()

    def test_compiled_flow_is_factory_only_and_final(self) -> None:
        with self.assertRaises(TypeError):
            CompiledFlow()  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            CompiledFlow(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):

            class DerivedCompiledFlow(CompiledFlow[dict[str, Any]]):
                pass

    def test_compilation_is_a_topology_snapshot(self) -> None:
        entry = node(handler, name="entry")
        first_target = node(handler, name="first-target")
        later_target = node(handler, name="later-target")
        entry.link(first_target)
        root = Flow(entry, name="root")
        ignored_root_target = node(handler, name="ignored-root-target")
        root.link(ignored_root_target)

        compiled = root.compile()
        before = compiled.describe()
        entry.link(later_target, "later")
        after = root.compile().describe()

        self.assertEqual(compiled.describe(), before)
        self.assertEqual(before["elements"][0]["links"], [])
        self.assertNotIn(
            "ignored-root-target", [item["name"] for item in before["elements"]]
        )
        self.assertEqual(len(before["elements"]), 3)
        self.assertEqual(len(after["elements"]), 4)

        before["elements"].clear()
        before["scope_definitions"][0]["exits"].append("mutated")
        fresh = compiled.describe()
        self.assertEqual(len(fresh["elements"]), 3)
        self.assertEqual(fresh["scope_definitions"][0]["exits"], [])


def _nested_description() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "auto_max_concurrency": 2,
        "root": {"element_id": 1, "scope_definition_id": 1},
        "elements": [
            {
                "element_id": 1,
                "kind": "flow",
                "name": "root",
                "parent_scope_definition_id": None,
                "owned_scope_definition_id": 1,
                "links": [],
            },
            {
                "element_id": 2,
                "kind": "node",
                "name": "parent_entry",
                "parent_scope_definition_id": 1,
                "links": [{"action": None, "target_element_id": 3}],
                "retry": {"max_attempts": 1},
                "timeout_ms": None,
            },
            {
                "element_id": 3,
                "kind": "flow",
                "name": "child",
                "parent_scope_definition_id": 1,
                "owned_scope_definition_id": 2,
                "links": [{"action": None, "target_element_id": 4}],
            },
            {
                "element_id": 4,
                "kind": "node",
                "name": "after",
                "parent_scope_definition_id": 1,
                "links": [],
                "retry": {"max_attempts": 1},
                "timeout_ms": None,
            },
            {
                "element_id": 5,
                "kind": "node",
                "name": "child_first",
                "parent_scope_definition_id": 2,
                "links": [{"action": None, "target_element_id": 6}],
                "retry": {"max_attempts": 1},
                "timeout_ms": None,
            },
            {
                "element_id": 6,
                "kind": "node",
                "name": "child_second",
                "parent_scope_definition_id": 2,
                "links": [],
                "retry": {"max_attempts": 1},
                "timeout_ms": None,
            },
        ],
        "scope_definitions": [
            {
                "scope_definition_id": 1,
                "owner_element_id": 1,
                "parent_scope_definition_id": None,
                "entry_element_id": 2,
                "exits": [],
                "concurrency": 1,
                "max_activations": None,
            },
            {
                "scope_definition_id": 2,
                "owner_element_id": 3,
                "parent_scope_definition_id": 1,
                "entry_element_id": 5,
                "exits": [],
                "concurrency": 2,
                "max_activations": None,
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
