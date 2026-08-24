from flow import create_flow


async def main():
    print("Processing sales.csv in chunks...")
    flow = create_flow()
    await flow.run({"input_file": "data/sales.csv"})


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
