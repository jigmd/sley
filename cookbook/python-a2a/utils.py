import os

from duckduckgo_search import DDGS
from openai import OpenAI


def call_llm(prompt):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    r = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[{"role": "user", "content": prompt}],
    )
    content = r.choices[0].message.content
    if content is None:
        raise RuntimeError("OpenAI returned no agent decision")
    return content


def search_web(query):
    results = DDGS().text(query, max_results=5)
    return "\n\n".join(
        f"Title: {result['title']}\nURL: {result['href']}\nSnippet: {result['body']}"
        for result in results
    )
