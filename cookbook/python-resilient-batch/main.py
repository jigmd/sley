import asyncio

from caskada import Flow, node


def dispatch(context):
    for record in context.state["records"]:
        context.emit("record", record)


def import_record(context):
    record = context.input
    try:
        amount = float(record["amount"])
    except ValueError as error:
        raise ValueError(f"record {record['id']} has an invalid amount") from error

    print(f"Imported record {record['id']}")
    context.end({"id": record["id"], "amount": amount})


def keep_completed(context, failure):
    imported = [
        terminal.output for terminal in failure.terminals if terminal.has_output
    ]
    context.state["imported"] = imported
    context.state["error"] = failure.primary.message

    print(f"Recovery kept {len(imported)} completed record")
    print(f"Failure: {failure.primary.message}")

    # Recovery replaces the partial terminals with one completed batch result.
    context.end({"imported": len(imported), "error": failure.primary.message})


dispatch_node = node(dispatch)
dispatch_node.link(node(import_record), "record")
batch = Flow(dispatch_node, concurrency=1, recover=keep_completed)


async def main():
    result = await batch.start(
        {
            "records": [
                {"id": 1, "amount": "12.50"},
                {"id": 2, "amount": "invalid"},
                {"id": 3, "amount": "9.75"},
            ]
        }
    ).result()

    print(f"Run status: {result.status}")
    print(f"Final terminals: {len(result.terminals)}")


if __name__ == "__main__":
    asyncio.run(main())
