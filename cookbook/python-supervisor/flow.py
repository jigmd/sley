from nodes import build_candidate, evaluate_candidate
from sley import Flow, node


def create_supervisor_flow() -> Flow:
    build = node(build_candidate)
    candidate_flow = Flow(build, exits=("candidate",), max_activations=2)

    evaluate = node(evaluate_candidate)
    candidate_flow.link(evaluate, "candidate")
    evaluate.link(candidate_flow, "revise")

    return Flow(
        candidate_flow,
        exits=("approved", "stopped"),
        max_activations=8,
    )


supervisor_flow = create_supervisor_flow()
