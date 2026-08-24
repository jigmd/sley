from openai import OpenAI


def call_llm(prompt: str) -> str:
    client = OpenAI(api_key="YOUR_API_KEY_HERE")
    response = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content or ""
