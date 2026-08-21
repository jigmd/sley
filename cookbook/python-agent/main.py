import asyncio
import sys

from flow import agent_flow


def question_from_args() -> str:
    return next(
        (arg[2:] for arg in sys.argv[1:] if arg.startswith("--")),
        "Who won the Nobel Prize in Physics 2024?",
    )


async def main() -> None:
    question = question_from_args()
    print(f"🤔 Processing question: {question}")
    state = await agent_flow.run({"question": question})
    print("\n🎯 Final Answer:")
    print(state.get("answer", "No answer found"))


if __name__ == "__main__":
    asyncio.run(main())
