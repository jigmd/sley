import asyncio

from flow import create_flow


async def main():
    url = input("Enter website URL to crawl (e.g., https://example.com): ")
    if not url:
        print("Error: URL is required")
        return

    max_pages = input("How many pages to crawl? (Enter a number): ")

    initial_state = {
        "base_url": url,
        "max_pages": int(max_pages) if max_pages else 10,
    }

    state = await create_flow().run(initial_state)
    print("\nReport generated:")
    print(state["report"])


if __name__ == "__main__":
    asyncio.run(main())
