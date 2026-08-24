import sys

from flow import create_chain_of_thought_flow


async def main():
    default_question = "You keep rolling a fair die until you roll three, four, five in that order consecutively on three rolls. What is the probability that you roll the die an odd number of times?"

    question = default_question
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            question = arg[2:]
            break

    print(f"🤔 Processing question: {question}")

    cot_flow = create_chain_of_thought_flow()
    initial_state = {
        "problem": question,
        "thoughts": [],
        "current_thought_number": 0,
        "total_thoughts_estimate": 10,
        "solution": None,
    }

    await cot_flow.run(initial_state)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
