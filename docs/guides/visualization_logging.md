---
machine-display: false
---

# Inspection and Logging

Sley exposes a static graph description and structured final results.
Application logging uses the host language's normal logging tools.

## Inspect a Compiled Graph

Compile once and inspect the portable description:

```python
compiled = flow.compile()
description = compiled.describe()

for element in description["elements"]:
    print(element["element_id"], element["kind"], element["name"])
```

```typescript
const compiled = flow.compile()
const description = compiled.describe()

for (const element of description.elements) {
  console.log(element.element_id, element.kind, element.name)
}
```

The description contains `elements`, `scopes`, links, entries, declared exits,
local concurrency, and activation limits. It is suitable input for a diagram
renderer or definition audit. `compiled.run()` and `compiled.start()` execute
that same snapshot even if the original graph objects are later changed.

## Log Application Facts

Log inside handlers or injected service clients when a domain action matters:

```python
import logging

logger = logging.getLogger("workflow")


async def index(context):
    documents = await client.index(context.input)
    logger.info("documents indexed", extra={"count": len(documents)})
    context.end(len(documents))
```

```typescript
const index = node(async (context) => {
  const documents = await client.index(context.input)
  logger.info({ count: documents.length }, 'documents indexed')
  context.end(documents.length)
})
```

Use state, input, or End output to transfer workflow data. Logs are observations,
not graph control or a data channel.

## Inspect a Full Result

Use `run()` when only final state matters. Use `start()` when the caller needs
terminal records or a structured failure:

```python
result = await flow.start(initial_state).result()

if result.status == "failed":
    logger.error("workflow failed", extra={"kind": result.failure.kind})
else:
    for terminal in result.terminals:
        logger.info("branch settled", extra={"type": terminal.type})
```

```typescript
const result = await flow.start(initialState).result()

if (result.status === 'failed') {
  logger.error({ kind: result.failure.kind }, 'workflow failed')
} else {
  for (const terminal of result.terminals) {
    logger.info({ type: terminal.type }, 'branch settled')
  }
}
```

Terminal records distinguish End from Flow exit, preserve output presence and
value, and identify the source activation. A Flow combiner receives the same
boundary information through `ScopeResult.terminals`.
