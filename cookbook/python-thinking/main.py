import argparse

from flow import create_refinement_flow


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("problem", nargs="?")
    parser.add_argument("--max-iterations", type=int, default=4)
    return parser.parse_args()


async def main() -> None:
    default_question = "You keep rolling a fair die until you roll three, four, five in that order consecutively on three rolls. What is the probability that you roll the die an odd number of times?"
    args = arguments()
    if not 1 <= args.max_iterations <= 4:
        raise ValueError("--max-iterations must be between 1 and 4")
    question = args.problem or default_question
    print(f"Refining a plan for: {question}")

    initial_state = {
        "problem": question,
        "max_iterations": args.max_iterations,
        "iterations": [],
        "solution": None,
    }
    await create_refinement_flow().run(initial_state)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
