from nodes import (
    build_component,
    collect_components,
    dispatch_components,
    evaluate_component,
    initialize_run,
    integrate_components,
    judge_whole,
    load_benchmark,
    settle_component,
)
from sley import Flow, node


def build_flow() -> Flow:
    build = node(build_component)
    evaluate = node(evaluate_component)
    build.link(evaluate, "evaluate")
    evaluate.link(build, "revise")
    component = Flow(
        build,
        exits=("passed", "capped", "unreachable"),
        max_activations=8,
    )
    settle = node(settle_component)
    component.link(settle, "passed")
    component.link(settle, "capped")
    component.link(settle, "unreachable")

    dispatch = node(dispatch_components)
    dispatch.link(component, "improve")
    components = Flow(dispatch, concurrency=2, combine=collect_components)

    initialize = node(initialize_run)
    set_bar = node(load_benchmark)
    integrate = node(integrate_components)
    judge = node(judge_whole)

    initialize.link(set_bar)
    set_bar.link(components)
    components.link(integrate, "ready")
    integrate.link(judge)
    judge.link(integrate, "revise")

    return Flow(
        initialize,
        exits=("approved", "stopped"),
        max_activations=10,
    )


quality_flow = build_flow()
