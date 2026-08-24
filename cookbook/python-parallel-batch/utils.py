import os

from anthropic import AsyncAnthropic


async def call_llm(prompt: str) -> str:
    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "your-api-key"))
    response = await client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=20_000,
        thinking={"type": "enabled", "budget_tokens": 16_000},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[-1].text
