import os

from openai import OpenAI


def call_llm(messages):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=messages,
        temperature=0.7,
    )
    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("OpenAI returned no answer")
    return content


if __name__ == "__main__":
    prompt = "In one sentence, what makes a conversation feel natural?"
    print(f"Prompt: {prompt}")
    print(f"Response: {call_llm([{'role': 'user', 'content': prompt}])}")
