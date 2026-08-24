import asyncio

from flow import recipe_flow


async def main() -> None:
    print("\nWelcome to Recipe Finder!")
    print("------------------------")
    await recipe_flow.run({})
    print("\nThanks for using Recipe Finder!")


if __name__ == "__main__":
    asyncio.run(main())
