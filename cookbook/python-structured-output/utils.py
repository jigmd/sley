import os

from openai import OpenAI


def call_llm(prompt: str) -> str:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("OpenAI returned no structured output")
    return content
