from caskada import Context, Flow, RunOptions, node


def handler(context: Context[dict[str, int]]) -> None:
    context.state["visits"] = context.state.get("visits", 0) + 1


flow: Flow[dict[str, int]] = Flow(node(handler), max_activations=3)
options = RunOptions(
    max_concurrency=2,
    max_activations=3,
    max_attempts=2,
    max_transitions=2,
    max_ready=2,
    max_reports=2,
    max_depth=2,
)


async def project() -> dict[str, int]:
    return await flow.run({}, options=options)
