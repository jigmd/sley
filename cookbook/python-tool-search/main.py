import asyncio

from flow import search_flow


async def main() -> None:
    query = input("Enter search query: ")
    if not query:
        print("Error: Query is required")
        return

    await search_flow.run({"query": query, "num_results": 5})


if __name__ == "__main__":
    asyncio.run(main())
