from caskada import Context, node
from utils.process_task import process_task


@node
async def process(context: Context) -> None:
    context.state["processed_output"] = await process_task(context.state["task_input"])


@node
async def review(context: Context) -> None:
    channel = context.state["review"]
    await context.state["sse_queue"].put(
        {
            "status": "waiting_for_review",
            "output_to_review": context.state["processed_output"],
        }
    )

    # The HTTP endpoint sets this event after storing the user's decision.
    await channel["event"].wait()
    channel["event"].clear()
    feedback = channel["feedback"]
    channel["feedback"] = None

    if feedback == "approved":
        context.state["final_result"] = context.state["processed_output"]
        context.emit("approved")
    else:
        context.emit("rejected")


@node
def show_result(context: Context) -> None:
    print("--- FINAL RESULT ---")
    print(context.state["final_result"])
