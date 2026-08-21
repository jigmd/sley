---
machine-display: false
---

# Testing

Test application logic as ordinary code. Test Caskada behavior through a real
Flow. `Context`, `RunHandle`, and compiled runtime objects are runtime-issued
objects and should not be constructed by tests.

## Test a Complete Small Flow

Inject a fake service, run the real graph, and assert the returned state:

{% tabs %}
{% tab title="Python" %}

```python
from caskada import Flow, node


async def test_answer_flow():
    calls = []

    async def fake_model(question):
        calls.append(question)
        return "Paris"

    async def answer(context):
        context.state["answer"] = await fake_model(context.state["question"])

    flow = Flow(node(answer))
    initial_state = {"question": "Capital of France?"}

    final_state = await flow.run(initial_state)

    assert final_state["answer"] == "Paris"
    assert calls == ["Capital of France?"]
    assert "answer" not in initial_state
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { Flow, node } from 'caskada'
import { expect, it, vi } from 'vitest'

it('answers a question', async () => {
  const model = vi.fn(async () => 'Paris')
  const answer = node<{ question: string; answer?: string }>(async (context) => {
    context.state.answer = await model(context.state.question)
  })

  const initialState = { question: 'Capital of France?' }
  const finalState = await new Flow(answer).run(initialState)

  expect(finalState.answer).toBe('Paris')
  expect(model).toHaveBeenCalledWith('Capital of France?')
  expect(initialState).not.toHaveProperty('answer')
})
```

{% endtab %}
{% endtabs %}

This tests the graph definition, state capture, handler, and normal Flow exit
together without mocking framework internals.

## Test Routing and Branch Data

Use observable application effects to assert which target ran. For fan-out,
collect values in a Flow combine callback rather than coordinating test branches
with shared counters.

Test these boundary cases explicitly when they matter:

- zero emissions and the unlabelled link;
- a named emission and its target;
- an unknown action;
- empty fan-out;
- `end()` with no output versus `end(None)` / `end(undefined)`;
- combine pass-through with zero emissions versus terminal replacement with one
  or more emissions.

## Test Failures Through `start()`

`run()` raises `RunError` for a non-completed result. Use `start()` when the test
needs the full result:

```python
handle = flow.start(initial_state)
result = await handle.result()

assert result.status == "failed"
assert result.failure.kind == "handler"
assert result.state["attempted"] is True
```

Use the corresponding TypeScript `handle.result()` Promise. Assert structured
failure kinds, details, and provenance rather than native exception messages.
When testing the simple `run()` projection, `RunError.result` exposes the same
structured data and its standard native cause points to the controlling
application error when one exists.

## Test Retry and Recovery Boundaries

Use a deterministic fake that fails a known number of times. Assert application
calls and final state. Remember that retry re-enters the complete handler, so a
test should catch accidental writes or effects before the fallible operation.

For recovery, separately cover:

- recovery emits a replacement route;
- recovery emits nothing and preserves the original failure;
- recovery itself fails.

## Test Definitions Without Running

`flow.compile()` catches invalid topology, duplicate ownership, and invalid
definition options. `flow.compile().describe()` returns a portable snapshot for
asserting links, scope concurrency, declared exits, and activation limits.

Prefer semantic assertions over snapshots of the entire description. Full
snapshots make harmless names or IDs expensive to change.

Keep framework conformance tests separate from application tests. Application
tests should prove the workflow's behavior; Caskada's own suite proves the
retained routing, terminal, combine, retry, recovery, concurrency, and
cross-language contracts.
