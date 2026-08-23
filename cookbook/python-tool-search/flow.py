from nodes import analyze, search
from sley import Flow


def build_flow() -> Flow:
    search.link(analyze)
    return Flow(search)


search_flow = build_flow()
