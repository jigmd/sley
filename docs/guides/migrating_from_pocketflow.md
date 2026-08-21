---
machine-display: false
---

# Migrating from PocketFlow

Modern Caskada uses the same small-graph idea but not PocketFlow's node
lifecycle or shared-dictionary control conventions. Treat migration as an
authoring-model conversion, not an import rename.

## Concept Map

| PocketFlow                    | Caskada v3                                    |
| ----------------------------- | --------------------------------------------- |
| `Node` / `AsyncNode` subclass | function wrapped with `node(...)`             |
| `prep` + `exec` + `post`      | one sync or async handler                     |
| shared store                  | `context.state`                               |
| params                        | `context.input`                               |
| action returned from `post`   | buffered `context.emit(action)`               |
| `node >> next_node`           | `node.link(next_node)`                        |
| `node - "action" >> target`   | `node.link(target, "action")`                 |
| Batch classes                 | several `emit(...)` calls in a normal handler |
| shared aggregation counters   | Flow `combine` callback                       |
| flow return/shared mutation   | state returned by `run()`                     |

## Convert the Lifecycle

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

Caskada:

```python
@node
async def summarize(context):
    document = require_document(context.state)
    summary = await model.summarize(document)
    context.state["summary"] = summary
    context.emit("review")
```

The handler may be synchronous or asynchronous. Validate before effects and
state writes. If retry is configured, Caskada retries the complete handler.

## Convert Data Passing

State is shared by every branch in one run. Input is specific to the current
branch:

```python
def dispatch(context):
    for chunk in context.state["chunks"]:
        context.emit("summarize", chunk)


async def summarize_chunk(context):
    context.end(await model.summarize(context.input))
```

Caskada shallow-copies the caller's top-level initial state and returns the
run-owned state when execution completes. Nested objects are still borrowed.

## Convert Batch Work

Use ordinary emissions for fan-out and a Flow combine callback for fan-in:

```python
def collect(context, result):
    context.state["summary"] = "\n".join(result.outputs)


dispatch_node = node(dispatch)
worker_node = node(summarize_chunk)
dispatch_node.link(worker_node, "summarize")

flow = Flow(dispatch_node, concurrency=4, combine=collect)
```

`end(value)` finishes one worker branch and contributes the value to
`result.outputs`. It does not end sibling branches. A combine callback with zero
emissions forwards the original terminals; emitting replaces them.

Handle an empty source explicitly if it should not take the ordinary unlabelled
route.

## Convert Flow Completion

A normal handler with no emission follows its unlabelled link. Without such a
link it exits the current Flow, so most leaf nodes need no termination call.

Use `end()` only for a deliberate hard terminal. Use declared Flow exits for
named outcomes that a parent graph may handle.

## Convert Execution and Failures

```python
final_state = await flow.run(initial_state)
```

`run()` returns final state and raises `RunError` for failed execution. Use
`start()` when the caller needs the complete structured result.

Use node retry/recovery for local failures and Flow recovery for a failed child
scope. Use Flow `concurrency` and `max_activations` for local scheduling bounds.

## Migration Order

1. Extract domain and service logic from PocketFlow lifecycle methods.
2. Build one function handler around that logic.
3. Decide whether each value belongs in shared state or branch input.
4. Convert default and named edges to target-first links.
5. Convert batch counters to Flow combine where synchronization is required.
6. Recheck retry side effects and empty fan-out behavior.
7. Assert the state returned by `run()` and inspect failure paths through
   `start()`.
