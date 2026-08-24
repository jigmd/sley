import os

import numpy as np
from openai import OpenAI


def get_embedding(text):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY"))

    response = client.embeddings.create(model="text-embedding-ada-002", input=text)
    return np.array(response.data[0].embedding, dtype=np.float32)
