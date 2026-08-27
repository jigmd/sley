import asyncio

from flow import create_flow


async def main():
    url = input("Enter website URL to crawl (e.g., https://example.com): ")
    if not url:
        print("Error: URL is required")
        return

    max_pages = input("How many pages to crawl? (Enter a number): ")
    try:
        page_limit = int(max_pages) if max_pages else 10
    except ValueError as error:
        raise ValueError("page count must be an integer") from error

    initial_state = {
        "base_url": url,
        "max_pages": page_limit,
    }

    state = await create_flow().run(initial_state)
    print("\nReport generated:")
    print(state["report"])


if __name__ == "__main__":
    asyncio.run(main())
