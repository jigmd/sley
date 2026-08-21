from __future__ import annotations

import unittest
from collections.abc import Sequence
from typing import Any

from caskada import (
    MAX_SAFE_INTEGER,
    DuplicateLinkError,
    Flow,
    GraphDefinitionError,
    GraphElement,
    Node,
    RetryPolicy,
    node,
)


def first(_context: object) -> None:
    pass


def second(_context: object) -> None:
    pass


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


class HugeSequence(Sequence[str]):
    def __len__(self) -> int:
        return 4_294_967_296

    def __getitem__(self, index: int) -> str:
        raise AssertionError("oversized exits must fail before item access")


class ThrowingSequence(Sequence[str]):
    cause = GraphDefinitionError("application error")

    def __len__(self) -> int:
        return 1

    def __getitem__(self, index: int) -> str:
        raise self.cause


class DefinitionTests(unittest.TestCase):
    def test_node_factory_creates_distinct_occurrences_and_decorator_forms(
        self,
    ) -> None:
        direct_a = node(first)
        direct_b = node(first)

        @node
        def decorated(_context: object) -> None:
            pass

        @node(name="configured")
        def configured(_context: object) -> None:
            pass

        self.assertIsInstance(direct_a, Node)
        self.assertIsNot(direct_a, direct_b)
        self.assertEqual(direct_a.name, "first")
        self.assertEqual(decorated.name, "decorated")
        self.assertEqual(configured.name, "configured")
        self.assertFalse(hasattr(direct_a, "handler"))
        self.assertFalse(hasattr(direct_a, "recovery"))

    def test_node_constructor_and_subclass_are_closed(self) -> None:
        with self.assertRaises(TypeError):
            Node()  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            Node(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):

            class Derived(Node[dict[str, Any]]):
                pass

        with self.assertRaises(TypeError):
            GraphElement("invalid")  # type: ignore[abstract]

    def test_node_configuration_is_validated_and_read_only(self) -> None:
        policy = RetryPolicy(max_attempts=3, delay_ms=25)
        configured = node(first, retry=policy, timeout_ms=50)

        self.assertIs(configured.retry, policy)
        self.assertEqual(configured.timeout_ms, 50)
        with self.assertRaises(AttributeError):
            configured.timeout_ms = 10  # type: ignore[misc]

        invalid_policies = (
            {"max_attempts": 0},
            {"max_attempts": True},
            {"max_attempts": IntegerSubclass(1)},
            {"max_attempts": MAX_SAFE_INTEGER + 1},
            {"should_retry": object()},
            {"delay_ms": -1},
            {"delay_ms": True},
        )
        for arguments in invalid_policies:
            with (
                self.subTest(arguments=arguments),
                self.assertRaises(GraphDefinitionError),
            ):
                RetryPolicy(**arguments)  # type: ignore[arg-type]

        with self.assertRaises(GraphDefinitionError):
            node(first, retry=object())  # type: ignore[arg-type]
        with self.assertRaises(GraphDefinitionError):
            node(first, timeout_ms=0)
        with self.assertRaises(GraphDefinitionError):
            node(first, recover=object())  # type: ignore[arg-type]

    def test_link_is_target_first_unique_and_declaration_ordered(self) -> None:
        source = node(first)
        default_target = node(second, name="default-target")
        named_target = node(second, name="named-target")

        self.assertIsNone(source.link(default_target))
        self.assertIsNone(source.link(named_target, action="default"))
        self.assertEqual(
            [(link.action, link.target.name) for link in source.links()],
            [(None, "default-target"), ("default", "named-target")],
        )
        self.assertIsInstance(source.links(), tuple)

        snapshot = source.links()
        with self.assertRaises(DuplicateLinkError):
            source.link(node(first))
        with self.assertRaises(DuplicateLinkError):
            source.link(node(first), "default")
        self.assertEqual(source.links(), snapshot)

    def test_link_rejects_ambiguous_and_nonprimitive_actions(self) -> None:
        source = node(first)
        target = node(second)

        invalid_calls = (
            lambda: source.link(target, None),
            lambda: source.link(target, ""),
            lambda: source.link(target, StringSubclass("named")),
            lambda: source.link("named", target),
            lambda: source.link(object()),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(GraphDefinitionError):
                call()  # type: ignore[misc]

    def test_flow_captures_definition_configuration(self) -> None:
        entry = node(first)
        exits = ["approved", "rejected"]
        flow = Flow(
            entry,
            name="review",
            exits=exits,
            concurrency=4,
            max_activations=20,
            combine=lambda _context, _result: None,
            recover=lambda _context, _failure: None,
        )
        exits.append("later")

        self.assertEqual(flow.name, "review")
        self.assertIs(flow.entry, entry)
        self.assertEqual(flow.exits, ("approved", "rejected"))
        self.assertEqual(flow.concurrency, 4)
        self.assertEqual(flow.max_activations, 20)
        self.assertEqual(flow.links(), ())
        with self.assertRaises(AttributeError):
            flow.concurrency = 2  # type: ignore[misc]

    def test_flow_defaults_and_invalid_configuration(self) -> None:
        entry = node(first)
        flow = Flow(entry)
        self.assertEqual(flow.name, "Flow")
        self.assertEqual(flow.exits, ())
        self.assertEqual(flow.concurrency, 1)
        self.assertIsNone(flow.max_activations)

        invalid_factories = (
            lambda: Flow(object()),
            lambda: Flow(entry, name=""),
            lambda: Flow(entry, name=StringSubclass("name")),
            lambda: Flow(entry, exits="done"),
            lambda: Flow(entry, exits=b"done"),
            lambda: Flow(entry, exits=["done", "done"]),
            lambda: Flow(entry, exits=[""]),
            lambda: Flow(entry, exits=[StringSubclass("done")]),
            lambda: Flow(entry, exits=HugeSequence()),
            lambda: Flow(entry, concurrency=0),
            lambda: Flow(entry, concurrency=True),
            lambda: Flow(entry, max_activations=0),
            lambda: Flow(entry, combine=object()),
            lambda: Flow(entry, recover=object()),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(GraphDefinitionError):
                factory()  # type: ignore[misc]

        with self.assertRaises(GraphDefinitionError) as raised:
            Flow(entry, exits=ThrowingSequence())
        self.assertIs(raised.exception.__cause__, ThrowingSequence.cause)

    def test_names_are_exact_and_anonymous_fallback_is_stable(self) -> None:
        class CallableWithoutName:
            def __call__(self, _context: object) -> None:
                pass

        self.assertEqual(node(CallableWithoutName()).name, "anonymous")
        with self.assertRaises(GraphDefinitionError):
            node(first, name="")
        with self.assertRaises(GraphDefinitionError):
            node(first, name=StringSubclass("name"))
        with self.assertRaises(GraphDefinitionError):
            node(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
