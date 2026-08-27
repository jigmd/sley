import os

from openai import OpenAI


def stream_llm(prompt: str):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        stream=True,
    )
