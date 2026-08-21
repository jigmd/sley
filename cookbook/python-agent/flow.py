from caskada import Flow
from nodes import answer, decide, search


def build_agent() -> Flow:
    decide.link(search, "search")
    decide.link(answer, "answer")
    search.link(decide, "decide")
    return Flow(decide)


agent_flow = build_agent()
