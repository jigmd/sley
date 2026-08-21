from caskada import Flow, node
from nodes import answer_unreliably, decide_action, search, supervise


def create_agent_inner_flow():
    decide = node(decide_action)
    search_web = node(search)
    answer = node(answer_unreliably)

    decide.link(search_web, "search")
    decide.link(answer, "answer")
    search_web.link(decide, "decide")

    return Flow(decide)


def create_agent_flow():
    agent = create_agent_inner_flow()
    supervisor = node(supervise)

    agent.link(supervisor)
    supervisor.link(agent, "retry")

    return Flow(agent)
