from nodes import (
    collect_sections,
    dispatch_sections,
    edit_brief,
    plan_brief,
    write_section,
)
from sley import Flow, node


def build_flow() -> Flow:
    dispatch = node(dispatch_sections)
    write = node(write_section)
    dispatch.link(write, "write")
    workers = Flow(dispatch, concurrency=3, combine=collect_sections)

    plan = node(plan_brief)
    edit = node(edit_brief)
    plan.link(workers, "build")
    workers.link(edit)

    return Flow(plan)


brief_flow = build_flow()
