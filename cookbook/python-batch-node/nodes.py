import pandas as pd


def dispatch_chunks(context):
    chunks = pd.read_csv(context.state["input_file"], chunksize=1000)

    for index, chunk in enumerate(chunks):
        # Each emit starts one branch; this value becomes its context.input.
        context.emit("chunk", (index, chunk))


def process_chunk(context):
    index, chunk = context.input
    total_sales = chunk["amount"].sum()

    print(f"Processor: Finished chunk {index}")
    # end(value) finishes this worker and contributes value to result.outputs.
    context.end(
        {
            "total_sales": total_sales,
            "num_transactions": len(chunk),
        }
    )


def show_stats(context):
    stats = context.state["statistics"]

    print("\nFinal Statistics:")
    print(f"- Total Sales: ${stats['total_sales']:,.2f}")
    print(f"- Average Sale: ${stats['average_sale']:,.2f}")
    print(f"- Total Transactions: {stats['total_transactions']:,}\n")
