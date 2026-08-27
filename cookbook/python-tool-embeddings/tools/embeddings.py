import os

from utils.client import client


def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        input=text,
    )
    return response.data[0].embedding
