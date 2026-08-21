from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from caskada import Context, Flow, GraphElement, RunError, ScopeResult, node

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "serial.json"
IMPLEMENTED_FIXTURES = {
    "S01_implicit_default",
    "S02_explicit_input",
    "S03_hard_end",
    "S04_output_presence",
    "S05_fanout_combine",
    "S06_combine_replacement",
    "S07_declared_exit",
    "S08_unknown_action",
    "S09_nested_forwarding",
    "S11_state_copy",
    "S12_explicit_null_input",
    "S13_atomic_batch_rejection",
}


class FixtureRuntime:
    def __init__(self, program: dict[str, Any]) -> None:
        self.program = program

    def build(self) -> Flow[dict[str, Any]]:
        definitions = self.program["elements"]
        elements: dict[str, GraphElement[dict[str, Any]]] = {
            identifier: node(
                self._node_handler(definition.get("steps", [])),
                name=identifier,
            )
            for identifier, definition in definitions.items()
            if definition["kind"] == "node"
        }
        unresolved = {
            identifier: definition
            for identifier, definition in definitions.items()
            if definition["kind"] == "flow"
        }
        while unresolved:
            progressed = False
            for identifier, definition in tuple(unresolved.items()):
                entry = elements.get(definition["entry"])
                if entry is None:
                    continue
                combine = self._combine_handler(definition.get("combine", []))
                elements[identifier] = Flow(
                    entry,
                    name=identifier,
                    exits=definition.get("exits", ()),
                    concurrency=definition.get("concurrency", 1),
                    combine=combine,
                )
                del unresolved[identifier]
                progressed = True
            if not progressed:
                raise AssertionError("fixture Flow entries contain an unresolved cycle")

        for link in self.program["links"]:
            source = elements[link["source"]]
            target = elements[link["target"]]
            if "action" in link:
                source.link(target, link["action"])
            else:
                source.link(target)
        root = elements[self.program["root"]]
        if type(root) is not Flow:
            raise AssertionError("fixture root must be a Flow")
        return root

    def _node_handler(self, steps: list[dict[str, Any]]) -> Any:
        def handler(context: Context[dict[str, Any], object]) -> None:
            self._execute_steps(context, steps, None)

        return handler

    def _combine_handler(self, steps: list[dict[str, Any]]) -> Any:
        if not steps:
            return None

        def combine(
            context: Context[dict[str, Any], object], result: ScopeResult
        ) -> None:
            self._execute_steps(context, steps, result.outputs)

        return combine

    def _execute_steps(
        self,
        context: Context[dict[str, Any], object],
        steps: list[dict[str, Any]],
        outputs: tuple[object, ...] | None,
    ) -> None:
        for step in steps:
            operation = step["op"]
            if operation == "set":
                _set_path(
                    context.state,
                    step["path"],
                    self._evaluate(context, step["value"], outputs),
                )
            elif operation == "append":
                target = _read_path(context.state, step["path"])
                if not isinstance(target, list):
                    raise AssertionError("append target must be a list")
                target.append(self._evaluate(context, step["value"], outputs))
            elif operation == "emit":
                value_present = "input" in step
                value = (
                    self._evaluate(context, step["input"], outputs)
                    if value_present
                    else context.input
                )
                if "action" in step:
                    if value_present:
                        context.emit(step["action"], value)
                    else:
                        context.emit(step["action"])
                elif value_present:
                    context.emit(input=value)
                else:
                    context.emit()
            elif operation == "end":
                if "output" in step:
                    context.end(self._evaluate(context, step["output"], outputs))
                else:
                    context.end()
            else:
                raise AssertionError(f"unknown fixture operation {operation!r}")

    def _evaluate(
        self,
        context: Context[dict[str, Any], object],
        expression: object,
        outputs: tuple[object, ...] | None,
    ) -> object:
        if isinstance(expression, list):
            return [self._evaluate(context, item, outputs) for item in expression]
        if not isinstance(expression, dict):
            return expression
        if "$" not in expression:
            return {
                key: self._evaluate(context, value, outputs)
                for key, value in expression.items()
            }
        kind = expression["$"]
        if kind == "input":
            return _read_path(context.input, expression.get("path", []))
        if kind == "state":
            return _read_path(context.state, expression.get("path", []))
        if kind == "outputs":
            if outputs is None:
                raise AssertionError("outputs expression is combine-only")
            return list(outputs)
        if kind == "add":
            return self._evaluate(
                context, expression["left"], outputs
            ) + self._evaluate(context, expression["right"], outputs)  # type: ignore[operator]
        if kind == "multiply":
            return self._evaluate(
                context, expression["left"], outputs
            ) * self._evaluate(context, expression["right"], outputs)  # type: ignore[operator]
        if kind == "sum":
            values = self._evaluate(context, expression["items"], outputs)
            if not isinstance(values, list):
                raise AssertionError("sum expression requires a list")
            return sum(values)
        raise AssertionError(f"unknown fixture expression {kind!r}")


