---
machine-display: true
---

# Utility Functions

Sley schedules application work but does not wrap model providers,
databases, search APIs, or media services. Use their SDKs through ordinary
functions or small client objects.

## Guides

- [LLM Calls](./llm.md)
- [Web Search](./websearch.md)
- [Text Chunking](./chunking.md)
- [Embeddings](./embedding.md)
- [Vector Search](./vector.md)
- [Text to Speech](./text_to_speech.md)

## Why Utilities Stay Outside Core

Provider APIs and deployment choices change independently of workflow
semantics. Keeping integrations in application code provides:

- direct access to the provider's current features and error types;
- straightforward service fakes in tests;
- provider replacement without changing graph control;
- explicit ownership of timeouts, rate limits, and credentials.

## A Useful Boundary

A utility should have a small domain-oriented interface:

```python
async def generate_answer(question: str, sources: list[str]) -> str: ...
```

```typescript
async function generateAnswer(question: string, sources: string[]): Promise<string>
```

The function owns provider request shape. The Sley handler owns when it is
called, where its result goes, and which graph route follows.

Keep utility fakes in tests. Avoid placing provider response objects in shared
state when a smaller application value will do.
