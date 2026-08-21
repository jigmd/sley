from caskada import Flow, node
from nodes import apply_filter, dispatch, load_image, save_image


def build_flow(concurrency: int) -> Flow:
    load = node(load_image)
    apply = node(apply_filter)
    save = node(save_image)
    load.link(apply, "filter")
    apply.link(save, "save")
    item_flow = Flow(load, name="process_image")

    start = node(dispatch)
    start.link(item_flow, "process")
    return Flow(start, concurrency=concurrency)


def create_flows() -> tuple[Flow, Flow]:
    return build_flow(1), build_flow(9)
