import os

from duckduckgo_search import DDGS
from openai import OpenAI


def call_llm(prompt: str) -> str:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    response = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content or ""


def search_web(query: str) -> str:
    results = DDGS().text(query, max_results=5)
    return "\n\n".join(
        f"Title: {result['title']}\nURL: {result['href']}\nSnippet: {result['body']}"
        for result in results
    )


if __name__ == "__main__":
    prompt = "In a few words, what is the meaning of life?"
    print(f"LLM prompt: {prompt}")
    print(f"LLM response: {call_llm(prompt)}")

    query = "Who won the Nobel Prize in Physics 2024?"
    print(f"\nSearch query: {query}")
    print(search_web(query))
