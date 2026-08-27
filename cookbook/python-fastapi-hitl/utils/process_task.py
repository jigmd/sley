import asyncio


async def process_task(input_data, revision_instructions=None):
    print(f"Processing: {input_data}")
    await asyncio.sleep(2)
    if revision_instructions:
        return f"Revised: {input_data} ({revision_instructions})"
    return f"Processed: {input_data}"
