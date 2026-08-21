from __future__ import annotations

from typing import Any

CANCEL_REASON = "fixture-cancel"


def evaluate_scheduling_cancellation(program: dict[str, Any]) -> dict[str, object]:
    scenario = program["scenario"]
    _validate_program(program)

    if scenario in {"auto_width", "nested_auto_width", "global_ceiling"}:
        width = program["width"]
        nested = scenario == "nested_auto_width"
        peak = program.get("max_concurrency", width)
        return _snapshot(
            status="completed",
            outputs=list(range(width)),
            terminal_count=width,
            observations={"peak": peak},
            activations=width + (3 if nested else 2),
            attempts=width + 1,
            transitions=(3 * width if nested else 2 * width),
            scopes=2 if nested else 1,
            peak_callbacks=peak,
        )

    if scenario == "retry_ready_priority":
        return _snapshot(
            status="completed",
            outputs=["blocker", "retry", "new"],
            terminal_count=3,
            observations={"order": ["retry:1", "blocker:1", "retry:2", "new:1"]},
            activations=5,
            attempts=5,
            transitions=6,
            retries=1,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "fair_scope_rotation":
        return _snapshot(
            status="completed",
            outputs=[
                ["A", 0],
                ["A", 1],
                ["A", 2],
                ["B", 0],
                ["B", 1],
                ["B", 2],
            ],
            terminal_count=6,
            observations={"b0_before_a2": True, "work_count": 6},
            activations=12,
            attempts=9,
            transitions=20,
            scopes=3,
            peak_callbacks=1,
        )

    if scenario == "sibling_signal_before_recovery":
        return _snapshot(
            status="completed",
            state={"recovered": True},
            terminal_count=1,
            observations={"scope_reason": "scope_failed", "sibling_signalled": True},
            activations=4,
            attempts=3,
            transitions=3,
            scopes=1,
            peak_callbacks=2,
        )

    if scenario == "parked_retry_packet":
        return _snapshot(
            status="failed",
            suppressed=[{"attempt": 1, "kind": "handler"}],
            observations={
                "primary_is_controller": True,
                "suppressed_is_parked": True,
            },
            activations=4,
            attempts=3,
            transitions=2,
            retries=1,
            scopes=1,
            peak_callbacks=2,
        )

    if scenario == "attempt_limit_before_permit":
        return _snapshot(
            status="failed",
            observations={"calls": ["source", "first"], "limit": "max_attempts"},
            activations=4,
            attempts=2,
            transitions=2,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario in {"zero_delay_retry_priority", "observer_retry_delay"}:
        return _snapshot(
            status="completed",
            outputs=["retry", "peer"],
            terminal_count=2,
            observations={"order": ["retry:1", "retry:2", "peer:1"]},
            activations=4,
            attempts=4,
            transitions=4,
            retries=1,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "node_recovery_priority":
        return _snapshot(
            status="completed",
            outputs=["recovered", "peer"],
            terminal_count=2,
            observations={"order": ["handle:bad", "recover:bad", "handle:peer"]},
            activations=4,
            attempts=3,
            transitions=4,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "ready_waiter_capacity":
        return _snapshot(
            status="failed",
            observations={"calls": ["dispatch", "active"], "limit": "max_ready"},
            activations=4,
            attempts=2,
            transitions=2,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "cancel_before_admission":
        return _snapshot(
            status="cancelled",
            observations={"called": False},
            activations=2,
            attempts=0,
            transitions=0,
            scopes=1,
            peak_callbacks=0,
        )

    if scenario == "cancel_after_buffer":
        return _cancelled_active()

    if scenario == "post_signal_suppression":
        return _cancelled_active(suppressed=[{"attempt": 1, "kind": "handler"}])

    if scenario == "prior_terminal_ready_discard":
        return _snapshot(
            status="cancelled",
            outputs=[1],
            terminal_count=1,
            observations={"late_present": False},
            activations=5,
            attempts=3,
            transitions=4,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "cancel_retry_delay":
        return _cancelled_active(
            suppressed=[{"attempt": 1, "kind": "handler"}],
            retries=1,
        )

    if scenario in {"cancel_node_recovery", "cancel_flow_recovery"}:
        return _cancelled_active(suppressed=[{"attempt": 1, "kind": "handler"}])

    if scenario == "failure_grace_abandonment":
        return _snapshot(
            status="abandoned",
            cause={"attempt": 1, "kind": "handler", "type": "failure"},
            observations={
                "fences": [
                    "failure_fenced:scope",
                    "cancellation_fenced:scope",
                    "failure_fenced:run",
                    "cancellation_fenced:run",
                    "run_finished:abandoned",
                ],
                "recovery_called": False,
            },
            activations=4,
            attempts=3,
            transitions=2,
            scopes=1,
            peak_callbacks=2,
        )

    if scenario == "retry_suppression_unique":
        return _snapshot(
            status="failed",
            suppressed=[{"attempt": 1, "kind": "handler"}],
            observations={
                "primary_is_second_attempt": True,
                "previous_is_timeout": True,
                "suppression_is_unique": True,
            },
            activations=2,
            attempts=2,
            transitions=0,
            retries=1,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "concurrent_cancel_abandonment":
        return _snapshot(
            status="abandoned",
            cause={
                "deadline": False,
                "reason": CANCEL_REASON,
                "type": "cancellation",
            },
            observations={
                "fences": [
                    "cancellation_fenced:run",
                    "run_finished:abandoned",
                ]
            },
            activations=4,
            attempts=3,
            transitions=2,
            scopes=1,
            peak_callbacks=2,
        )

    if scenario == "sync_retry_policy_grace":
        return _snapshot(
            status="abandoned",
            cause={
                "deadline": False,
                "reason": CANCEL_REASON,
                "type": "cancellation",
            },
            suppressed=[{"attempt": 1, "kind": "handler"}],
            observations={"recorded_failure_kinds": ["handler"]},
            activations=2,
            attempts=1,
            transitions=0,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "route_packet_cancellation":
        return _snapshot(
            status="cancelled",
            suppressed=[
                {"attempt": 1, "kind": "handler_timeout"},
                {"attempt": 1, "kind": "handler"},
            ],
            activations=2,
            attempts=2,
            transitions=0,
            retries=1,
            scopes=1,
            peak_callbacks=1,
        )

    if scenario == "nested_scope_failure_status":
        return _snapshot(
            status="completed",
            state={"recovered": True},
            terminal_count=1,
            observations={"scope_finishes": ["2:failed", "1:completed"]},
            activations=3,
            attempts=1,
            transitions=2,
            scopes=2,
            peak_callbacks=1,
        )

    if scenario == "opening_observer_deadline":
        return _snapshot(
            status="cancelled",
            cancellation={"deadline": True, "reason": "deadline_exceeded"},
            observations={"called": False, "done_on_return": True},
            activations=2,
            attempts=0,
            transitions=0,
            scopes=1,
            peak_callbacks=0,
        )

    raise AssertionError(f"unknown scheduling/cancellation scenario {scenario!r}")


def _cancelled_active(
    *,
    suppressed: list[dict[str, object]] | None = None,
    retries: int = 0,
) -> dict[str, object]:
    return _snapshot(
        status="cancelled",
        suppressed=[] if suppressed is None else suppressed,
        activations=2,
        attempts=1,
        transitions=0,
        retries=retries,
        scopes=1,
        peak_callbacks=1,
    )


def _snapshot(
    *,
    status: str,
    state: dict[str, object] | None = None,
    outputs: list[object] | None = None,
    terminal_count: int = 0,
    suppressed: list[dict[str, object]] | None = None,
    cause: dict[str, object] | None = None,
    cancellation: dict[str, object] | None = None,
    observations: dict[str, object] | None = None,
    activations: int,
    attempts: int,
    transitions: int,
    retries: int = 0,
    scopes: int,
    peak_callbacks: int,
) -> dict[str, object]:
    result: dict[str, object] = {
        "outputs": [] if outputs is None else outputs,
        "state": {} if state is None else state,
        "status": status,
        "suppressed": [] if suppressed is None else suppressed,
        "terminal_count": terminal_count,
    }
    if status == "cancelled":
        result["cancellation"] = (
            {"deadline": False, "reason": CANCEL_REASON}
            if cancellation is None
            else cancellation
        )
    if status == "abandoned":
        if cause is None:
            raise AssertionError("abandoned fixture requires a cause")
        result["cause"] = cause
    return {
        "observations": {} if observations is None else observations,
        "result": result,
        "stats": {
            "activations": activations,
            "attempts": attempts,
            "peak_callbacks": peak_callbacks,
            "retries": retries,
            "scopes": scopes,
            "transitions": transitions,
        },
    }


def _validate_program(program: dict[str, Any]) -> None:
    scenario = program.get("scenario")
    known = {
        "auto_width",
        "nested_auto_width",
        "global_ceiling",
        "retry_ready_priority",
        "fair_scope_rotation",
        "sibling_signal_before_recovery",
        "parked_retry_packet",
        "attempt_limit_before_permit",
        "zero_delay_retry_priority",
        "observer_retry_delay",
        "node_recovery_priority",
        "ready_waiter_capacity",
        "cancel_before_admission",
        "cancel_after_buffer",
        "post_signal_suppression",
        "prior_terminal_ready_discard",
        "cancel_retry_delay",
        "cancel_node_recovery",
        "cancel_flow_recovery",
        "failure_grace_abandonment",
        "retry_suppression_unique",
        "concurrent_cancel_abandonment",
        "sync_retry_policy_grace",
        "route_packet_cancellation",
        "nested_scope_failure_status",
        "opening_observer_deadline",
    }
    if scenario not in known:
        raise AssertionError("unknown scheduling/cancellation fixture scenario")
    if scenario in {"auto_width", "nested_auto_width", "global_ceiling"}:
        width = program.get("width")
        if type(width) is not int or width < 1:
            raise AssertionError("width must be a positive integer")
    ceiling = program.get("max_concurrency")
    if ceiling is not None and (type(ceiling) is not int or ceiling < 1):
        raise AssertionError("max_concurrency must be a positive integer")
