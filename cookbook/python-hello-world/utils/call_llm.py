from openai import OpenAI


def call_llm(prompt: str) -> str:
    client = OpenAI(api_key="YOUR_API_KEY_HERE")
    r = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": prompt}]
    )
    content = r.choices[0].message.content
    if content is None:
        raise RuntimeError("OpenAI returned no answer")
    return content


if __name__ == "__main__":
    prompt = "What is the meaning of life?"
    print(call_llm(prompt))
