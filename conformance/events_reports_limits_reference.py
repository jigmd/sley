from __future__ import annotations


def evaluate_events_reports_limits(scenario: str) -> dict[str, object]:
    if scenario == "successful_trace":
        return {
            "committed_terminal_sequence": 1,
            "end_terminal_sequence": 1,
            "kinds": [
                "run_started",
                "scope_started",
                "callback_started",
                "callback_finished",
                "transition_committed",
                "callback_started",
                "callback_finished",
                "transition_committed",
                "terminal_committed",
                "scope_finished",
                "run_finished",
            ],
            "route_destination": "activation",
            "run_ids": ["fixture-events"],
            "sequences": list(range(1, 12)),
            "status": "completed",
        }
    if scenario == "observer_skip":
        return {
            "attempts": 1,
            "calls": 0,
            "kinds": [
                "run_started",
                "scope_started",
                "callback_started",
                "cancellation_fenced",
                "callback_finished",
                "scope_finished",
                "run_finished",
            ],
            "status": "cancelled",
        }
    if scenario == "observer_throw":
        return {
            "calls": 1,
            "diagnostic": {"event_sequence": 1, "message": "Observer raised"},
            "diagnostic_count": 1,
            "status": "completed",
        }
    if scenario == "report_presence":
        return {
            "report_count": 2,
            "reports": [
                {"has_data": False, "name": "started"},
                {"data": None, "has_data": True, "name": "value"},
            ],
            "status": "completed",
        }
    if scenario == "report_reentrant":
        return {
            "diagnostic": {
                "event_sequence": 4,
                "message": "Observer reentrancy disabled",
            },
            "published_reports": 1,
            "report_count": 1,
            "status": "completed",
        }
    if scenario == "report_overflow":
        return _limit(
            limit="max_reports",
            activation_id=2,
            attempt=1,
            activations=2,
            attempts=1,
            transitions=0,
            reports=1,
            scopes=1,
            observations={
                "caught": 2,
                "failure_fences": 1,
                "published_reports": 1,
            },
        )
    if scenario == "transition_overflow":
        return _limit(
            limit="max_transitions",
            activation_id=2,
            attempt=1,
            activations=2,
            attempts=1,
            transitions=0,
            reports=0,
            scopes=1,
            observations={
                "caught": True,
                "caught_kinds": [
                    "failure_recorded",
                    "failure_fenced:run",
                    "cancellation_fenced:run",
                ],
                "control_order": [
                    "failure_recorded",
                    "failure_fenced:run",
                    "cancellation_fenced:run",
                    "callback_finished",
                    "run_finished",
                ],
            },
        )
    if scenario == "capacity_priority":
        return _limit(
            limit="max_activations",
            activation_id=2,
            attempt=1,
            activations=2,
            attempts=1,
            transitions=0,
            reports=0,
            scopes=1,
        )
    if scenario == "depth_limit":
        return _limit(
            limit="max_depth",
            activation_id=3,
            attempt=None,
            activations=3,
            attempts=1,
            transitions=1,
            reports=0,
            scopes=1,
        )
    if scenario == "attempt_limit":
        return _limit(
            limit="max_attempts",
            activation_id=3,
            attempt=None,
            activations=3,
            attempts=1,
            transitions=1,
            reports=0,
            scopes=1,
            observations={"calls": ["source"]},
        )
    raise AssertionError(f"unknown events/reports/limits scenario {scenario!r}")


def _limit(
    *,
    limit: str,
    activation_id: int,
    attempt: int | None,
    activations: int,
    attempts: int,
    transitions: int,
    reports: int,
    scopes: int,
    observations: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "failure": {
            "activation_id": activation_id,
            "attempt": attempt,
            "kind": "limit",
            "limit": limit,
            "scope_id": 1,
        },
        "observations": {} if observations is None else observations,
        "stats": {
            "activations": activations,
            "attempts": attempts,
            "peak_ready": 1,
            "reports": reports,
            "scopes": scopes,
            "transitions": transitions,
        },
        "status": "failed",
        "terminal_count": 0,
    }
