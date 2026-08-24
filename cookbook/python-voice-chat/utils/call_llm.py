import os

from openai import OpenAI


def call_llm(messages):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))

    response = client.chat.completions.create(
        model="gpt-4o", messages=messages, temperature=0.7
    )

    return response.choices[0].message.content


if __name__ == "__main__":
    prompt = "In one sentence, what makes a conversation feel natural?"
    print(f"Prompt: {prompt}")
    print(f"Response: {call_llm([{'role': 'user', 'content': prompt}])}")
