---
description: Convert PocketFlow lifecycle nodes, shared data, actions, and batch work into Sley's function handlers and structured Flows.
---

# Migrate from PocketFlow

PocketFlow and Sley share a small graph idea, but not an authoring or execution
contract. Treat migration as a behavior conversion rather than an import rename.

## Translate the core model

| PocketFlow                    | Sley                                     |
| ----------------------------- | ---------------------------------------- |
| `Node` / `AsyncNode` subclass | Function wrapped with `node(...)`        |
| `prep` + `exec` + `post`      | One sync or async handler                |
| Shared store                  | `context.state`                          |
| Params                        | `context.input`                          |
| Action returned from `post`   | Buffered `context.emit(action)`          |
| `node >> target`              | `node.link(target)`                      |
| `node - "action" >> target`   | `node.link(target, "action")`            |
| Batch classes                 | Several `emit(...)` calls in one handler |
| Aggregation counters          | Flow `combine` callback                  |
| Shared mutation as result     | State returned by `run()`                |

## Collapse the lifecycle without losing its order

PocketFlow:

```python
class Summarize(AsyncNode):
    async def prep_async(self, shared):
        return shared["document"]

    async def exec_async(self, document):
        return await model.summarize(document)

    async def post_async(self, shared, document, summary):
        shared["summary"] = summary
        return "review"
```

Sley:

```python
@node
async def summarize(context):
    document = require_document(context.state)
    summary = await model.summarize(document)
    context.state["summary"] = summary
    context.emit("review")
```

The handler can be synchronous or asynchronous. Validate first. Sley retry
repeats this whole function, so place non-idempotent effects deliberately.

## Choose state or input for each value

State is one mapping shared by every branch in the run. Input belongs to the
current branch:

```python
def dispatch(context):
    for chunk in context.state["chunks"]:
        context.emit("summarize", chunk)


async def summarize_chunk(context):
    context.end(await model.summarize(context.input))
```

Sley shallow-copies only the caller's top-level initial mapping. Nested values
remain shared references. Static types describe payloads but do not validate
them or prove agreement across links.

## Replace returned actions with buffered control

```python
decide.link(search, "search")
decide.link(answer, "answer")
```

Inside the handler:

```python
context.emit("search", query)
```

One successful handler may buffer zero, one, or many routes. The complete buffer
commits after the handler returns successfully. A throw discards those routes,
but not state writes or external effects.

A successful handler with no control call follows its unlabelled link. Without
one, it exits the current Flow. Most leaf nodes therefore need no `end()`.

## Replace batch classes with a scoped join

Use ordinary emissions for fan-out, `end(value)` to publish branch results, and
a Flow combiner for fan-in:

```python
def collect(context, result):
    context.state["summary"] = "\n".join(result.outputs)


dispatch_node = node(dispatch)
worker_node = node(summarize_chunk)
dispatch_node.link(worker_node, "summarize")

flow = Flow(dispatch_node, concurrency=4, combine=collect)
```

The combiner runs after every branch in its Flow settles. It receives terminal
outputs in settlement order, which may differ from dispatch order under
concurrency. Carry an index and sort when source order matters.

Handle an empty source explicitly when it must not take the ordinary unlabelled
path.

## Convert completion and failure handling

- Use `run()` for final state; it raises `RunError` on workflow failure.
- Use `start().result()` when the caller needs `Completed`, `Failed`, terminals,
  or structured failure data.
- Use node retry/recovery for local handler failure.
- Use Flow recovery when a child scope fails and settled sibling terminals
  matter.
- Use Flow-local `concurrency` for parallelism and `max_activations` for an
  execution bound.

## Migration checklist

1. Extract service and domain calls from lifecycle methods.
2. Reassemble their required order in one handler.
3. Decide whether each value is shared state or branch input.
4. Convert default and named edges to target-first links.
5. Convert batch classes and counters to fan-out plus combine.
6. Recheck retry side effects, empty fan-out, and concurrent ordering.
7. Assert the state returned by `run()` and inspect failure paths through
   `start()`.

Continue with [Links and routing](../learn/routing.md) to see the Sley control
model without migration terminology.
