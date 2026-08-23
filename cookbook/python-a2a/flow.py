from nodes import answer, decide, search
from sley import Flow

decide.link(search, "search")
decide.link(answer, "answer")
search.link(decide, "decide")

agent_flow = Flow(decide)
