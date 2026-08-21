from flow import flow


async def main():
    print("\nWelcome to Text Converter!")
    print("=========================")

    shared = {}
    await flow.run(shared)

    print("\nThank you for using Text Converter!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
