from caskada import Flow, node
from nodes import dispatch_chunks, process_chunk, show_stats


def combine_chunks(context, result):
    # result.outputs contains values published by the workers' end(value) calls.
    total_sales = sum(chunk["total_sales"] for chunk in result.outputs)
    total_transactions = sum(chunk["num_transactions"] for chunk in result.outputs)

    context.state["statistics"] = {
        "total_sales": total_sales,
        "average_sale": total_sales / total_transactions,
        "total_transactions": total_transactions,
    }

    # Replace all worker terminals with one continuation to show_stats.
    context.emit()


def create_flow():
    dispatch = node(dispatch_chunks)
    process = node(process_chunk)
    show = node(show_stats)

    dispatch.link(process, "chunk")
    batch = Flow(dispatch, combine=combine_chunks)
    # The combiner's unlabelled emission follows this link after the batch settles.
    batch.link(show)

    return Flow(batch)
