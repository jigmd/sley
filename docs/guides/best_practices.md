# Best Practices

## Keep Handlers Small

A node handler should perform one recognizable unit of work. Put graph control in
`context.emit(...)` and `context.end(...)`, and keep service clients and domain
logic in ordinary functions that can be tested without Caskada.

Use nested Flows when a group of nodes has its own entry, exits, concurrency
limit, or combine step. Do not create a Flow merely to group files.

## Choose One Data Channel Deliberately

Caskada has three application-data channels:

- `context.state` is one shared top-level map for the run.
- `context.input` is the value carried by the current branch.
- `context.end(value)` publishes one completed branch output for a Flow
  combiner.

Use state for run-wide facts and accumulated results. Use input for the specific
item a branch is processing. Use End output when a parent Flow must join results
from several branches.

Caskada does not validate application schemas or prove payload compatibility
across links. Validate dynamic input before writes or external effects:

```python
def process(context):
    job = parse_job(context.input)
    result = call_service(job)
    context.state["result"] = result
```

Static `Context[State, Input]` types document a handler's local expectation;
they are not runtime validation and do not type-check an entire graph.

## Treat Retry as Whole-Handler Retry

A retry invokes the complete handler again. Validate first, then perform
fallible work, and commit state or irreversible effects as late as practical.
Prefer idempotent service operations and idempotency keys where an external
effect may be repeated.

Use a node recovery callback for a local fallback. Use a Flow recovery callback
when the boundary needs to interpret failure from any child branch.

## Make Control Intent Visible

- Emit nothing for the ordinary unlabelled path.
- Use `emit("review", value)` for a genuinely named path.
- Use `end(value)` only for a hard branch terminal, commonly a worker output.
- Use a Flow combine callback when work must wait for every branch in that Flow.

The string `"default"` has no special meaning. An unlabelled link is defined by
`source.link(target)`.

`end()` appends an End arm; it does not stop the host function. Return afterward
when no later application code should run:

```python
def worker(context):
    context.end(transform(context.input))
    return
```

An empty emission loop follows the normal zero-emission rule. If an empty batch
must not continue to a worker, handle that case explicitly with `end()`.

## Be Intentional About Shared State

The caller's top-level initial state is shallow-copied once. Every branch in the
run shares the resulting top-level state map, and `run()` returns it. Nested
objects remain borrowed references.

With concurrent branches:

- write disjoint state keys, or synchronize application access;
- treat shared branch input objects as immutable, or emit distinct copies;
- do not assume output settlement order matches source order.

Read the returned state when chaining separate runs:

```python
state = await prepare_flow.run(initial_state)
state = await answer_flow.run(state)
```

Prefer one composed root Flow when the phases are one logical run.

## Bound Work Explicitly

Use Flow `concurrency` for local parallelism and optional Flow
`max_activations` for a local cycle or scope budget.

Provider quotas and timeouts remain application concerns. Put shared rate
limiting in the service client when several Flows use the same provider.

## Inspect Without Driving Control

Use `compile().describe()` for static topology. Use ordinary application logging
inside handlers for domain facts; logging must not decide graph control.

Use `run()` when only the final state matters. Use `start()` when the caller
needs terminal metadata or a structured failure.

## Organize for the Reader

Keep small projects small. A typical application needs only:

```text
main.py
nodes.py
flow.py
services.py
```

Split files when a domain boundary becomes real, not in anticipation of future
size. Keep shared type definitions together when types materially help readers;
omit them in examples or scripts where they add more ceremony than clarity.