def _read_path(value: object, path: list[str]) -> object:
    current = value
    for key in path:
        if not isinstance(current, dict):
            raise TypeError("fixture path does not reference a record")
        current = current[key]
    return current


def _set_path(state: dict[str, Any], path: list[str], value: object) -> None:
    if not path:
        raise AssertionError("state path cannot be empty")
    current = state
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _normalize_terminal(terminal: object) -> dict[str, object]:
    terminal_type = terminal.type
    has_output = terminal.has_output
    if terminal_type == "end":
        result: dict[str, object] = {"type": "end", "has_output": has_output}
    else:
        result = {
            "type": "exit",
            "action": terminal.action,
            "has_output": True,
        }
    if has_output:
        output = terminal.output
        result["output"] = (
            {"$host": "missing"}
            if terminal_type == "exit" and output is None
            else output
        )
    return result


async def _run_fixture(fixture: dict[str, Any]) -> dict[str, object]:
    initial_state = fixture["program"]["initial_state"]
    runtime = FixtureRuntime(fixture["program"])
    compiled = runtime.build().compile()
    settled = await compiled.start(initial_state).result()
    terminals = [_normalize_terminal(item) for item in settled.terminals]
    outputs = [item["output"] for item in terminals if item["has_output"]]
    if settled.status == "failed":
        detail = settled.failure.detail
        if detail is None or detail.type != "unknown_action":
            raise AssertionError("S08 requires unknown_action detail")
        names = {
            element["element_id"]: element["name"]
            for element in compiled.describe()["elements"]
        }
        failure = {
            "kind": settled.failure.kind,
            "action": detail.action,
            "source": names[settled.failure.element_id],
        }
        try:
            await compiled.run(initial_state)
        except RunError as error:
            projection: dict[str, object] = {
                "type": "throw",
                "error": {
                    "name": type(error).__name__,
                    "message": str(error),
                    "result_status": error.result.status,
                },
            }
        else:
            raise AssertionError("failed run projection did not raise RunError")
        failed_record: dict[str, object] = {
            "id": fixture["id"],
            "result": {
                "status": "failed",
                "state": settled.state,
                "terminals": terminals,
                "failure": failure,
            },
            "run_projection": projection,
        }
        if fixture["id"] == "S13_atomic_batch_rejection":
            failed_record.pop("run_projection")
            failed_record["stats"] = {
                "activations": settled.stats.activations,
                "attempts": settled.stats.attempts,
                "transitions": settled.stats.transitions,
                "retries": settled.stats.retries,
                "reports": settled.stats.reports,
                "scopes": settled.stats.scopes,
                "peak_ready": settled.stats.peak_ready,
                "peak_callbacks": settled.stats.peak_callbacks,
            }
        return failed_record

    result: dict[str, object] = {
        "id": fixture["id"],
        "result": {
            "status": "completed",
            "state": settled.state,
            "terminals": terminals,
            "terminal_outputs": outputs,
        },
    }
    if "initial_state_after" in fixture["expect"]:
        result["initial_state_after"] = initial_state
    return result


async def _main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures = [
        await _run_fixture(fixture)
        for fixture in collection["fixtures"]
        if fixture["id"] in IMPLEMENTED_FIXTURES
    ]
    print(json.dumps({"fixtures": fixtures}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(_main())
