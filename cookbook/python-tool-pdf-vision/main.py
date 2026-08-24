import asyncio

from flow import vision_flow


async def main() -> None:
    state = await vision_flow.run({})
    for result in state["results"]:
        print(f"\nFile: {result['filename']}")
        print("-" * 50)
        print(result["text"])


if __name__ == "__main__":
    asyncio.run(main())
