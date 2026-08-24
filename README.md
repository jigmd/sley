# Sley

A structured graph runtime for Python and TypeScript.

Sley is a fork of Caskada. It keeps that history visible while taking the graph
runtime forward under its own package and project identity.

<p align="center">
  <a href="https://pypi.org/project/sley"><img src="https://img.shields.io/pypi/v/sley?logo=python&label=Python&style=flat-square" alt="Python package"></a>
  <a href="https://www.npmjs.com/package/sley"><img src="https://img.shields.io/npm/v/sley?logo=typescript&label=TypeScript&style=flat-square" alt="TypeScript package"></a>
  <a href="https://github.com/jigmd/sley"><img src="https://img.shields.io/github/stars/jigmd/sley?logo=github&style=flat-square" alt="GitHub stars"></a>
</p>

Sley runs ordinary functions as nodes in nested directed graphs. It provides
explicit branching, structured fan-out and joining, retries, recovery, local
concurrency, and typed execution results without depending on an LLM provider
or application framework.

## Why Sley

A sley is the moving loom frame that carries the reed, keeps warp threads
separated, and advances the fabric. To sley also means threading the warp in a
prescribed pattern. The analogy is direct: the graph defines the pattern,
branches and state are the threads, Sley executes their arrangement, and a
completed run is the woven result.

## Install

```bash
pip install sley
```

```bash
npm install sley
```

Python 3.13 or newer is required. The TypeScript package ships ESM and CommonJS
builds.

## Python

```python
import asyncio

from sley import Flow, node


@node
def normalize(context):
    context.state["question"] = context.state["question"].strip()


@node
def answer(context):
    context.state["answer"] = f"You asked: {context.state['question']}"


normalize.link(answer)


async def main() -> None:
    state = await Flow(normalize).run({"question": "  Why?  "})
    print(state["answer"])


asyncio.run(main())
```

## TypeScript

```typescript
import { Flow, node } from 'sley'

interface State {
  question: string
  answer?: string
}

const normalize = node<State>((context) => {
  context.state.question = context.state.question.trim()
})

const answer = node<State>((context) => {
  context.state.answer = `You asked: ${context.state.question}`
})

normalize.link(answer)

const state = await new Flow(normalize).run({ question: '  Why?  ' })
console.log(state.answer)
```

Both programs print `You asked: Why?`.

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

Several control calls create a buffered fan-out. Sley commits that buffer only
after the handler returns normally; state writes and external effects are not
rolled back.

### Data

`context.state` is the one mutable top-level map shared by every branch in one
run. Sley shallow-copies the caller's initial mapping once, so `run()` returns
the authoritative final state and does not mutate the caller's top-level map.
Nested values remain shared references.

`context.input` is the value carried by one branch. Omitted input forwards the
current input. Sley preserves application values but does not validate their
schema or prove payload compatibility between links.

### Flows And Combine

A `Flow` is a structured scope. It waits until all of its branches settle, then
optionally invokes one `combine` callback.

```python
def combine(context, result):
    context.state["total"] = sum(result.outputs)


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

- [Website](https://sley.jig.md)
- [Quickstart](https://github.com/jigmd/sley/blob/main/docs/quickstart.md)
- [Core model](https://github.com/jigmd/sley/blob/main/docs/learn/core-model.md)
- [Cookbook](https://github.com/jigmd/sley/tree/main/cookbook)
- [Migration from Caskada](https://github.com/jigmd/sley/blob/main/docs/about/migrate-from-caskada.md)
- [Normative runtime contract](https://github.com/jigmd/sley/blob/main/architecture/rfcs/0001-sley-runtime.md)

## License

Sley is licensed under the Mozilla Public License 2.0.
