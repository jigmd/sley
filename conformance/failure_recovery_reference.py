from __future__ import annotations

from copy import deepcopy
from typing import Any

FAILURE_MESSAGES = {
    "handler": "Node handler raised",
    "node_recovery": "Node recovery raised",
    "flow_combine": "Flow combine raised",
    "flow_recovery": "Flow recovery raised",
}


def evaluate_failure_recovery(program: dict[str, Any]) -> dict[str, object]:
    topology = program["topology"]
    handler = program["handler"]
    retry_max_attempts = program["retry_max_attempts"]
    node_recovery = program["node_recovery"]
    flow_recovery = program["flow_recovery"]
    _validate_program(
        topology,
        handler,
        retry_max_attempts,
        node_recovery,
        flow_recovery,
    )

    state: dict[str, object] = {}
    failures: list[dict[str, object]] = []
    retries: list[dict[str, object]] = []
    terminals: list[dict[str, object]] = []
    transitions = (
        1 if topology in {"node_after_source", "nested_flow", "combine"} else 0
    )
    scopes = 2 if topology == "nested_flow" else 1
    activations = {
        "root_node": 2,
        "node_after_source": 3,
        "nested_flow": 4,
        "combine": 2,
    }[topology]
    handler_attempts = 1
    previous: dict[str, object] | None = None

    def new_failure(
        kind: str,
        source: str,
        attempt: int | None,
        prior: dict[str, object] | None = None,
    ) -> dict[str, object]:
        failure = {
            "failure_id": len(failures) + 1,
            "kind": kind,
            "message": FAILURE_MESSAGES[kind],
            "source": source,
            "attempt": attempt,
            "previous_failure_id": None if prior is None else prior["failure_id"],
        }
        failures.append(failure)
        return failure

    if topology == "combine":
        state["handler_attempts"] = 1
        terminals.append(_end(program["input"]))
        previous = new_failure("flow_combine", "root", None)
    else:
        state["handler_attempts"] = 1
        previous = new_failure("handler", "worker", 1)
        if handler == "fail_once_then_end" and retry_max_attempts > 1:
            retries.append(
                {
                    "failure_id": previous["failure_id"],
                    "failed_attempt": 1,
                    "next_attempt": 2,
                    "delay_ms": 0,
                }
            )
            handler_attempts = 2
            state["handler_attempts"] = 2
            terminals.append(_end(program["output"]))
            transitions += 1
            previous = None

    if previous is not None and topology != "combine" and node_recovery != "none":
        observation: dict[str, object] = {
            "failure_id": previous["failure_id"],
            "kind": previous["kind"],
        }
        if topology == "node_after_source":
            observation["input"] = deepcopy(program["input"])
        state["node_recovery"] = observation
        if node_recovery == "end":
            terminals.append(_end(program["output"]))
            transitions += 1
            previous = None
        elif node_recovery == "throw":
            previous = new_failure("node_recovery", "worker", None, previous)

    if previous is not None and flow_recovery != "none":
        combine_failure = topology == "combine"
        observation = {
            "failure_id": previous["failure_id"],
            "kind": previous["kind"],
            "failing_activation_id": None if combine_failure else 4,
            "settled_outputs": [program["input"]] if combine_failure else [],
            "result_outputs": [program["input"]] if combine_failure else None,
        }
        if topology == "nested_flow":
            observation["input"] = deepcopy(program["input"])
        state["flow_recovery"] = observation
        if flow_recovery == "end":
            terminals = [_end(program["output"])]
            transitions += 1 if combine_failure else 2
            previous = None
        elif flow_recovery == "throw":
            previous = new_failure(
                "flow_recovery",
                "root" if combine_failure else "child",
                None,
                previous,
            )

    attempts = handler_attempts + (
        1 if topology in {"node_after_source", "nested_flow"} else 0
    )
    stats = {
        "activations": activations,
        "attempts": attempts,
        "transitions": transitions,
        "retries": len(retries),
        "scopes": scopes,
    }
    if previous is None:
        result: dict[str, object] = {
            "status": "completed",
            "state": state,
            "terminals": terminals,
        }
    else:
        result = {
            "status": "failed",
            "state": state,
            "terminals": terminals,
            "failure": previous,
            "suppressed": [],
        }
    snapshot: dict[str, object] = {
        "result": result,
        "trace": {"failures": failures, "retries": retries},
        "stats": stats,
    }
    if previous is not None:
        snapshot["run_projection"] = _run_projection()
    return snapshot


def _end(output: object) -> dict[str, object]:
    return {"type": "end", "has_output": True, "output": deepcopy(output)}


def _run_projection() -> dict[str, object]:
    return {
        "type": "throw",
        "error": {
            "name": "RunError",
            "message": "Caskada run failed",
            "result_status": "failed",
            "cause_is_result_failure_cause": True,
        },
    }


def _validate_program(
    topology: object,
    handler: object,
    retry_max_attempts: object,
    node_recovery: object,
    flow_recovery: object,
) -> None:
    if topology not in {"root_node", "node_after_source", "nested_flow", "combine"}:
        raise AssertionError("unknown failure fixture topology")
    if handler not in {"fail", "fail_once_then_end", "end"}:
        raise AssertionError("unknown failure fixture handler")
    if type(retry_max_attempts) is not int or retry_max_attempts < 1:
        raise AssertionError("failure fixture retry count must be positive")
    if node_recovery not in {"none", "pass", "end", "throw"}:
        raise AssertionError("unknown Node recovery mode")
    if flow_recovery not in {"none", "pass", "end", "throw"}:
        raise AssertionError("unknown Flow recovery mode")
    if topology == "combine" and handler != "end":
        raise AssertionError("combine fixture handler must End")
    if topology != "combine" and handler == "end":
        raise AssertionError("non-combine failure fixture handler cannot End")
