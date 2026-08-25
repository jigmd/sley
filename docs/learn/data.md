---
description: Decide whether a value belongs to the whole run, one branch, or a completed branch result.
---

# State and Input

The release graph now chooses between publishing and review, but both routes
still reach into shared state for everything. That becomes confusing as soon as
each path needs its own instruction.

We will keep the graph from the routing lesson and add only branch payloads.
The title, slug, and risk remain facts about the whole run. A publishing channel
or review request belongs to the branch that receives it.

| Data            | Use it for                                    |
| --------------- | --------------------------------------------- |
| `context.state` | Facts shared for the life of one run          |
| `context.input` | The message carried by this particular branch |

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
    if context.state["risk"] == "high":
        context.emit(
            "needs_review",
            {"owner": "release team", "reason": "risk is high"},
        )
    else:
        context.emit("ready", {"channel": "stable"})


@node
def review(context):
    request = context.input
    context.state["status"] = (
        f"{context.state['slug']}: {request['owner']} reviews because {request['reason']}"
    )


@node
def publish(context):
    context.state["status"] = (
        f"published: {context.state['slug']} to {context.input['channel']}"
    )


prepare.link(decide)
decide.link(review, "needs_review")
decide.link(publish, "ready")
release = Flow(prepare)

state = asyncio.run(release.run({"title": "Hello Sley", "risk": "high"}))
print(state["status"])
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

interface ReviewRequest {
  owner: string
  reason: string
}

interface PublishTarget {
  channel: string
}

const prepare = node<State>((context) => {
  context.state.slug = context.state.title.trim().toLowerCase().replaceAll(' ', '-')
})

const decide = node<State>((context) => {
  if (context.state.risk === 'high') {
    context.emit('needs_review', { owner: 'release team', reason: 'risk is high' })
  } else {
    context.emit('ready', { channel: 'stable' })
  }
})

const review = node<State, ReviewRequest>((context) => {
  const request = context.input
  context.state.status = `${context.state.slug}: ${request.owner} reviews because ${request.reason}`
})

const publish = node<State, PublishTarget>((context) => {
  context.state.status = `published: ${context.state.slug} to ${context.input.channel}`
})

prepare.link(decide)
decide.link(review, 'needs_review')
decide.link(publish, 'ready')
const release = new Flow(prepare)

const state = await release.run({ title: 'Hello Sley', risk: 'high' })
console.log(state.status)
```

{% endtab %}
{% endtabs %}

Both programs print:

```text
hello-sley: release team reviews because risk is high
```

Only the `emit(...)` calls and the receiving handlers changed. The topology is
still `prepare -> decide -> publish or review`, and the slug created in the
first lesson still matters at the end.

## State is the run's shared notebook

Sley shallow-copies the initial top-level mapping or object once. Every branch
and nested Flow in that run shares the copied state, and `run()` returns it. The
caller's top-level value is not mutated.

Nested objects are not copied. A list, client, cache, or object placed in the
initial state remains the same reference. Concurrent branches therefore need
the same coordination as ordinary concurrent code.

Use state for facts that unrelated later steps need: the release title, slug,
risk, policy, final status, or an injected service.

## Input is one branch's message

`emit("needs_review", request)` binds `request` to `context.input` in the next
activation. Another branch can carry a completely different value. Omitting a
replacement input forwards the current input unchanged.

Use input for the item or instruction this branch is processing. That choice
keeps fan-out honest: several workers may share policy in state while each
receives its own check, document, or request as input.

## Sley preserves data; your application validates it

Types make one handler's expectation visible, but Sley does not prove that
linked nodes agree on payload shape. Python keeps normal `KeyError` behavior for
a missing key. TypeScript keeps normal `undefined` behavior for a missing
property.

Validate untrusted values before state writes, external effects, or graph
control. This is not a gap to hide with magic data wrappers; it is an
application boundary to make deliberate.

## Change one thing

Run the example with low risk. Predict which input shape reaches `publish` and
which values remain available to both routes through state. Then move `slug`
into branch input and decide whether the graph became clearer or merely more
repetitive.

You can now give each path its own message without losing shared release facts.
[Fan-out, End, and combine](fan-out-and-combine.md) uses that same idea several
times at once, then rejoins the work without a shared counter.
