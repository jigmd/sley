from caskada import Flow, RetryPolicy, node
from nodes import chain_of_thought


def create_chain_of_thought_flow():
    thought = node(
        chain_of_thought,
        retry=RetryPolicy(max_attempts=3, delay_ms=10_000),
    )

    thought.link(thought, "continue")

    return Flow(thought, max_activations=50)
