import os

from openai import OpenAI


def stream_llm(prompt: str):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    return client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        stream=True,
    )
