from caskada import Flow
from nodes import analyze, search


def build_flow() -> Flow:
    search.link(analyze)
    return Flow(search)


search_flow = build_flow()
