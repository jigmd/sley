---
machine-display: false
---

# Inspection, Events, and Logging

Caskada exposes static graph descriptions and typed runtime events. It does not
build an implicit execution tree or serialize application values for you.

## Inspect a Compiled Graph

Compile once and inspect the portable description:

```python
compiled = flow.compile()
description = compiled.describe()

for element in description["elements"]:
    print(element["element_id"], element["kind"], element["name"])
```

```typescript
const compiled = flow.compile()
const description = compiled.describe()

for (const element of description.elements) {
  console.log(element.element_id, element.kind, element.name)
}
```

The description includes elements, links, scope ownership, entries, declared
exits, local concurrency and activation caps, plus the topology-derived global
concurrency default. It is suitable input for a diagram renderer or definition
audit. `CompiledFlow.run()` and `.start()` execute that same snapshot.

## Observe a Run

Pass a synchronous observer in RunOptions:

{% tabs %}
{% tab title="Python" %}

```python
from caskada import RunOptions


def observe(event):
    print(event.sequence, event.kind, event.run_id)


handle = flow.start(initial_state, options=RunOptions(observer=observe))
result = await handle.result()
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
const handle = flow.start(initialState, {
  observer(event) {
    console.log(event.sequence, event.kind, event.runId)
  },
})

const result = await handle.result
```

{% endtab %}
{% endtabs %}

Events cover run and scope lifecycle, callback admission and settlement, retry,
committed transitions and terminals, failure and cancellation fences, and
application reports. The schema version is `RUN_EVENT_SCHEMA_VERSION`.

Events are causally ordered facts, not a promise that independent concurrent
callbacks settle in a predetermined order.

## Report Application Facts

A live callback can publish a named application fact:

```python
context.report("documents_indexed", {"count": len(documents)})
```

```typescript
context.report('documents_indexed', { count: documents.length })
```

Reports share the run event stream and consume the run report budget. Omitted
data is distinct from explicit `None` / `undefined`.

Use reports for facts an observer should see. Do not use them to transfer data
between nodes; use state, input, or End output for that.

## Standard Logging Adapters

The Python adapter integrates with `logging`:

```python
import logging

from caskada import RunOptions
from caskada_logging import logging_observer

options = RunOptions(observer=logging_observer(logging.getLogger("workflow")))
```

The browser-safe TypeScript adapter accepts a small logger interface:

```typescript
import { createLoggingObserver } from 'caskada/logging'

const options = { observer: createLoggingObserver(logger) }
```

Adapters attach the complete typed event as structured metadata. Failure events
log at error, cancellation fences at warning, important lifecycle facts at
info, and detailed facts at debug.

## Observer Rules

Observers run synchronously at defined publication checkpoints. Keep them
bounded and fast:

- enqueue work to an existing bounded sink rather than performing network I/O;
- never return a coroutine, Promise, or thenable;
- never depend on observers to drive graph control;
- expect observer failures to become diagnostics rather than workflow failures.

Application values in causes, cancellation reasons, reports, terminal outputs,
and state are borrowed host values. An observer must not assume that every event
is JSON serializable or safe to format recursively.

## Full Results

Use `run()` for the final shared state. Use `start()` when observability matters:
every RunResult status carries state, terminals, statistics, and observer
diagnostics. Failed, cancelled, and abandoned results retain structured failure
or cancellation information without requiring log parsing.

Terminal records contain kind, action where applicable, output presence and
value, settlement sequence, and source activation ID. Combine callbacks receive
the same boundary information through `ScopeResult.terminals`, plus the
value-only `ScopeResult.outputs` projection.
