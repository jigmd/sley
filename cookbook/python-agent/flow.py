from nodes import answer, decide, search
from sley import Flow


def build_agent() -> Flow:
    decide.link(search, "search")
    decide.link(answer, "answer")
    search.link(decide, "decide")
    return Flow(decide, max_activations=20)


agent_flow = build_agent()
