---
machine-display: false
---

# Embeddings

An embedding utility converts application text into a numeric vector. Keep the
provider-specific request outside graph code:

```python
from typing import Protocol


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...
```

```typescript
interface Embedder {
  embed(text: string): Promise<readonly number[]>
}
```

## Use Branch Input for Batch Work

```python
def dispatch(context):
    for document in context.state["documents"]:
        context.emit("embed", document)


async def embed_document(context):
    vector = await embedder.embed(context.input)
    context.end({"document": context.input, "vector": vector})


def collect(context, result):
    context.state["embeddings"] = list(result.outputs)
```

The Flow controls concurrency. The embedder owns provider batching, request
limits, model configuration, and response validation.

## Preserve the Vector Contract

Record these application invariants near the index that consumes the vectors:

- embedding model or version;
- vector dimension;
- numeric representation;
- normalization and distance metric;
- document/chunk identity;
- behavior for empty input.

Do not mix vectors produced by incompatible models in one index. Validate
dimension before storage, and use a provider-side timeout for every request.

See the embedding, PDF vision, RAG, and map/reduce cookbook projects for complete
graph examples.
