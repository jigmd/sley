from __future__ import annotations

import unittest
from typing import Any

from caskada import Context, Flow, RunOptions, ScopeFailure, ScopeResult, node


class FlowRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_flow_recovers_one_failed_child(self) -> None:
        seen: list[ScopeFailure] = []
        suppressed_inside: list[tuple[object, ...]] = []
        handler_state: list[dict[str, Any]] = []
        recovery_state: list[dict[str, Any]] = []

        def fail(context: Context[dict[str, Any]]) -> None:
            handler_state.append(context.state)
            context.state["attempted"] = True
            raise LookupError("child")

        def recover(
            context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            recovery_state.append(context.state)
            seen.append(failure)
            suppressed_inside.append(tuple(failure.suppressed))
            self.assertIsNone(context.input)
            self.assertIsNone(context.attempt)
            context.end("recovered")

        result = await Flow(node(fail), recover=recover).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.state, {"attempted": True})
        self.assertIs(handler_state[0], recovery_state[0])
        self.assertEqual(len(seen), 1)
        scoped = seen[0]
        self.assertEqual(scoped.primary.kind, "handler")
        self.assertEqual(suppressed_inside, [()])
        self.assertEqual(scoped.suppressed, ())
        self.assertEqual(scoped.settled_before_fence, ())
        self.assertIsNone(scoped.result)
        self.assertEqual(scoped.failing_activation_id, 2)
        self.assertNotIn("LookupError", repr(scoped))
        self.assertEqual(
            [terminal.output for terminal in result.terminals], ["recovered"]
        )

    async def test_scope_fence_discards_ready_siblings_and_reports_prior_terminals(
        self,
    ) -> None:
        seen: list[ScopeFailure] = []

        def dispatch(context: Context[dict[str, Any]]) -> None:
            context.emit("done", 1)
            context.emit("fail", 2)
            context.emit("late", 3)

        def done(context: Context[dict[str, Any], int]) -> None:
            context.end(context.input)

        def fail(_context: Context[dict[str, Any], int]) -> None:
            raise RuntimeError("failed")

        def late(context: Context[dict[str, Any], int]) -> None:
            context.state["late"] = context.input

        def recover(
            context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            seen.append(failure)
            context.end("replacement")

        source = node(dispatch)
        source.link(node(done), "done")
        source.link(node(fail), "fail")
        source.link(node(late), "late")
        result = await Flow(source, recover=recover).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertNotIn("late", result.state)
        self.assertEqual(len(seen[0].settled_before_fence), 1)
        self.assertEqual(seen[0].settled_before_fence[0].output, 1)
        self.assertEqual(seen[0].failing_activation_id, 4)
        self.assertEqual(
            [terminal.output for terminal in result.terminals], ["replacement"]
        )
        self.assertEqual(result.stats.attempts, 3)

    async def test_combine_failure_exposes_its_exact_scope_result(self) -> None:
        combined: list[ScopeResult] = []
        recovered: list[ScopeFailure] = []
        cause = RuntimeError("combine")

        def combine(_context: Context[dict[str, Any]], result: ScopeResult) -> None:
            combined.append(result)
            raise cause

        def recover(
            context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            recovered.append(failure)
            context.end(sum(value for value in failure.result.outputs))  # type: ignore[union-attr]

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
        self.assertEqual(len(recovered), 1)
        scoped = recovered[0]
        self.assertEqual(scoped.primary.kind, "flow_combine")
        self.assertIs(scoped.primary.cause, cause)
        self.assertIs(scoped.result, combined[0])
        self.assertIsNone(scoped.failing_activation_id)
        self.assertEqual(scoped.settled_before_fence, combined[0].terminals)
        self.assertEqual([terminal.output for terminal in result.terminals], [4])

    async def test_zero_emission_recovery_propagates_the_exact_primary(self) -> None:
        seen: list[ScopeFailure] = []
        suppressed_inside: list[tuple[object, ...]] = []

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise ValueError("unhandled")

        def recover(
            _context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            seen.append(failure)
            suppressed_inside.append(tuple(failure.suppressed))

        result = await Flow(node(fail), recover=recover).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("zero-emission Flow recovery must propagate")
        self.assertIs(result.failure, seen[0].primary)
        self.assertEqual(result.suppressed, suppressed_inside[0])
        self.assertEqual(tuple(seen[0].suppressed), suppressed_inside[0])
        self.assertEqual(result.terminals, seen[0].settled_before_fence)

    async def test_recovery_throw_replaces_primary_and_retains_previous(self) -> None:
        seen: list[ScopeFailure] = []
        recovery_cause = RuntimeError("recovery")

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise LookupError("handler")

        def recover(
            _context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            seen.append(failure)
            raise recovery_cause

        result = await Flow(node(fail), recover=recover).start({}).result()

        self.assertEqual(result.status, "failed")
        if result.status != "failed":
            self.fail("recovery throw must fail")
        self.assertEqual(result.failure.kind, "flow_recovery")
        self.assertIs(result.failure.cause, recovery_cause)
        self.assertIsNone(result.failure.attempt)
        self.assertIs(result.failure.previous, seen[0].primary)
        self.assertEqual(result.suppressed, ())

    async def test_nested_zero_recovery_escalates_with_controlling_input(self) -> None:
        payload = {"job": 8}
        child_failures: list[ScopeFailure] = []
        parent_failures: list[ScopeFailure] = []

        def fail(context: Context[dict[str, Any], object]) -> None:
            self.assertIs(context.input, payload)
            raise RuntimeError("nested")

        def child_recover(
            context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            self.assertIs(context.input, payload)
            child_failures.append(failure)

        child = Flow(node(fail), recover=child_recover)
        dispatch = node(lambda context: context.emit("child", payload))
        dispatch.link(child, "child")

        def parent_recover(
            context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            self.assertIs(context.input, payload)
            parent_failures.append(failure)
            context.end("parent-recovered")

        result = await Flow(dispatch, recover=parent_recover).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertIs(parent_failures[0].primary, child_failures[0].primary)
        self.assertEqual(child_failures[0].failing_activation_id, 4)
        self.assertEqual(parent_failures[0].failing_activation_id, 3)
        self.assertEqual(
            [terminal.output for terminal in result.terminals], ["parent-recovered"]
        )

    async def test_nested_recovery_success_resumes_parent_once(self) -> None:
        resumes = 0

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise RuntimeError("nested")

        def child_recover(
            context: Context[dict[str, Any], object], _failure: ScopeFailure
        ) -> None:
            context.emit(input=11)

        child = Flow(node(fail), recover=child_recover)

        def resume(context: Context[dict[str, Any], int]) -> None:
            nonlocal resumes
            resumes += 1
            context.state["value"] = context.input

        child.link(node(resume))
        result = await Flow(child).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(resumes, 1)
        self.assertEqual(result.state, {"value": 11})

    async def test_nested_recovery_throw_reaches_parent_as_one_failed_flow(
        self,
    ) -> None:
        child_seen: list[ScopeFailure] = []
        parent_seen: list[ScopeFailure] = []

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise LookupError("handler")

        def child_recover(
            _context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            child_seen.append(failure)
            raise RuntimeError("child recovery")

        child = Flow(node(fail), recover=child_recover)

        def parent_recover(
            context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            parent_seen.append(failure)
            context.end()

        result = await Flow(child, recover=parent_recover).start({}).result()

        self.assertEqual(result.status, "completed")
        self.assertEqual(parent_seen[0].primary.kind, "flow_recovery")
        self.assertIs(parent_seen[0].primary.previous, child_seen[0].primary)
        self.assertEqual(parent_seen[0].failing_activation_id, 2)

    async def test_invalid_flow_recovery_bypasses_parent_recovery(self) -> None:
        parent_called = False

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise RuntimeError("handler")

        def invalid_recovery(
            _context: Context[dict[str, Any], object], _failure: ScopeFailure
        ) -> object:
            return object()

        child = Flow(
            node(fail),
            recover=invalid_recovery,  # type: ignore[arg-type]
        )

        def parent_recovery(
            _context: Context[dict[str, Any], object], _failure: ScopeFailure
        ) -> None:
            nonlocal parent_called
            parent_called = True

        result = await Flow(child, recover=parent_recovery).start({}).result()

        self.assertEqual(result.status, "failed")
        self.assertFalse(parent_called)
        if result.status != "failed":
            self.fail("invalid Flow recovery must fail")
        self.assertEqual(result.failure.kind, "invalid_combination")
        self.assertEqual(result.failure.previous.kind, "handler")  # type: ignore[union-attr]

    async def test_nested_boundary_preflight_keeps_the_producing_flow_ids(self) -> None:
        parent_called = False

        def combine(
            context: Context[dict[str, Any], object], _result: ScopeResult
        ) -> None:
            context.emit("missing")

        child = Flow(node(lambda _context: None), combine=combine)

        def parent_recover(
            _context: Context[dict[str, Any], object], _failure: ScopeFailure
        ) -> None:
            nonlocal parent_called
            parent_called = True

        result = await Flow(child, recover=parent_recover).start({}).result()

        self.assertEqual(result.status, "failed")
        self.assertFalse(parent_called)
        if result.status != "failed":
            self.fail("unknown combine action must fail")
        self.assertEqual(result.failure.kind, "unknown_action")
        self.assertEqual(result.failure.scope_id, 2)
        self.assertEqual(result.failure.activation_id, 2)
        self.assertEqual(result.failure.element_id, 2)
        self.assertIsNone(result.failure.attempt)

        def fail(_context: Context[dict[str, Any]]) -> None:
            raise RuntimeError("handler")

        def invalid_recovery_route(
            context: Context[dict[str, Any], object], _failure: ScopeFailure
        ) -> None:
            context.emit("missing")

        recovery_result = (
            await Flow(node(fail), recover=invalid_recovery_route).start({}).result()
        )
        self.assertEqual(recovery_result.status, "failed")
        if recovery_result.status != "failed":
            self.fail("unknown recovery action must fail")
        self.assertEqual(recovery_result.failure.kind, "unknown_action")
        self.assertEqual(recovery_result.failure.scope_id, 1)
        self.assertEqual(recovery_result.failure.activation_id, 1)
        self.assertEqual(recovery_result.failure.element_id, 1)
        self.assertIsNone(recovery_result.failure.attempt)
        self.assertEqual(recovery_result.failure.previous.kind, "handler")  # type: ignore[union-attr]

    async def test_deep_failure_propagation_is_iterative(self) -> None:
        def fail(_context: Context[dict[str, Any]]) -> None:
            raise RuntimeError("deep")

        element = node(fail)
        for index in range(1_500):
            element = Flow(element, name=f"nested-{index}")

        def recover(
            context: Context[dict[str, Any], object], failure: ScopeFailure
        ) -> None:
            context.state["kind"] = failure.primary.kind
            context.end()

        state = await Flow(element, recover=recover).run(
            {},
            options=RunOptions(max_depth=1_501),
        )

        self.assertEqual(state, {"kind": "handler"})


if __name__ == "__main__":
    unittest.main()
