---
description: Retry one transient handler safely, resume from a local fallback, and recover a failed Flow with settled-work context.
---

# Retry and recovery

Retry repeats one complete Node handler. Recovery decides what the graph should
do after retry stops. Use both only for failures whose meaning is explicit in
the application.

## Retry a transient operation

The service below fails twice, then succeeds. The handler commits state only
after the fallible call succeeds.

{% tabs %}
{% tab title="Python" %}

```python
import asyncio

from sley import Context, Failure, Flow, RetryPolicy, node


class TransientError(Exception):
    pass


calls = 0


def fetch_value() -> str:
    global calls
    calls += 1
    if calls < 3:
        raise TransientError("service unavailable")
    return "ready"


def is_transient(failure: Failure) -> bool:
    return isinstance(failure.cause, TransientError)


@node(
    retry=RetryPolicy(
        max_attempts=3,
        should_retry=is_transient,
        delay_ms=10,
    )
)
def fetch(context: Context) -> None:
    value = fetch_value()
    context.state["value"] = value


async def main() -> None:
    state = await Flow(fetch).run({})
    print(calls, state["value"])


asyncio.run(main())
```

Output:

```text
3 ready
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { Flow, node } from '@jigging/sley'

import type { Failure } from '@jigging/sley'

class TransientError extends Error {}

let calls = 0

function fetchValue(): string {
  calls++
  if (calls < 3) throw new TransientError('service unavailable')
  return 'ready'
}

function isTransient(failure: Failure): boolean {
  return failure.cause instanceof TransientError
}

const fetch = node<{ value?: string }>(
  (context) => {
    const value = fetchValue()
    context.state.value = value
  },
  {
    retry: {
      maxAttempts: 3,
      shouldRetry: isTransient,
      delayMs: 10,
    },
  },
)

const state = await new Flow(fetch).run({})
console.log(calls, state.value)
```

Output:

```text
3 ready
```

{% endtab %}
{% endtabs %}

`max_attempts` / `maxAttempts` counts the first call, so `3` means at most
three total attempts. The predicate and delay callback are synchronous. A
delay callback receives the attempt that just failed and its `Failure`.

Retry is considered only for a handler failure while attempts remain. A policy
that returns false stops retry immediately. A policy throw or invalid return
becomes `retry_policy`; an invalid handler return becomes `invalid_outcome` and
is not retried.

## Make the whole handler safe to repeat

Each attempt receives the same `context.state` object and `context.input` value.
A failed attempt discards every buffered `emit` and `end`, but Sley cannot undo:

- state mutations;
- database or filesystem writes;
- messages sent to another service;
- charges, uploads, or other external effects.

Validate first, perform the fallible operation, then commit state and control.
Use application idempotency keys when the operation itself may complete before
the client observes failure.

Do not stack provider retries and Sley retries without calculating the maximum
combined attempts. Provider request timeouts also remain service-client
configuration; Sley does not add a handler timeout.

## Resume from Node recovery

Node recovery receives the final `Failure` and a fresh Context carrying the
same branch input. Emit an intentional route to replace failure with normal
control.

{% tabs %}
{% tab title="Python" %}

```python
def recover_fetch(context, failure):
    context.state["warning"] = failure.message
    context.emit("fallback")


fetch = node(
    fetch_handler,
    retry=RetryPolicy(max_attempts=3, should_retry=is_transient),
    recover=recover_fetch,
)
fetch.link(read_cache, "fallback")
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
const fetch = node(fetchHandler, {
  retry: { maxAttempts: 3, shouldRetry: isTransient },
  recover(context, failure) {
    context.state.warning = failure.message
    context.emit('fallback')
  },
})
fetch.link(readCache, 'fallback')
```

{% endtab %}
{% endtabs %}

Recovery runs once after retry stops. One or more explicit control calls
replace the failure and route from the Node. If recovery makes no control call,
the exact failure propagates. There is no implicit unlabelled emission from a
recovery callback.

When recovery itself throws or returns an application value, the replacement
Failure identifies `node_recovery` or `invalid_outcome`; its `previous` field
retains the failure recovery was handling.

## Recover a failed Flow

Flow recovery handles failure from any activation or from `combine`. It runs
after the scope stops admitting new work and waits for its already-running
local wave.

{% tabs %}
{% tab title="Python" %}

```python
from sley import ScopeFailure


def recover_batch(context, failure: ScopeFailure):
    context.state["completed_before_failure"] = list(failure.terminals)
    context.state["error"] = failure.primary.message
    context.end()


batch = Flow(dispatch, concurrency=4, recover=recover_batch)
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import type { ScopeFailure } from '@jigging/sley'

function recoverBatch(context: Context<State>, failure: ScopeFailure): void {
  context.state.completedBeforeFailure = [...failure.terminals]
  context.state.error = failure.primary.message
  context.end()
}

const batch = new Flow(dispatch, {
  concurrency: 4,
  recover: recoverBatch,
})
```

{% endtab %}
{% endtabs %}

`ScopeFailure.terminals` contains branches that settled before failure.
`primary` is the controlling Failure. `result` contains the exact
`ScopeResult` only when `combine` failed after receiving it.

Explicit recovery control replaces both the failure and settled terminal set,
then routes from the Flow occurrence. The `end()` above converts the failed
scope into one successful hard terminal. With zero control calls, Flow recovery
propagates the failure and original terminals unchanged.

For every failure and result field, see the
[Runtime semantics](../reference/runtime-semantics.md) and language API
references.
