import asyncio

from flow import selection_flow


async def main() -> None:
    state = await selection_flow.run(
        {
            "request": (
                "Explain to a small engineering team why explicit workflow "
                "graphs can be easier to maintain than nested callbacks."
            ),
            "angles": ["direct", "worked-example", "checklist", "tradeoff-first"],
            "seed": 7,
        }
    )

    print("\nFinal selected answer:")
    print(state["final_answer"])


if __name__ == "__main__":
    asyncio.run(main())
