import asyncio

from flow import chat_flow


async def main() -> None:
    print("=" * 50)
    print("Caskada Chat with Memory")
    print("=" * 50)
    print("This chat keeps your 3 most recent conversations")
    print("and brings back relevant past conversations when helpful")
    print("Type 'exit' to end the conversation")
    print("=" * 50)
    await chat_flow.run({})


if __name__ == "__main__":
    asyncio.run(main())
