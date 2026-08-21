# Flow And Combine

A Flow owns one structured execution scope. It has an entry graph element,
outward links, declared named exits, local concurrency and activation caps, and
optional combine and recovery callbacks.

## Define A Flow

{% tabs %}
{% tab title="Python" %}

```python
batch = Flow(
    dispatch,
    name="Document batch",
    exits=("needs_review",),
    concurrency=8,
    max_activations=1_000,
    combine=collect,
    recover=recover_batch,
)
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
const batch = new Flow(dispatch, {
  name: 'Document batch',
  exits: ['needs_review'],
  concurrency: 8,
  maxActivations: 1_000,
  combine: collect,
  recover: recoverBatch,
})
```

{% endtab %}
{% endtabs %}

Flows are graph elements, so they can be linked and nested like Nodes. Each
child Flow invocation gets a fresh scope. Recursive Flow containment is
rejected at compilation.

## Exits

When a route has no matching link on its source element:

- an unlabelled route exits the current Flow;
- a named route exits only if that action is declared by the Flow;
- any other named route fails as `unknown_action`.

A nested Flow exit is then resolved through the Flow occurrence's links in its
parent. Hard End terminals bypass links and propagate through enclosing
boundaries unless a combiner replaces them.

## Structured Completion

A Flow does not finish when its first branch settles. It waits until every
admitted child branch has reached an End, exited, or failed. It then invokes
`combine` once if configured.

`ScopeResult` exposes:

- `terminals`: every End and Exit terminal in settlement order;
- `outputs`: the values carried by output-bearing terminals, also in settlement
  order.

An output-free `end()` remains a terminal but is absent from `outputs`.

```python
def collect(context, result):
    context.state["rows"] = list(result.outputs)
    context.emit()
```

Combine control is replacement-based:

- zero emissions preserve and forward the exact terminal set;
- one or more emissions replace that set with new outward continuations;
- combine may not call application handlers before all children settle.

This is why a reusable map/reduce helper is usually unnecessary: the runtime
already owns the synchronization point. Keep explicit Map and Reduce nodes only
when that pattern itself is the lesson or reusable abstraction.

## Empty Dispatch

A successful normal handler with no emissions creates one implicit unlabelled
continuation. Therefore a loop that emits zero items does not mean zero
branches. Handle a meaningful empty case explicitly:

```python
if not items:
    context.end()
    return

for item in items:
    context.emit("work", item)
```

## Concurrency

`Flow(concurrency=N)` caps simultaneously admitted direct child activations in
that scope. Run-wide `max_concurrency`/`maxConcurrency` is an optional global
ceiling. When omitted, Caskada derives the global ceiling from the largest
compiled Flow concurrency value.

Concurrency never makes synchronous callbacks nonblocking. Async callbacks
must yield, and blocking clients need an async API or deliberate thread/process
offload.

## Recovery

Flow recovery receives a `ScopeFailure` after the failing scope is fenced and
settled. It contains the primary Failure, suppressed failures, terminals that
settled before the fence, any partial ScopeResult, and the direct failing child
activation when one exists.

Zero recovery emissions propagate the exact failure packet. Emissions replace
it with normal outward control.

## Run And Start

`run(initial_state)` awaits a completed run and returns its shared state. It
raises `RunError` for failed, cancelled, or abandoned results.

`start(initial_state)` returns immediately with a `RunHandle`. Use the handle to
cancel, poll completion, or await the full discriminated `RunResult` including
terminals, failures, suppressed failures, diagnostics, statistics, and state.
