from nodes import refine_plan
from sley import Flow, RetryPolicy, node


def create_refinement_flow() -> Flow:
    refine = node(
        refine_plan,
        retry=RetryPolicy(max_attempts=3, delay_ms=1_000),
    )
    refine.link(refine, "continue")
    return Flow(refine, max_activations=4)
