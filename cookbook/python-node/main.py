import asyncio

from flow import flow


async def main() -> None:
    text = """
    Sley is a structured graph runtime. Functions perform work, links choose
    what runs next, and Flows define execution boundaries.
    """

    state = await flow.run({"data": text, "summary": None})
    if state["summary"] is None:
        raise RuntimeError("The summarizer completed without a summary")

    print("\nInput text:", text)
    print("\nSummary:", state["summary"])


if __name__ == "__main__":
    asyncio.run(main())
