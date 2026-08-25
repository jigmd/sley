---
description: Convert PocketFlow lifecycle nodes, shared data, actions, and batch work into Sley's function handlers and structured Flows.
---

# Migrate from PocketFlow

The familiar graph shape survives this migration; the lifecycle around it does
not. Move one behavior at a time so a simpler handler does not quietly change
validation, side effects, or routing.

PocketFlow and Sley share a small graph idea, but not an authoring or execution
contract. Treat migration as a behavior conversion rather than an import rename.

## Translate the core model

| PocketFlow                              | Sley                                             |
| --------------------------------------- | ------------------------------------------------ |
| `Node` / `AsyncNode` subclass           | Function wrapped with `node(...)`                |
| `prep` + `exec` + `post`                | One sync or async handler                        |
| Shared store                            | `context.state`                                  |
| Params                                  | Closure, state, or branch input; no direct match |
| Action returned from `post`             | Buffered `context.emit(action)`                  |
| `node >> target`                        | `node.link(target)`                              |
| `node - "action" >> target`             | `node.link(target, "action")`                    |
| `BatchNode.post(..., exec_res_list)`    | Flow `combine(context, result)`                  |
| `BatchFlow` replay with per-item Params | Branch inputs sent to a nested Flow              |
| Shared mutation as result               | State returned by `run()`                        |

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

## Replace Params by ownership, not by name

PocketFlow Params are inherited and merged configuration for a Node or Flow,
often used to identify one item in a BatchFlow. Sley does not merge a parameter
context across graph elements.

Choose the destination by what the value means:

- close over stable service or policy configuration;
- put facts needed across the whole run in state;
- carry one batch item or instruction as branch input.

A batch item from PocketFlow Params often becomes `context.input`, but mapping
every Params dictionary there would turn shared configuration into repeated
messages.

## Choose state or input for application data

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

## Replace each batch model deliberately

PocketFlow `BatchNode` runs `exec` for every item returned by `prep`, then gives
the complete `exec_res_list` to `post`. In Sley, use emissions for those items,
`end(value)` for worker results, and a Flow combiner for the corresponding
fan-in:

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

PocketFlow `BatchFlow` instead reruns a child Flow with different Params. In
Sley, emit one branch input to a nested Flow for each item. Add a combiner only
when the parent must join those Flow results; fan-out alone is enough when each
branch may leave independently.

Handle an empty source explicitly when it must not take the ordinary unlabelled
path.

## Convert retry and fallback

PocketFlow `max_retries` and Sley `max_attempts` both count total executions,
including the first. PocketFlow `wait` is measured in seconds; Sley `delay_ms`
uses milliseconds:

```python
fetch = node(
    fetch_handler,
    retry=RetryPolicy(max_attempts=3, delay_ms=1_000),
    recover=recover_fetch,
)
```

PocketFlow `exec_fallback(prep_res, exc)` returns a replacement `exec` result
that continues into `post`. Sley Node recovery receives `(context, failure)` and
must use `emit(...)` or `end(...)` to replace the failure. Returning an
application value is invalid. With no recovery control call, the original
failure propagates.

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
5. Convert BatchNode aggregation to fan-out plus combine where needed.
6. Convert BatchFlow Params to explicit inputs for a nested Flow.
7. Recheck retry counts, delay units, side effects, empty fan-out, and ordering.
8. Assert the state returned by `run()` and inspect failure paths through
   `start()`.

Continue with [Links and routing](../learn/routing.md) to see the Sley control
model without migration terminology.
