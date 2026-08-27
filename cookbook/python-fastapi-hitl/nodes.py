from sley import Context, node
from utils.process_task import process_task


@node
async def process(context: Context) -> None:
    context.state["processed_output"] = await process_task(
        context.state["task_input"], context.state.pop("revision_instructions", None)
    )


@node
async def review(context: Context) -> None:
    channel = context.state["review"]
    channel["waiting"] = True
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
    channel["waiting"] = False

    if feedback["decision"] == "approved":
        context.state["final_result"] = context.state["processed_output"]
        context.emit("approved")
    else:
        revisions = context.state.setdefault("revision_count", 0) + 1
        context.state["revision_count"] = revisions
        if revisions > context.state["max_revisions"]:
            raise RuntimeError("human review exceeded the revision limit")
        context.state["revision_instructions"] = feedback["instructions"]
        context.emit("rejected")


@node
def show_result(context: Context) -> None:
    print("--- FINAL RESULT ---")
    print(context.state["final_result"])
