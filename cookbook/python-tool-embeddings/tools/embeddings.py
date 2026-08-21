from utils.client import client


def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(model="text-embedding-ada-002", input=text)
    return response.data[0].embedding
