import asyncio


async def process_task(input_data):
    print(f"Processing: {input_data}")
    await asyncio.sleep(2)
    return f"Processed: {input_data}"
