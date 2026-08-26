---
description: Build and run your first Sley graph in one file, then see exactly what made it a graph.
---

# Quickstart

Build the smallest useful Sley graph: prepare a release name, publish it, and
get `published: hello-sley` back. It runs in one file, with no service, account,
or graph theory between you and the result.

## Install Sley

{% tabs %}
{% tab title="Python" %}

Python 3.13 or newer is required.

```bash
python -m pip install sley
```

{% endtab %}
{% tab title="TypeScript" %}

```bash
npm install @jigging/sley
```

{% endtab %}
{% endtabs %}

## Build one path

The target is one final status: `published: hello-sley`. `prepare` turns the
title into a slug; `publish` records the result. One link makes that order
visible.

{% tabs %}
{% tab title="Python" %}

Create `quickstart.py`:

```python
import asyncio

from sley import Flow, node


@node
def prepare(context):
    title = context.state["title"].strip().lower()
    context.state["slug"] = title.replace(" ", "-")


@node
def publish(context):
    context.state["status"] = f"published: {context.state['slug']}"


prepare.link(publish)
release = Flow(prepare)


async def main():
    state = await release.run({"title": "  Hello Sley  "})
    print(state["status"])


asyncio.run(main())
```

Run it:

```bash
python quickstart.py
```

{% endtab %}
{% tab title="TypeScript" %}

Create `quickstart.mts`:

```typescript
import { Flow, node } from '@jigging/sley'

interface State {
  title: string
  slug?: string
  status?: string
}

const prepare = node<State>((context) => {
  context.state.slug = context.state.title.trim().toLowerCase().replaceAll(' ', '-')
})

const publish = node<State>((context) => {
  context.state.status = `published: ${context.state.slug}`
})

prepare.link(publish)
const release = new Flow(prepare)

const state = await release.run({ title: '  Hello Sley  ' })
console.log(state.status)
```

Run it:

Running an `.mts` file directly requires Node.js 24 or newer. On an earlier
version, use the TypeScript runner already configured by your project.

```bash
node quickstart.mts
```

{% endtab %}
{% endtabs %}

Both programs print:

```text
published: hello-sley
```

## What made this a graph?

The functions are familiar. Three lines give them graph behavior:

```text
prepare.link(publish)   allow one path from prepare to publish
Flow(prepare)           make prepare the entry point
release.run(state)      start the graph and wait for it to finish
```

`@node` / `node(...)` wraps each function as a graph node. When `prepare`
returns normally, Sley follows its unlabelled link to `publish`. The two nodes
share one run-owned state object, and `run()` returns that state after the Flow
settles.

`publish` has no outgoing link. Its normal return therefore leaves the Flow and
completes this run. A leaf does not need a special finish call.

## Change one thing

Change the title and predict the slug before you run the file again. Then add a
third node named `announce`, link `publish` to it, and have it write a message
to state.

That small exercise is the first graph-authoring habit: change topology and
application work separately, then predict the observable result.

You can now build and run a linear graph. The [Core model](https://sley.jig.md/learn/core-model)
gives names to the four ideas you just used, so adding a decision next will not
make the model feel larger than it is.
