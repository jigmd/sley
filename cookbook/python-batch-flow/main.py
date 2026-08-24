import asyncio

from flow import batch_flow


async def main() -> None:
    print("Processing images with filters...")
    await batch_flow.run({})
    print("\nAll images processed successfully!")
    print("Check the 'output' directory for results.")


if __name__ == "__main__":
    asyncio.run(main())
