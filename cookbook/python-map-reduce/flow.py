from caskada import Flow, node
from nodes import (
    collect_evaluations,
    evaluate_resume,
    map_resumes,
    read_resumes,
    reduce_results,
)


def build_flow() -> Flow:
    mapper = node(map_resumes)
    evaluator = node(evaluate_resume)
    mapper.link(evaluator, "evaluate")
    map_flow = Flow(mapper, concurrency=5, combine=collect_evaluations)

    read = node(read_resumes)
    reduce = node(reduce_results)
    read.link(map_flow)
    map_flow.link(reduce)
    return Flow(read)


resume_flow = build_flow()
