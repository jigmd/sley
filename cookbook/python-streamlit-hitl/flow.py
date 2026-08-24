from sley import Context, Flow, node
from utils.process_task import process_task


@node
def process(context: Context) -> None:
    context.state["processed_output"] = process_task(context.state["task_input"])


@node
def finalize(context: Context) -> None:
    context.state["final_result"] = context.state["processed_output"]


processing_flow = Flow(process)
finalization_flow = Flow(finalize)
