def create_index(dimension: int) -> dict:
    if not isinstance(dimension, int) or dimension < 1:
        raise ValueError("embedding dimension must be positive")
    return {"dimension": dimension, "vectors": []}


def add_vector(index: dict, vector: list[float]) -> int:
    if len(vector) != index["dimension"]:
        raise ValueError("embedding dimension changed")
    index["vectors"].append(list(vector))
    return len(index["vectors"]) - 1


def search_vectors(index: dict, query_vector: list[float], k: int = 1):
    if not isinstance(k, int) or k < 1:
        raise ValueError("k must be positive")
    if len(query_vector) != index["dimension"]:
        raise ValueError("query embedding has the wrong dimension")
    ranked = sorted(
        (
            sum((left - right) ** 2 for left, right in zip(query_vector, vector)),
            position,
        )
        for position, vector in enumerate(index["vectors"])
    )[:k]
    return [position for _distance, position in ranked], [
        distance for distance, _position in ranked
    ]
