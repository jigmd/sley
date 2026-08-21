import asyncio

from flow import voice_chat


async def main() -> None:
    print("Starting Caskada Voice Chat...")
    print("Speak after 'Listening for your query...' appears.")
    print("Press Ctrl+C to stop, or remain silent to end the Flow.")
    await voice_chat.run({"chat_history": []})


if __name__ == "__main__":
    asyncio.run(main())
