import os

from openai import OpenAI


def call_llm(prompt: str) -> str:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""
