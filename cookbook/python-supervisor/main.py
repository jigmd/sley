import sys

from flow import create_agent_flow


async def main():
    default_question = "Who won the Nobel Prize in Physics 2024?"

    question = default_question
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            question = arg[2:]
            break

    agent_flow = create_agent_flow()

    print(f"🤔 Processing question: {question}")
    state = await agent_flow.run({"question": question})
    print("\n🎯 Final Answer:")
    print(state.get("answer", "No answer found"))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
