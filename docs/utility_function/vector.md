# Vector Search

Vector indexes are application services. Sley coordinates when they are
built or queried; it does not prescribe an index product or storage model.

## Define a Small Interface

```python
from typing import Protocol


class VectorIndex(Protocol):
    def add(self, item_id: str, vector: list[float], text: str) -> None: ...
    def search(self, vector: list[float], limit: int) -> list[str]: ...
```

```typescript
interface VectorIndex {
  add(itemId: string, vector: readonly number[], text: string): Promise<void>
  search(vector: readonly number[], limit: number): Promise<readonly string[]>
}
```

The implementation may be in memory, a database, or a remote service. Tests can
use a deterministic in-memory fake with the same interface.

## Keep Index Ownership Explicit

An index object is usually a borrowed nested value or injected service, not
portable state data. Decide whether it lives:

- outside the run as an injected dependency;
- inside a nested state binding for one process;
- behind an ID that refers to durable storage.

The run's top-level state is shallow-copied, so a nested index object remains the
same reference. Concurrent callbacks using it must follow that implementation's
thread-safety and consistency rules.

## Separate Offline and Online Work

A common RAG design has two Flows:

1. build or update the index from documents;
2. embed a query, search the index, and generate an answer.

Compose them under one root Flow when they are one invocation. When they are
separate runs, pass the state returned by the first run into the second.

Validate vector dimension and index configuration at the utility boundary. Put
remote-service timeouts and rate limits in the index client.
