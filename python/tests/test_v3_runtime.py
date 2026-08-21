from __future__ import annotations

import asyncio
import unittest
from typing import Any

import caskada
from caskada import (
    Completed,
    Context,
    DuplicateLinkError,
    Flow,
    GraphDefinitionError,
    RetryPolicy,
    RunError,
    ScopeFailure,
    ScopeResult,
    node,
)


class DefinitionTests(unittest.TestCase):
    def test_public_surface_is_explicit_and_small(self) -> None:
        public = {name for name in vars(caskada) if not name.startswith("_")}
        self.assertEqual(public, set(caskada.__all__))
        self.assertLessEqual(len(public), 24)

    def test_node_supports_direct_and_decorator_forms(self) -> None:
        def direct(_context: object) -> None:
            pass

        @node
        def decorated(_context: object) -> None:
            pass

        @node(name="configured")
        def configured(_context: object) -> None:
            pass

        self.assertEqual(node(direct).name, "direct")
        self.assertEqual(decorated.name, "decorated")
        self.assertEqual(configured.name, "configured")

    def test_node_and_retry_options_fail_fast(self) -> None:
        handler = lambda _context: None
        invalid = (
            lambda: node(object()),
            lambda: node(handler, name=""),
            lambda: node(handler, retry=object()),
            lambda: node(handler, recover=object()),
            lambda: RetryPolicy(max_attempts=0),
            lambda: RetryPolicy(max_attempts=True),
            lambda: RetryPolicy(should_retry=object()),
            lambda: RetryPolicy(delay_ms=-1),
        )
        for factory in invalid:
            with self.subTest(factory=factory), self.assertRaises(GraphDefinitionError):
                factory()  # type: ignore[misc]

    def test_links_are_target_first_ordered_and_unique(self) -> None:
        source = node(lambda _context: None)
        unlabelled = node(lambda _context: None, name="unlabelled")
        named = node(lambda _context: None, name="named")

        source.link(unlabelled)
        source.link(named, "review")

        self.assertEqual(
            [(link.action, link.target.name) for link in source.links()],
            [(None, "unlabelled"), ("review", "named")],
        )
        with self.assertRaises(DuplicateLinkError):
            source.link(node(lambda _context: None))
        with self.assertRaises(DuplicateLinkError):
            source.link(node(lambda _context: None), "review")

    def test_link_arguments_fail_fast(self) -> None:
        source = node(lambda _context: None)
        target = node(lambda _context: None)
        invalid = (
            lambda: source.link(object()),
            lambda: source.link(target, ""),
            lambda: source.link(target, None),
        )
        for call in invalid:
            with self.subTest(call=call), self.assertRaises(GraphDefinitionError):
                call()  # type: ignore[misc]

    def test_flow_captures_and_validates_configuration(self) -> None:
        entry = node(lambda _context: None)
        exits = ["done"]
        flow = Flow(
            entry,
            name="batch",
            exits=exits,
            concurrency=3,
            max_activations=10,
        )
        exits.append("later")

        self.assertEqual(flow.name, "batch")
        self.assertEqual(flow.exits, ("done",))
        self.assertEqual(flow.concurrency, 3)
        self.assertEqual(flow.max_activations, 10)

        invalid = (
            lambda: Flow(object()),
            lambda: Flow(entry, name=""),
            lambda: Flow(entry, exits="done"),
            lambda: Flow(entry, exits=("done", "done")),
            lambda: Flow(entry, concurrency=0),
            lambda: Flow(entry, max_activations=0),
            lambda: Flow(entry, combine=object()),
            lambda: Flow(entry, recover=object()),
        )
        for factory in invalid:
            with self.subTest(factory=factory), self.assertRaises(GraphDefinitionError):
                factory()  # type: ignore[misc]

    def test_compile_rejects_recursive_flow_containment(self) -> None:
        entry = node(lambda _context: None)
        recursive = Flow(entry)
        entry.link(recursive)

        with self.assertRaises(GraphDefinitionError):
            recursive.compile()

    def test_compile_snapshots_topology_and_describe_returns_copies(self) -> None:
        entry = node(lambda _context: None, name="entry")
        entry.link(node(lambda _context: None, name="first"))
        compiled = Flow(entry, name="root").compile()
        before = compiled.describe()

        entry.link(node(lambda _context: None, name="later"), "later")
        self.assertEqual(compiled.describe(), before)
        self.assertNotEqual(Flow(entry).compile().describe(), before)

        before["elements"].clear()  # type: ignore[union-attr]
        self.assertTrue(compiled.describe()["elements"])

    def test_describe_contains_only_topology_and_policies(self) -> None:
        entry = node(lambda _context: None, name="entry")
        description = Flow(entry, name="root", concurrency=2).compile().describe()

        self.assertEqual(description["schema_version"], 1)
        self.assertEqual(description["root"], {"element_id": 1, "scope_id": 1})
        self.assertEqual(
            [item["name"] for item in description["elements"]],  # type: ignore[index,union-attr]
            ["root", "entry"],
        )
        self.assertNotIn("handler", repr(description))


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_uses_one_shallow_copied_shared_state(self) -> None:
        nested: list[str] = []
        initial = {"count": 0, "nested": nested}
        seen: list[dict[str, Any]] = []

        def first(context: Context[dict[str, Any]]) -> None:
            seen.append(context.state)
            context.state["count"] = 1

        def second(context: Context[dict[str, Any]]) -> None:
            seen.append(context.state)
            context.state["count"] += 1
            context.state["nested"].append("shared")

        first_node = node(first)
        first_node.link(node(second))
        state = await Flow(first_node).run(initial)

        self.assertEqual(state, {"count": 2, "nested": ["shared"]})
        self.assertIs(seen[0], seen[1])
        self.assertIsNot(state, initial)
        self.assertEqual(initial, {"count": 0, "nested": ["shared"]})

    async def test_invalid_initial_state_fails_before_callback(self) -> None:
        calls = 0

        def handler(_context: object) -> None:
            nonlocal calls
            calls += 1

        flow = Flow(node(handler))
        with self.assertRaises(TypeError):
            flow.start(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            flow.start({1: "not a string"})  # type: ignore[dict-item]
        self.assertEqual(calls, 0)

    async def test_branch_input_can_be_replaced_and_forwarded(self) -> None:
        seen: list[object] = []

        def produce(context: Context[dict[str, Any]]) -> None:
            context.emit("work", {"value": 7})

        def forward(context: Context[dict[str, Any], object]) -> None:
            seen.append(context.input)
            context.emit()

        def consume(context: Context[dict[str, Any], object]) -> None:
            seen.append(context.input)
            context.state["value"] = context.input

        producer = node(produce)
        forwarding = node(forward)
        producer.link(forwarding, "work")
        forwarding.link(node(consume))

        state = await Flow(producer).run({})
        self.assertEqual(state["value"], {"value": 7})
        self.assertIs(seen[0], seen[1])

    async def test_silent_handler_follows_unlabelled_link(self) -> None:
        first = node(lambda _context: None)
        first.link(node(lambda context: context.state.__setitem__("ran", True)))

        self.assertEqual(await Flow(first).run({}), {"ran": True})

    async def test_silent_leaf_exits_with_current_input(self) -> None:
        dispatch = node(lambda context: context.emit("leaf", 7))
        dispatch.link(node(lambda _context: None), "leaf")

        result = await Flow(dispatch).start({}).result()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.terminals[0].type, "exit")
        self.assertEqual(result.terminals[0].output, 7)

    async def test_end_bypasses_links_and_preserves_output_presence(self) -> None:
        observed: list[ScopeResult] = []

        def finish(context: Context[dict[str, Any]]) -> None:
            context.end()
            context.end(None)

        def combine(_context: object, result: ScopeResult) -> None:
            observed.append(result)

        finishing = node(finish)
        finishing.link(node(lambda context: context.state.__setitem__("ran", True)))
        result = await Flow(finishing, combine=combine).start({}).result()

        self.assertNotIn("ran", result.state)
        self.assertEqual(observed[0].outputs, (None,))
        first, second = result.terminals
        self.assertEqual((first.has_output, first.output), (False, None))
        self.assertEqual((second.has_output, second.output), (True, None))
        self.assertEqual((first.sequence, second.sequence), (1, 2))

    async def test_fanout_combine_reads_all_outputs(self) -> None:
        def dispatch(context: Context[dict[str, Any]]) -> None:
            for value in (1, 2, 3):
                context.emit("work", value)

        def work(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input * 10)

        def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
            context.state["outputs"] = result.outputs

        source = node(dispatch)
        source.link(node(work), "work")
        result = await Flow(source, combine=combine).start({}).result()

        self.assertEqual(result.state["outputs"], (10, 20, 30))
        self.assertEqual([item.output for item in result.terminals], [10, 20, 30])

    async def test_combine_can_replace_nested_terminals_with_one_message(self) -> None:
        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("work", 2)
            context.emit("work", 3)

        def work(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input * 10)

        def combine(context: Context[dict[str, Any]], result: ScopeResult) -> None:
            context.emit(input=sum(result.outputs))

        source = node(dispatch)
        source.link(node(work), "work")
        child = Flow(source, combine=combine)
        child.link(
            node(lambda context: context.state.__setitem__("total", context.input))
        )

        self.assertEqual(await Flow(child).run({}), {"total": 50})

    async def test_declared_exit_succeeds_and_unknown_action_fails(self) -> None:
        exit_node = node(lambda context: context.emit("done", 4))
        completed = await Flow(exit_node, exits=("done",)).start({}).result()
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.terminals[0].action, "done")  # type: ignore[union-attr]

        failed = await Flow(exit_node).start({}).result()
        self.assertEqual(failed.status, "failed")
        if failed.status == "failed":
            self.assertEqual(failed.failure.kind, "unknown_action")

    async def test_control_batch_is_atomic_when_one_action_is_unknown(self) -> None:
        def source(context: Context[dict[str, Any]]) -> None:
            context.emit("valid", 1)
            context.emit("missing", 2)

        source_node = node(source)
        source_node.link(
            node(lambda context: context.state.__setitem__("ran", context.input)),
            "valid",
        )
        result = await Flow(source_node).start({}).result()

        self.assertEqual(result.status, "failed")
        self.assertNotIn("ran", result.state)
        self.assertEqual(result.terminals, ())

    async def test_failed_handler_discards_its_control_buffer(self) -> None:
        cause = RuntimeError("after emit")

        def source(context: Context[dict[str, Any]]) -> None:
            context.emit("valid")
            raise cause

        source_node = node(source)
        source_node.link(
            node(lambda context: context.state.__setitem__("ran", True)), "valid"
        )
        result = await Flow(source_node).start({}).result()

        self.assertEqual(result.status, "failed")
        self.assertNotIn("ran", result.state)
        if result.status == "failed":
            self.assertIs(result.failure.cause, cause)

    async def test_invalid_callback_return_fails_fast(self) -> None:
        result = await Flow(node(lambda _context: 42)).start({}).result()  # type: ignore[arg-type]
        self.assertEqual(result.status, "failed")
        if result.status == "failed":
            self.assertEqual(result.failure.kind, "invalid_outcome")

    async def test_context_closes_after_callback(self) -> None:
        retained: list[Context[dict[str, Any]]] = []

        def handler(context: Context[dict[str, Any]]) -> None:
            retained.append(context)

        await Flow(node(handler)).run({})
        with self.assertRaises(RuntimeError):
            retained[0].emit()
        with self.assertRaises(RuntimeError):
            _ = retained[0].state


class ResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_defers_callbacks_and_memoizes_result(self) -> None:
        calls = 0

        def handler(context: Context[dict[str, Any]]) -> None:
            nonlocal calls
            calls += 1
            context.state["handled"] = True

        handle = Flow(node(handler)).start({})
        self.assertFalse(handle.done())
        self.assertEqual(calls, 0)

        first = await handle.result()
        second = await handle.result()
        self.assertTrue(handle.done())
        self.assertIs(first, second)
        self.assertIsInstance(first, Completed)
        self.assertEqual(first.state, {"handled": True})
        self.assertEqual(calls, 1)

    async def test_run_returns_state_or_raises_exact_failed_result(self) -> None:
        self.assertEqual(
            await Flow(node(lambda context: context.state.__setitem__("x", 1))).run({}),
            {"x": 1},
        )

        cause = ValueError("failed")

        def fail(_context: object) -> None:
            raise cause

        with self.assertRaises(RunError) as raised:
            await Flow(node(fail)).run({})
        self.assertIs(raised.exception.result.failure.cause, cause)
        self.assertIs(raised.exception.__cause__, cause)

    async def test_compiled_flow_is_reusable_with_fresh_state(self) -> None:
        compiled = Flow(node(lambda _context: None)).compile()
        first = await compiled.start({"run": 1}).result()
        second = await compiled.start({"run": 2}).result()

        self.assertEqual(first.state, {"run": 1})
        self.assertEqual(second.state, {"run": 2})
        self.assertIsNot(first.state, second.state)


class RetryAndRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_reuses_state_and_input_but_discards_failed_buffer(
        self,
    ) -> None:
        calls = 0
        payload = object()
        seen_inputs: list[object] = []

        def work(context: Context[dict[str, Any], object]) -> None:
            nonlocal calls
            calls += 1
            seen_inputs.append(context.input)
            context.state["calls"] = calls
            context.end(f"attempt-{calls}")
            if calls < 3:
                raise LookupError("retry")

        dispatch = node(lambda context: context.emit("work", payload))
        dispatch.link(node(work, retry=RetryPolicy(max_attempts=3)), "work")
        result = await Flow(dispatch).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.state, {"calls": 3})
        self.assertEqual([item.output for item in result.terminals], ["attempt-3"])
        self.assertEqual(seen_inputs, [payload, payload, payload])

    async def test_retry_predicate_can_decline_and_node_recovery_can_resume(
        self,
    ) -> None:
        seen: list[object] = []

        def fail(_context: object) -> None:
            raise ValueError("declined")

        def recover(context: Context[dict[str, Any]], failure: object) -> None:
            seen.append(failure)
            context.emit("resume", 9)

        worker = node(
            fail,
            retry=RetryPolicy(max_attempts=3, should_retry=lambda _failure: False),
            recover=recover,
        )
        worker.link(
            node(lambda context: context.state.__setitem__("value", context.input)),
            "resume",
        )

        self.assertEqual(await Flow(worker).run({}), {"value": 9})
        self.assertEqual(len(seen), 1)

    async def test_zero_emission_node_recovery_propagates_failure(self) -> None:
        recovered: list[object] = []

        def fail(_context: object) -> None:
            raise RuntimeError("failed")

        result = (
            await Flow(
                node(fail, recover=lambda _context, failure: recovered.append(failure))
            )
            .start({})
            .result()
        )

        self.assertEqual(result.status, "failed")
        if result.status == "failed":
            self.assertIs(result.failure, recovered[0])

    async def test_retry_policy_failure_replaces_handler_failure(self) -> None:
        policy_error = RuntimeError("policy")

        def fail(_context: object) -> None:
            raise ValueError("handler")

        def bad_policy(_failure: object) -> bool:
            raise policy_error

        result = (
            await Flow(
                node(fail, retry=RetryPolicy(max_attempts=2, should_retry=bad_policy))
            )
            .start({})
            .result()
        )

        self.assertEqual(result.status, "failed")
        if result.status == "failed":
            self.assertEqual(result.failure.kind, "retry_policy")
            self.assertIs(result.failure.cause, policy_error)
            self.assertEqual(result.failure.previous.kind, "handler")  # type: ignore[union-attr]

    async def test_flow_recovery_receives_settled_terminals(self) -> None:
        seen: list[ScopeFailure] = []

        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("done", 1)
            context.emit("fail", 2)
            context.emit("late", 3)

        def fail(_context: object) -> None:
            raise RuntimeError("failed")

        def recover(context: Context[dict[str, Any]], failure: ScopeFailure) -> None:
            seen.append(failure)
            context.end("replacement")

        source = node(dispatch)
        source.link(node(lambda context: context.end(context.input)), "done")
        source.link(node(fail), "fail")
        source.link(
            node(lambda context: context.state.__setitem__("late", True)), "late"
        )
        result = await Flow(source, recover=recover).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertNotIn("late", result.state)
        self.assertEqual([item.output for item in seen[0].terminals], [1])
        self.assertEqual([item.output for item in result.terminals], ["replacement"])

    async def test_combine_failure_exposes_exact_scope_result(self) -> None:
        combined: list[ScopeResult] = []
        recovered: list[ScopeFailure] = []

        def combine(_context: object, result: ScopeResult) -> None:
            combined.append(result)
            raise RuntimeError("combine")

        def recover(context: Context[dict[str, Any]], failure: ScopeFailure) -> None:
            recovered.append(failure)
            context.end(sum(failure.result.outputs))  # type: ignore[union-attr,arg-type]

        result = (
            await Flow(
                node(lambda context: context.end(4)),
                combine=combine,
                recover=recover,
            )
            .start({})
            .result()
        )

        self.assertEqual(result.status, "completed")
        self.assertIs(recovered[0].result, combined[0])
        self.assertEqual(recovered[0].primary.kind, "flow_combine")
        self.assertEqual(result.terminals[0].output, 4)

    async def test_recovery_error_retains_previous_failure(self) -> None:
        recovery_error = RuntimeError("recovery")

        def fail(_context: object) -> None:
            raise ValueError("handler")

        def recover(_context: object, _failure: object) -> None:
            raise recovery_error

        result = await Flow(node(fail), recover=recover).start({}).result()
        self.assertEqual(result.status, "failed")
        if result.status == "failed":
            self.assertEqual(result.failure.kind, "flow_recovery")
            self.assertIs(result.failure.cause, recovery_error)
            self.assertEqual(result.failure.previous.kind, "handler")  # type: ignore[union-attr]

    async def test_nested_flow_recovery_resumes_parent_once(self) -> None:
        def fail(_context: object) -> None:
            raise RuntimeError("nested")

        child = Flow(
            node(fail),
            recover=lambda context, _failure: context.emit(input=11),
        )
        child.link(
            node(lambda context: context.state.__setitem__("value", context.input))
        )

        self.assertEqual(await Flow(child).run({}), {"value": 11})


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_flow_concurrency_is_a_local_callback_limit(self) -> None:
        active = 0
        peak = 0
        started = asyncio.Event()
        release = asyncio.Event()

        def dispatch(context: Context[dict[str, Any]]) -> None:
            for value in range(4):
                context.emit("work", value)

        async def work(context: Context[dict[str, Any], int]) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                started.set()
            await release.wait()
            active -= 1
            context.end(context.input)

        source = node(dispatch)
        source.link(node(work), "work")
        handle = Flow(source, concurrency=2).start({})
        await asyncio.wait_for(started.wait(), 1)
        release.set()
        result = await asyncio.wait_for(handle.result(), 1)

        self.assertEqual(peak, 2)
        self.assertEqual(len(result.terminals), 4)

    async def test_serial_flow_never_overlaps_callbacks(self) -> None:
        active = 0
        peak = 0

        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("work", 1)
            context.emit("work", 2)

        async def work(_context: object) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1

        source = node(dispatch)
        source.link(node(work), "work")
        await Flow(source).run({})
        self.assertEqual(peak, 1)

    async def test_max_activations_stops_a_cycle(self) -> None:
        looping = node(lambda _context: None)
        looping.link(looping)
        result = await Flow(looping, max_activations=3).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status == "failed":
            self.assertEqual(result.failure.kind, "activation_limit")


if __name__ == "__main__":
    unittest.main()
