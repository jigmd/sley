# Node

A Node is one configured occurrence of an ordinary handler function.

## Create A Node

{% tabs %}
{% tab title="Python" %}

```python
from caskada import Context, node


@node
async def fetch(context: Context) -> None:
    context.state["document"] = await client.fetch(context.state["url"])
```

`node(fetch_handler)` is the primitive form. `@node` and `@node(...)` are
decorator conveniences.

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { node } from 'caskada'

const fetch = node<State>(async (context) => {
  context.state.document = await client.fetch(context.state.url)
})
```

{% endtab %}
{% endtabs %}

Handlers return `None`/`undefined`. Application values travel through state,
branch input, or terminal output. Any other callback return value is an invalid
outcome.

`Node` itself is runtime-created and final. Subclass lifecycles are not part of
v3.

## Occurrences And Reuse

Calling `node(handler)` creates one occurrence with its own name, links, retry
policy, and recovery callback. To place the same behavior twice in one
graph, create two occurrences:

```python
primary = node(fetch_handler, name="primary fetch")
fallback = node(fetch_handler, name="fallback fetch")
```

A Python `@node` binding is already one occurrence. Put decoration inside a
graph factory, or keep the undecorated handler, when fresh topology is needed.

## Links

Links are directional and target first:

```python
source.link(default_target)
source.link(review_target, "review")
```

```typescript
source.link(defaultTarget)
source.link(reviewTarget, 'review')
```

One occurrence may have one unlabelled link and at most one link for each named
action. `link()` returns nothing. Graph compilation rejects invalid ownership,
duplicate placements, and recursive Flow containment.

## Normal Settlement

Control calls append intents to the callback-local buffer. They do not schedule
work immediately and do not stop the function.

- Zero intents from a normal handler synthesize one unlabelled continuation.
- One intent transfers the branch without a fan-out copy.
- Several intents form one ordered, atomic fan-out.
- A thrown error discards the whole buffer.

State writes are immediate and are not rolled back when a callback fails.

## Retry And Recovery

{% tabs %}
{% tab title="Python" %}

```python
from caskada import RetryPolicy, node

fetch = node(
    fetch_handler,
    retry=RetryPolicy(max_attempts=3, delay_ms=500),
    recover=fetch_recovery,
)
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
const fetch = node<State>(fetchHandler, {
  retry: { maxAttempts: 3, delayMs: 500 },
  recover: fetchRecovery,
})
```

{% endtab %}
{% endtabs %}

A retry repeats the whole handler with the same activation, state, and input.
Validate and perform fallible work before committing application state or
irreversible effects when a retry could occur.

`should_retry`/`shouldRetry` receives the structured `Failure`. `delay_ms`/
`delayMs` may be a fixed delay or a synchronous function of the failed attempt
and Failure.

Recovery receives a fresh Context plus the Failure. Zero recovery emissions
propagate the exact failure. Emissions replace it with normal control.
