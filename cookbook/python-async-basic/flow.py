from caskada import Flow
from nodes import approve, fetch, suggest


def build_flow() -> Flow:
    fetch.link(suggest, "suggest")
    suggest.link(approve, "approve")
    approve.link(suggest, "retry")
    return Flow(fetch)


recipe_flow = build_flow()
