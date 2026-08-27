from nodes import (
    collect_candidates,
    dispatch_angles,
    edit_winner,
    generate_candidate,
    run_tournament,
)
from sley import Flow, node


def build_flow() -> Flow:
    dispatch = node(dispatch_angles)
    generate = node(generate_candidate)
    dispatch.link(generate, "generate")
    candidates = Flow(dispatch, concurrency=4, combine=collect_candidates)

    tournament = node(run_tournament)
    edit = node(edit_winner)
    candidates.link(tournament)
    tournament.link(edit)

    return Flow(candidates)


selection_flow = build_flow()
