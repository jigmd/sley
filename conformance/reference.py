from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


class _Missing:
    pass


MISSING = _Missing()


@dataclass(frozen=True)
class Arm:
    kind: str
    action: str | None = None
    value: object = MISSING
    present: bool = False


@dataclass(frozen=True)
class Terminal:
    type: str
    action: str | None = None
    value: object = MISSING
    has_output: bool = False


@dataclass(frozen=True)
class ContractFailure:
    kind: str
    action: str
    source: str


def normalize(value: object) -> object:
    if value is MISSING:
        return {"$host": "missing"}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, tuple):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value


def _read_path(value: object, path: list[str]) -> object:
    current = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise AssertionError(f"fixture expression cannot read {path!r}")
        current = current[key]
    return current


class ReferenceInterpreter:
    def __init__(self, program: dict[str, Any]):
        self.program = deepcopy(program)
        self.elements: dict[str, dict[str, Any]] = self.program["elements"]
        self.links: list[dict[str, Any]] = self.program["links"]
        self._validate_program()

        self.caller_state: dict[str, Any] = deepcopy(self.program["initial_state"])
        self.state: dict[str, Any] = dict(self.caller_state)
        self.events: list[str] = []
        self.stats = {
            "activations": 0,
            "attempts": 0,
            "transitions": 0,
            "retries": 0,
            "reports": 0,
            "scopes": 0,
            "peak_ready": 0,
            "peak_callbacks": 0,
            "duration_ms": 0,
        }

    def _validate_program(self) -> None:
        root = self.program["root"]
        if root not in self.elements or self.elements[root]["kind"] != "flow":
            raise AssertionError("program root must name a Flow")

        seen_links: set[tuple[str, str | None]] = set()
        for key, element in self.elements.items():
            if element["kind"] == "flow" and element["entry"] not in self.elements:
                raise AssertionError(f"Flow {key!r} has an unknown entry")
        for link in self.links:
            source = link["source"]
            target = link["target"]
            if source not in self.elements or target not in self.elements:
                raise AssertionError("link source and target must name elements")
            identity = (source, link.get("action"))
            if identity in seen_links:
                raise AssertionError(f"duplicate fixture link {identity!r}")
            seen_links.add(identity)

    def compile(self) -> dict[str, object]:
        root_key = self.program["root"]
        next_element_id = 1
        next_scope_id = 2
        placements: dict[tuple[int, str], int] = {}
        element_records: dict[int, dict[str, object]] = {}
        scope_records: list[dict[str, object]] = []
        pending_scopes: list[tuple[str, int, int | None]] = [(root_key, 1, None)]

        def place(scope_id: int, key: str, parent_scope_id: int | None) -> int:
            nonlocal next_element_id, next_scope_id
            identity = (scope_id, key)
            if identity in placements:
                return placements[identity]
            element_id = next_element_id
            next_element_id += 1
            placements[identity] = element_id
            element = self.elements[key]
            if element["kind"] == "flow":
                if element_id == 1:
                    owned_scope_id = 1
                else:
                    owned_scope_id = next_scope_id
                    next_scope_id += 1
                    pending_scopes.append((key, owned_scope_id, scope_id))
                element_records[element_id] = {
                    "element_id": element_id,
                    "kind": "flow",
                    "name": key,
                    "parent_scope_definition_id": parent_scope_id,
                    "owned_scope_definition_id": owned_scope_id,
                    "links": [],
                }
            else:
                element_records[element_id] = {
                    "element_id": element_id,
                    "kind": "node",
                    "name": key,
                    "parent_scope_definition_id": scope_id,
                    "links": [],
                    "retry": {"max_attempts": 1},
                    "timeout_ms": None,
                }
            return element_id

        root_element_id = place(1, root_key, None)

        while pending_scopes:
            flow_key, scope_id, parent_scope_id = pending_scopes.pop(0)
            flow = self.elements[flow_key]
            flow_element_id = placements[(parent_scope_id or 1, flow_key)]
            entry_key = flow["entry"]
            entry_id = place(scope_id, entry_key, scope_id)
            scope_records.append(
                {
                    "scope_definition_id": scope_id,
                    "owner_element_id": flow_element_id,
                    "parent_scope_definition_id": parent_scope_id,
                    "entry_element_id": entry_id,
                    "exits": list(flow.get("exits", [])),
                    "concurrency": flow.get("concurrency", 1),
                    "max_activations": None,
                }
            )

            queue = [entry_key]
            visited: set[str] = set()
            while queue:
                source = queue.pop(0)
                if source in visited:
                    continue
                visited.add(source)
                source_id = place(scope_id, source, scope_id)
                for link in self.links:
                    if link["source"] != source:
                        continue
                    target = link["target"]
                    target_was_new = (scope_id, target) not in placements
                    target_id = place(scope_id, target, scope_id)
                    element_records[source_id]["links"].append(
                        {
                            "action": link.get("action"),
                            "target_element_id": target_id,
                        }
                    )
                    if target_was_new:
                        queue.append(target)

        auto_max = max(
            element.get("concurrency", 1)
            for element in self.elements.values()
            if element["kind"] == "flow"
        )
        return {
            "schema_version": 1,
            "auto_max_concurrency": auto_max,
            "root": {"element_id": root_element_id, "scope_definition_id": 1},
            "elements": [element_records[index] for index in sorted(element_records)],
            "scope_definitions": scope_records,
        }

    def run(self) -> dict[str, object]:
        self.events.append("run_started")
        self.stats["activations"] = 1  # Root Flow owner.
        terminals, failure = self._execute_flow(
            self.program["root"], MISSING, root=True
        )
        self.events.append("run_finished")

        if failure is not None:
            result: dict[str, object] = {
                "status": "failed",
                "state": normalize(self.state),
                "terminals": [self._normalize_terminal(item) for item in terminals],
                "failure": {
                    "kind": failure.kind,
                    "action": failure.action,
                    "source": failure.source,
                },
            }
        else:
            if not terminals:
                raise AssertionError("a completed root Flow must have a terminal")
            result = {
                "status": "completed",
                "state": normalize(self.state),
                "terminals": [self._normalize_terminal(item) for item in terminals],
                "terminal_outputs": [
                    normalize(item.value) for item in terminals if item.has_output
                ],
            }

        if failure is None:
            run_projection: dict[str, object] = {
                "type": "return",
                "state": normalize(self.state),
            }
        else:
            run_projection = {
                "type": "throw",
                "error": {
                    "name": "RunError",
                    "message": "Caskada run failed",
                    "result_status": "failed",
                },
            }

        return {
            "compiled": self.compile(),
            "result": result,
            "run_projection": run_projection,
            "event_kinds": list(self.events),
            "stats": dict(self.stats),
            "initial_state_after": normalize(self.caller_state),
        }

    def _execute_flow(
        self, flow_key: str, incoming: object, *, root: bool
    ) -> tuple[list[Terminal], ContractFailure | None]:
        flow = self.elements[flow_key]
        self.stats["scopes"] += 1
        self.events.append("scope_started")

        self.stats["activations"] += 1  # This scope's entry.
        queue: list[tuple[str, object]] = [(flow["entry"], incoming)]
        self._record_ready(queue)
        terminals: list[Terminal] = []

        while queue:
            element_key, branch_input = queue.pop(0)
            element = self.elements[element_key]
            if element["kind"] == "flow":
                child_terminals, failure = self._execute_flow(
                    element_key, branch_input, root=False
                )
                if failure is not None:
                    self.events.append("scope_finished")
                    return terminals, failure
                failure = self._forward_child(
                    flow_key, element_key, child_terminals, queue, terminals
                )
                if failure is not None:
                    self.events.append("scope_finished")
                    return terminals, failure
                continue

            self.stats["attempts"] += 1
            self.stats["peak_callbacks"] = max(self.stats["peak_callbacks"], 1)
            self.events.append("callback_started")
            arms = self._execute_steps(element["steps"], branch_input, None)
            if not arms:
                arms = [Arm("emit", value=branch_input, present=True)]
            self.events.append("callback_finished")
            failure = self._route_arms(flow_key, element_key, arms, queue, terminals)
            if failure is not None:
                self.events.append("scope_finished")
                return terminals, failure

        if "combine" in flow:
            outputs = [item.value for item in terminals if item.has_output]
            self.events.append("callback_started")
            combine_arms = self._execute_steps(flow["combine"], incoming, outputs)
            self.events.append("callback_finished")
            if combine_arms:
                terminals = []
                for arm in combine_arms:
                    self.stats["transitions"] += 1
                    self.events.append("transition_committed")
                    if arm.kind == "end":
                        terminal = Terminal(
                            "end", value=arm.value, has_output=arm.present
                        )
                    else:
                        terminal = Terminal(
                            "exit",
                            action=arm.action,
                            value=arm.value,
                            has_output=True,
                        )
                    terminals.append(terminal)
                    self.events.append("terminal_committed")

        self.events.append("scope_finished")
        return terminals, None

    def _forward_child(
        self,
        parent_flow_key: str,
        child_key: str,
        child_terminals: list[Terminal],
        queue: list[tuple[str, object]],
        terminals: list[Terminal],
    ) -> ContractFailure | None:
        arms: list[Arm] = []
        for terminal in child_terminals:
            if terminal.type == "end":
                arms.append(
                    Arm("end", value=terminal.value, present=terminal.has_output)
                )
            else:
                arms.append(
                    Arm(
                        "emit",
                        action=terminal.action,
                        value=terminal.value,
                        present=True,
                    )
                )
        return self._route_arms(parent_flow_key, child_key, arms, queue, terminals)

    def _route_arms(
        self,
        flow_key: str,
        source_key: str,
        arms: list[Arm],
        queue: list[tuple[str, object]],
        terminals: list[Terminal],
    ) -> ContractFailure | None:
        resolutions: list[tuple[str, str | None]] = []
        flow = self.elements[flow_key]

        for arm in arms:
            if arm.kind == "end":
                resolutions.append(("end", None))
                continue
            target = self._link_target(source_key, arm.action)
            if target is not None:
                resolutions.append(("target", target))
            elif arm.action is None or arm.action in flow.get("exits", []):
                resolutions.append(("exit", None))
            else:
                return ContractFailure("unknown_action", arm.action, source_key)

        for arm, (resolution, target) in zip(arms, resolutions, strict=True):
            self.stats["transitions"] += 1
            self.events.append("transition_committed")
            if resolution == "target":
                assert target is not None
                self.stats["activations"] += 1
                queue.append((target, arm.value))
                self._record_ready(queue)
            elif resolution == "end":
                terminals.append(
                    Terminal("end", value=arm.value, has_output=arm.present)
                )
                self.events.append("terminal_committed")
            else:
                terminals.append(
                    Terminal(
                        "exit",
                        action=arm.action,
                        value=arm.value,
                        has_output=True,
                    )
                )
                self.events.append("terminal_committed")
        return None

    def _link_target(self, source: str, action: str | None) -> str | None:
        for link in self.links:
            if link["source"] == source and link.get("action") == action:
                return link["target"]
        return None

    def _execute_steps(
        self,
        steps: list[dict[str, Any]],
        branch_input: object,
        outputs: list[object] | None,
    ) -> list[Arm]:
        arms: list[Arm] = []
        for step in steps:
            operation = step["op"]
            if operation == "set":
                self._set_path(
                    step["path"],
                    self._evaluate(step["value"], branch_input, outputs),
                )
            elif operation == "append":
                target = _read_path(self.state, step["path"])
                if not isinstance(target, list):
                    raise AssertionError("append target must be a list")
                target.append(self._evaluate(step["value"], branch_input, outputs))
            elif operation == "emit":
                value = (
                    self._evaluate(step["input"], branch_input, outputs)
                    if "input" in step
                    else branch_input
                )
                arms.append(
                    Arm(
                        "emit",
                        action=step.get("action"),
                        value=value,
                        present=True,
                    )
                )
            elif operation == "end":
                present = "output" in step
                value = (
                    self._evaluate(step["output"], branch_input, outputs)
                    if present
                    else MISSING
                )
                arms.append(Arm("end", value=value, present=present))
            else:
                raise AssertionError(f"unknown fixture operation {operation!r}")
        return arms

    def _evaluate(
        self, expression: object, branch_input: object, outputs: list[object] | None
    ) -> object:
        if isinstance(expression, list):
            return [self._evaluate(item, branch_input, outputs) for item in expression]
        if not isinstance(expression, dict):
            return expression
        if "$" not in expression:
            return {
                key: self._evaluate(value, branch_input, outputs)
                for key, value in expression.items()
            }

        kind = expression["$"]
        if kind == "input":
            return _read_path(branch_input, expression.get("path", []))
        if kind == "state":
            return _read_path(self.state, expression.get("path", []))
        if kind == "outputs":
            if outputs is None:
                raise AssertionError("outputs expression is combine-only")
            return list(outputs)
        if kind == "add":
            return self._evaluate(
                expression["left"], branch_input, outputs
            ) + self._evaluate(expression["right"], branch_input, outputs)
        if kind == "multiply":
            return self._evaluate(
                expression["left"], branch_input, outputs
            ) * self._evaluate(expression["right"], branch_input, outputs)
        if kind == "sum":
            items = self._evaluate(expression["items"], branch_input, outputs)
            if not isinstance(items, list):
                raise AssertionError("sum expression requires a list")
            return sum(items)
        raise AssertionError(f"unknown fixture expression {kind!r}")

    def _set_path(self, path: list[str], value: object) -> None:
        if not path:
            raise AssertionError("state path cannot be empty")
        current: dict[str, Any] = self.state
        for key in path[:-1]:
            child = current.get(key)
            if not isinstance(child, dict):
                child = {}
                current[key] = child
            current = child
        current[path[-1]] = value

    def _record_ready(self, queue: list[tuple[str, object]]) -> None:
        self.stats["peak_ready"] = max(self.stats["peak_ready"], len(queue))

    @staticmethod
    def _normalize_terminal(terminal: Terminal) -> dict[str, object]:
        if terminal.type == "end":
            value: dict[str, object] = {
                "type": "end",
                "has_output": terminal.has_output,
            }
        else:
            value = {
                "type": "exit",
                "action": terminal.action,
                "has_output": True,
            }
        if terminal.has_output:
            value["output"] = normalize(terminal.value)
        return value
