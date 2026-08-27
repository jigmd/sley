import os

from openai import OpenAI


def call_llm(prompt):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("OpenAI returned no answer")
    return content


def get_embedding(text):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(
        model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        input=text,
    )
    return response.data[0].embedding


def fixed_size_chunk(text, chunk_size=2000):
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i : i + chunk_size])
    return chunks


if __name__ == "__main__":
    print("=== Testing call_llm ===")
    prompt = "In a few words, what is the meaning of life?"
    print(f"Prompt: {prompt}")
    response = call_llm(prompt)
    print(f"Response: {response}")

    print("=== Testing embedding function ===")
    text1 = "The quick brown fox jumps over the lazy dog."
    text2 = "Python is a popular programming language for data science."

    oai_emb1 = get_embedding(text1)
    oai_emb2 = get_embedding(text2)
    print(f"OpenAI Embedding dimension: {len(oai_emb1)}")
    oai_similarity = sum(left * right for left, right in zip(oai_emb1, oai_emb2))
    print(f"OpenAI similarity between texts: {oai_similarity:.4f}")
