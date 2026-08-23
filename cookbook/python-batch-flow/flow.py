from nodes import apply_filter, dispatch, load_image, save_image
from sley import Flow, node


def build_flow() -> Flow:
    load = node(load_image)
    apply = node(apply_filter)
    save = node(save_image)
    load.link(apply, "filter")
    apply.link(save, "save")
    image_flow = Flow(load, name="process_image")

    start = node(dispatch)
    start.link(image_flow, "process")
    return Flow(start)


batch_flow = build_flow()
