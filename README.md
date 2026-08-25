<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark-reverse.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark.svg">
    <img width="360" alt="Sley" src="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark.svg">
  </picture>
</p>

<p align="center"><strong>Complex workflows. Obvious code.</strong></p>

<p align="center">
  <a href="https://pypi.org/project/sley"><img src="https://img.shields.io/pypi/v/sley?logo=python&label=Python&style=flat-square" alt="Python package"></a>
  <a href="https://www.npmjs.com/package/@jigging/sley"><img src="https://img.shields.io/npm/v/%40jigging%2Fsley?logo=typescript&label=TypeScript&style=flat-square" alt="TypeScript package"></a>
  <a href="https://github.com/jigmd/sley"><img src="https://img.shields.io/github/stars/jigmd/sley?logo=github&style=flat-square" alt="GitHub stars"></a>
</p>

Sley turns tangled workflow logic into code your team can scan and change with
confidence. Every possible path stays visible, the final state comes back
directly, and your application remains ordinary Python or TypeScript.

Write ordinary functions, connect the paths they may take, and run the graph.
Branching, fan-out, joins, retries, and nested workflows stay visible without
handing your application to a framework.

## Example: a release with two outcomes

The following program is a complete Sley graph. Low-risk work publishes now;
high-risk work waits for review. Both allowed paths sit side by side, and the
caller gets the resulting status directly.

### Python

```python
import asyncio

from sley import Flow, node


@node
def decide(context):
    action = "needs_review" if context.state["risk"] == "high" else "ready"
    context.emit(action)


@node
def publish(context):
    context.state["status"] = "published"


@node
def review(context):
    context.state["status"] = "waiting for review"


decide.link(publish, "ready")
decide.link(review, "needs_review")
release = Flow(decide)

for risk in ("low", "high"):
    state = asyncio.run(release.run({"risk": risk}))
    print(f"{risk}: {state['status']}")
```

### TypeScript

```typescript
import { Flow, node } from '@jigging/sley'

interface State {
  risk: 'low' | 'high'
  status?: string
}

const decide = node<State>((context) => {
  const action = context.state.risk === 'high' ? 'needs_review' : 'ready'
  context.emit(action)
})

const publish = node<State>((context) => {
  context.state.status = 'published'
})

const review = node<State>((context) => {
  context.state.status = 'waiting for review'
})

decide.link(publish, 'ready')
decide.link(review, 'needs_review')
const release = new Flow(decide)

for (const risk of ['low', 'high'] as const) {
  const state = await release.run({ risk })
  console.log(`${risk}: ${state.status}`)
}
```

Both programs print:

```text
low: published
high: waiting for review
```

The decision stays inside `decide`; the allowed outcomes stay in its two links;
the caller gets the final status from `run()`. No hidden handoff or terminal
lookup is required.

## Small by design

- A **node** is one ordinary synchronous or asynchronous function.
- A **link** makes one allowed next step visible.
- `emit()` chooses one or more paths.
- A **Flow** waits for those paths and `run()` returns their final shared state.

Use Sley when branching and synchronization have made a workflow's shape hard
to see. Keep ordinary calls, conditions, loops, `asyncio.gather`, or
`Promise.all` while they still explain the workflow clearly.

## Install

```bash
pip install sley
```

```bash
npm install @jigging/sley
```

Python requires version 3.13 or newer. Package and runtime details live in the
[Python](https://sley.jig.md/reference/python) and
[TypeScript](https://sley.jig.md/reference/typescript) references.

## Start learning

The [Quickstart](https://sley.jig.md/quickstart) takes one file from installation
to visible output. The Learn path then evolves that same release workflow from a
linear graph through routing, branch data, fan-out, joins, nested boundaries,
failure evidence, and advanced graph design.

- [Documentation](https://sley.jig.md)
- [Quickstart](https://sley.jig.md/quickstart)
- [Core model](https://sley.jig.md/learn/core-model)
- [Example projects](https://sley.jig.md/examples)
- [Migration from Caskada](https://sley.jig.md/about/migrate-from-caskada)
- [Runtime semantics](https://sley.jig.md/reference/runtime-semantics)

Sley evolved through PocketFlow and Caskada. The
[lineage](https://sley.jig.md/about/lineage) records what changed and which
tradeoffs remain intentional.

## License

Sley is licensed under the Mozilla Public License 2.0.
