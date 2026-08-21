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
            observations={"sibling_signalled": True},
            activations=4,
            attempts=3,
            transitions=3,
            scopes=1,
            peak_callbacks=2,
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
        result["cancellation"] = {"deadline": False, "reason": CANCEL_REASON}
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
        "cancel_before_admission",
        "cancel_after_buffer",
        "post_signal_suppression",
        "prior_terminal_ready_discard",
        "cancel_retry_delay",
        "cancel_node_recovery",
        "cancel_flow_recovery",
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
