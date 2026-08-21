from flow import qa_flow


async def main() -> None:
    # run() waits for the Flow and returns its final shared state.
    state = await qa_flow.run(
        {
            "question": "In one sentence, what's the end of universe?",
            "answer": None,
        }
    )

    print("Question:", state["question"])
    print("Answer:", state["answer"])


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
