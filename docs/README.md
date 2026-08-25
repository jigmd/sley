---
description: Turn tangled workflow control flow into a small, explicit graph of ordinary Python or TypeScript functions.
---

# Sley

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark-reverse.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark.svg">
    <img width="320" alt="Sley" src="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark.svg">
  </picture>
</p>

## Complex workflows. Obvious code.

Sley turns tangled workflow logic into code your team can scan and change with
confidence. Every possible path stays visible, the final state comes back
directly, and your application remains ordinary Python or TypeScript.

You have probably watched a clean sequence grow into nested conditions,
callbacks, counters, and fallback logic. The work is still understandable. Its
shape is not. Sley puts that shape back where you can see it.

Write ordinary functions, connect the paths they may take, and run the graph.
Branching, fan-out, joins, retries, and nested workflows stay visible without
handing your application to a framework.

## Example: a release with two outcomes

The following program is a complete Sley graph. Low-risk work publishes now;
high-risk work waits for review. Both allowed paths sit side by side, and the
caller gets the resulting status directly.

{% tabs %}
{% tab title="Python" %}

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

{% endtab %}
{% tab title="TypeScript" %}

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

{% endtab %}
{% endtabs %}

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

That small model is the point. Sley owns in-process graph execution. Your code
keeps validation, storage, services, UI, and every domain decision.

Use Sley when branching and synchronization have made a workflow's shape hard
to see. Keep ordinary calls, conditions, loops, `asyncio.gather`, or
`Promise.all` while they still explain the workflow clearly.

## Learn to think in graphs

These docs do more than teach method names. You will begin with no graph-runtime
vocabulary and finish able to:

- choose node boundaries that keep work readable;
- model decisions, loops, fan-out, and fan-in without hiding control;
- decide what belongs in shared state, branch input, and terminal output;
- place scope, concurrency, retry, and recovery boundaries deliberately;
- recognise graph designs that are doing too much;
- test and explain a workflow from its observable behavior.

The judgment transfers beyond Sley. The examples simply give you a small,
runnable place to build it.

## Start with one file

```bash
pip install sley
```

```bash
npm install @jigging/sley
```

The [Quickstart](quickstart.md) takes one file from installation to a completed
run with visible output. No service, account, API key, or application framework
is required.
