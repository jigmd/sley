from caskada import Flow
from nodes import answer, decide, search

decide.link(search, "search")
decide.link(answer, "answer")
search.link(decide, "decide")

agent_flow = Flow(decide)
