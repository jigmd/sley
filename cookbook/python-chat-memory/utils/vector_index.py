import faiss
import numpy as np


def create_index(dimension=1536):
    return faiss.IndexFlatL2(dimension)


def add_vector(index, vector):
    vector = np.array(vector).reshape(1, -1).astype(np.float32)
    index.add(vector)
    return index.ntotal - 1


def search_vectors(index, query_vector, k=1):
    k = min(k, index.ntotal)
    if k == 0:
        return [], []

    query_vector = np.array(query_vector).reshape(1, -1).astype(np.float32)
    distances, indices = index.search(query_vector, k)
    return indices[0].tolist(), distances[0].tolist()
