import asyncio

from flow import word_counter


async def main() -> None:
    await word_counter.run({})


if __name__ == "__main__":
    asyncio.run(main())
