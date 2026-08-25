---
description: Add a real decision to a graph with one ordinary path and explicit named routes.
---

# Links and Routing

Your first release always published. Real workflows have moments where the next
step depends on what just happened. This is where a graph starts paying for
itself: the decision lives in one node, while every allowed outcome is visible
in its links.

We will keep the preparation step and route low-risk releases to publishing and
high-risk releases to review.

{% tabs %}
{% tab title="Python" %}

```python
import asyncio

from sley import Flow, node


@node
def prepare(context):
    context.state["slug"] = context.state["title"].strip().lower().replace(" ", "-")


@node
def decide(context):
    action = "needs_review" if context.state["risk"] == "high" else "ready"
    context.emit(action)


@node
def publish(context):
    context.state["status"] = f"published: {context.state['slug']}"


@node
def review(context):
    context.state["status"] = f"review: {context.state['slug']}"


prepare.link(decide)
decide.link(publish, "ready")
decide.link(review, "needs_review")
release = Flow(prepare)


async def main():
    for risk in ("low", "high"):
        state = await release.run({"title": "Hello Sley", "risk": risk})
        print(f"{risk}: {state['status']}")


asyncio.run(main())
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { Flow, node } from '@jigging/sley'

interface State {
  title: string
  risk: 'low' | 'high'
  slug?: string
  status?: string
}

const prepare = node<State>((context) => {
  context.state.slug = context.state.title.trim().toLowerCase().replaceAll(' ', '-')
})

const decide = node<State>((context) => {
  const action = context.state.risk === 'high' ? 'needs_review' : 'ready'
  context.emit(action)
})

const publish = node<State>((context) => {
  context.state.status = `published: ${context.state.slug}`
})

const review = node<State>((context) => {
  context.state.status = `review: ${context.state.slug}`
})

prepare.link(decide)
decide.link(publish, 'ready')
decide.link(review, 'needs_review')
const release = new Flow(prepare)

for (const risk of ['low', 'high'] as const) {
  const state = await release.run({ title: 'Hello Sley', risk })
  console.log(`${risk}: ${state.status}`)
}
```

{% endtab %}
{% endtabs %}

The output is:

```text
low: published: hello-sley
high: review: hello-sley
```

## The quiet path is unlabelled

`prepare` makes no control call. A successful node handler with zero control
calls behaves like one implicit `emit()`, so Sley follows the unlabelled link to
`decide`.

If a node has no unlabelled link, the same continuation leaves its current Flow
normally. That is how `publish` and `review` finish. Ordinary leaves stay
ordinary; neither needs `end()`.

The string `"default"` has no special meaning. It is a normal action label and
is different from the unlabelled path.

## Named routes expose decisions

`decide` emits the outcome `ready` or `needs_review`. Sley resolves that action
against the node's links. If no matching link or declared Flow exit exists, the
run fails with `unknown_action`. A misspelled decision never disappears and
never guesses a destination.

Name actions after what the decision means, not after the current target. A
route named `needs_review` can later lead to a queue, notification, or nested
approval Flow without changing the decision itself.

## The graph-design lesson

A decision node should answer one domain question. Its links should enumerate
the allowed answers. When one node both decides and performs every outcome, the
topology becomes invisible again inside its body.

Links may point backward or to the same node, so the same mechanism can express
a loop. A deliberate cycle needs an exit and an activation guard; the
[Concurrency and cycles](../guides/concurrency-and-cycles.md) guide builds one
when you need it.

## Change one thing

Add a third risk named `blocked`, a `reject` node, and a `rejected` action. Make
the `blocked` risk emit `rejected`. Before running the code, check that the
decision node has exactly three possible answers and that each answer has one
link.

The graph can now choose where work goes. Next, [State and input](data.md) makes
the data carried by each choice just as explicit as its destination.
