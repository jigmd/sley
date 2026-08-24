---
description: Choose run or start and inspect Sley's structured completed and failed results.
---

# Failures and results

Use `run()` when the caller needs final state. Use `start()` when it needs the
full result, including terminals or structured failure details.

This example deliberately divides by zero so both APIs can show the same
failure.

{% tabs %}
{% tab title="Python" %}

```python
import asyncio

from sley import Flow, RunError, node


@node
def divide(context):
    context.state["result"] = 10 / context.state["divisor"]


division = Flow(divide)


async def main():
    state = await division.run({"divisor": 2})
    print(f"run: {state['result']}")

    failed = await division.start({"divisor": 0}).result()
    print(f"start: {failed.status}")
    if failed.status == "failed":
        print(f"kind: {failed.failure.kind}")
        print(f"attempt: {failed.failure.attempt}")

    try:
        await division.run({"divisor": 0})
    except RunError as error:
        print(f"run error: {error.result.failure.kind}")


asyncio.run(main())
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { Flow, node, RunError } from 'sley'

interface State {
  divisor: number
  result?: number
}

const divide = node<State>((context) => {
  if (context.state.divisor === 0) throw new Error('division by zero')
  context.state.result = 10 / context.state.divisor
})

const division = new Flow(divide)

const state = await division.run({ divisor: 2 })
console.log(`run: ${state.result}`)

const failed = await division.start({ divisor: 0 }).result()
console.log(`start: ${failed.status}`)
if (failed.status === 'failed') {
  console.log(`kind: ${failed.failure.kind}`)
  console.log(`attempt: ${failed.failure.attempt}`)
}

try {
  await division.run({ divisor: 0 })
} catch (error) {
  if (error instanceof RunError) {
    console.log(`run error: ${error.result.failure.kind}`)
  }
}
```

{% endtab %}
{% endtabs %}

{% tabs %}
{% tab title="Python output" %}

```text
run: 5.0
start: failed
kind: handler
attempt: 1
run error: handler
```

{% endtab %}
{% tab title="TypeScript output" %}

```text
run: 5
start: failed
kind: handler
attempt: 1
run error: handler
```

{% endtab %}
{% endtabs %}

## `run()` is the final-state projection

`await flow.run(initialState)` waits for completion and returns the run-owned
shared state. If the run fails, it raises `RunError`. The error's `result` is
the exact structured failed result, and its native cause points to the
controlling application error when one exists.

This is the right API for most application calls.

## `start()` exposes the full result

`flow.start(initialState)` starts the run and immediately returns a `RunHandle`.
Await `handle.result()` to receive exactly one of these shapes:

```text
Completed { status, state, terminals }
Failed    { status, state, terminals, failure }
```

Each terminal records whether a branch ended or exited, whether it carried an
output, its value, settlement sequence, and source activation. A failed result
keeps any sibling terminals that settled before the failure.

`Failure.kind` identifies the runtime stage, such as `handler`,
`unknown_action`, or `activation_limit`. Its IDs and `previous` link preserve
where a replacement failure came from without depending on exception-message
text.

Retries and recovery can turn selected failures into normal control, but they
repeat or replace lifecycle outcomes and deserve a deliberate policy. Continue
with [Retry and recovery](../guides/retry-and-recovery.md) for that task, or use
the [Python](../reference/python.md) and
[TypeScript](../reference/typescript.md) references for exact result fields.
