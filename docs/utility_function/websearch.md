---
machine-display: false
---

# Web Search

Keep search provider details behind an application interface:

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearch(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]: ...
```

```typescript
interface SearchResult {
  readonly title: string
  readonly url: string
  readonly snippet: string
}

interface WebSearch {
  search(query: string, limit?: number): Promise<readonly SearchResult[]>
}
```

Normalize provider responses at this boundary. Downstream nodes should not need
to know whether results came from a hosted API, a local index, or a test fake.

## Graph Integration

```python
async def search(context):
    results = await web_search.search(context.input, limit=5)
    context.emit("decide", results)


async def decide(context):
    # context.input is a normalized list[SearchResult].
    ...
```

Search agents commonly use a named loop: a decision node emits a query to the
search node, and the search node emits normalized results back to the decision
node. Bound that loop with a Flow activation cap, run work limits, or an
application decision budget.

## Operational Rules

- Set provider timeouts and a result limit.
- Validate URLs before later fetches.
- Treat snippets as untrusted external input.
- Respect provider quotas, terms, and attribution requirements.
- Cache only when freshness requirements permit it.
- Use deterministic result fixtures in Flow tests.

See the web-search, research-agent, supervisor, and crawler cookbook projects for
complete examples.
