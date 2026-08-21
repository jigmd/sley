<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://cdn.jsdelivr.net/gh/skadaai/caskada@main/.github/media/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="https://cdn.jsdelivr.net/gh/skadaai/caskada@main/.github/media/logo-light.png">
    <img width="280" alt="Caskada" src="https://cdn.jsdelivr.net/gh/skadaai/caskada@main/.github/media/logo-light.png">
  </picture>
</p>

<p align="center">
  A structured workflow runtime for Python and TypeScript.
</p>

<p align="center">
  <a href="https://pypi.org/project/caskada"><img src="https://img.shields.io/pypi/v/caskada?logo=python&label=Python&style=flat-square" alt="Python package"></a>
  <a href="https://www.npmjs.com/package/caskada"><img src="https://img.shields.io/npm/v/caskada?logo=typescript&label=TypeScript&style=flat-square" alt="TypeScript package"></a>
  <a href="https://github.com/skadaai/caskada"><img src="https://img.shields.io/github/stars/skadaai/caskada?logo=github&style=flat-square" alt="GitHub stars"></a>
</p>

Caskada runs ordinary functions as nodes in nested directed graphs. It provides
explicit branching, structured fan-out and joining, retries, recovery, local
concurrency, and typed execution results without depending on an LLM provider
or application framework.

## Install

```bash
pip install caskada
```

```bash
npm install caskada
```

Python 3.13 or newer is required. The TypeScript package ships ESM and CommonJS
builds.

## Python

```python
import asyncio

from caskada import Context, Flow, node


@node
async def answer(context: Context) -> None:
    question = context.state["question"]
    context.state["answer"] = await model.answer(question)


async def main() -> None:
    state = await Flow(answer).run({"question": "Why?"})
    print(state["answer"])


asyncio.run(main())
```

## TypeScript

```typescript
import { Flow, node } from 'caskada'

interface State {
  question: string
  answer?: string
}

const answer = node<State>(async (context) => {
  context.state.answer = await model.answer(context.state.question)
})

const state = await new Flow(answer).run({ question: 'Why?' })
console.log(state.answer)
```

## Core Model

### Nodes

`node(handler)` turns a function into one graph occurrence. A handler receives
one `Context` and returns no application value.

```python
@node
def decide(context):
    if needs_review(context.state):
        context.emit("review")
```

Nodes connect target first:

```python
decide.link(review, "review")
decide.link(publish)  # unlabelled link
```

The equivalent TypeScript spelling is identical:

```typescript
decide.link(review, 'review')
decide.link(publish)
```

### Control

- `context.emit()` selects the unlabelled link.
- `context.emit("review")` selects a named link.
- `context.emit("work", item)` also supplies the next branch's
  `context.input`.
- A successful normal handler with no control call behaves like one implicit
  `emit()`.
- `context.end(value)` creates a hard terminal for the current branch and
  bypasses links. It does not stop the handler function, so use a normal
  `return` when later statements should not run.

Several `emit()` or `end()` calls in one handler create an atomic fan-out.

### Data

`context.state` is the one mutable top-level map shared by every branch in one
run. Caskada shallow-copies the caller's initial mapping once, so `run()` returns
the authoritative final state and does not mutate the caller's top-level map.
Nested values remain shared references.

`context.input` is the value carried by one branch. Omitted input forwards the
current input. Caskada preserves application values but does not validate their
schema or prove payload compatibility between links.

### Flows And Combine

A `Flow` is a structured scope. It waits until all of its branches settle, then
optionally invokes one `combine` callback.

```python
def combine(context, result):
    context.state["total"] = sum(result.outputs)
    context.emit()


batch = Flow(dispatch, combine=combine, concurrency=8)
```

Worker branches publish values with `context.end(value)`. The combiner reads
those values through `result.outputs`. Zero combiner emissions preserve the
original terminals; one or more emissions replace them with new outward
continuations.

### Results

`await flow.run(initial_state)` is the simple API. It returns the final state for
every completed run and raises `RunError` on failure. The error retains the
failed result and exposes a controlling application error through standard
native exception chaining.

`flow.start(initial_state)` returns a `RunHandle` whose `result()` method exposes
the completed or failed result, including state and settled terminals.

## Learn

- [Getting started](https://github.com/skadaai/caskada/blob/main/docs/getting_started.md)
- [Core concepts](https://github.com/skadaai/caskada/blob/main/docs/core_abstraction/index.md)
- [Cookbook](https://github.com/skadaai/caskada/tree/main/cookbook)
- [Migration from v2](https://github.com/skadaai/caskada/blob/main/docs/guides/migration.md)
- [Normative v3 runtime contract](https://github.com/skadaai/caskada/blob/main/internal/rfcs/0001-caskada-v3-runtime.md)

## License

Caskada is licensed under the Mozilla Public License 2.0.
