import os

from openai import OpenAI


def get_embedding(text):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    response = client.embeddings.create(
        model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        input=text,
    )
    return response.data[0].embedding
