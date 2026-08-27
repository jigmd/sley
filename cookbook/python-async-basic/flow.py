from nodes import approve, fetch, suggest
from sley import Flow


def build_flow() -> Flow:
    fetch.link(suggest, "suggest")
    suggest.link(approve, "approve")
    approve.link(suggest, "retry")
    return Flow(fetch, max_activations=50)


recipe_flow = build_flow()
