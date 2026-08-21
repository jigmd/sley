import os

from anthropic import Anthropic


def call_llm(prompt: str) -> str:
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "your-api-key"))
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=20_000,
        thinking={"type": "enabled", "budget_tokens": 16_000},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[-1].text
