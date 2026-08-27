import csv

CHUNK_SIZE = 1000


def dispatch_chunks(context):
    emitted = False
    with open(context.state["input_file"], newline="", encoding="utf-8") as source:
        rows = csv.DictReader(source)
        chunk = []
        for row in rows:
            chunk.append(float(row["amount"]))
            if len(chunk) == CHUNK_SIZE:
                context.emit("chunk", chunk)
                emitted = True
                chunk = []
        if chunk:
            context.emit("chunk", chunk)
            emitted = True
    if not emitted:
        raise ValueError("CSV contains no transactions")


def process_chunk(context):
    amounts = context.input
    total_sales = sum(amounts)

    print(f"Processor: Finished chunk with {len(amounts)} transactions")
    # end(value) finishes this worker and contributes value to result.outputs.
    context.end(
        {
            "total_sales": total_sales,
            "num_transactions": len(amounts),
        }
    )


def show_stats(context):
    stats = context.state["statistics"]

    print("\nFinal Statistics:")
    print(f"- Total Sales: ${stats['total_sales']:,.2f}")
    print(f"- Average Sale: ${stats['average_sale']:,.2f}")
    print(f"- Total Transactions: {stats['total_transactions']:,}\n")
