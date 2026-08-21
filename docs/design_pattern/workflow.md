# Workflow

A workflow is a graph whose steps have clear dependencies. The common case is
linear and needs no explicit control calls.

```python
extract.link(transform)
transform.link(load)
pipeline = Flow(extract)
```

A successful normal handler with no emissions follows its unlabelled link.
When a step chooses between paths, emit a named action:

```python
@node
def review(context):
    action = "publish" if context.state["approved"] else "revise"
    context.emit(action)


review.link(publish, "publish")
review.link(revise, "revise")
```

## Data Choice

Use shared state for workflow facts that later, unrelated steps need. Use
branch input when one transition carries a specific work item.

```python
context.state["customer_id"] = customer.id
context.emit("charge", invoice)
```

The charge handler reads the invoice from `context.input` and can still read the
customer ID from `context.state`.

## Composition

Nest a reusable Flow when a group of steps has its own concurrency, exits,
combiner, recovery, or activation cap. A normal child Flow exit follows the
child occurrence's link in its parent; `end()` intentionally bypasses it.

See [python-workflow](../../cookbook/python-workflow/) for a linear example and
[python-flow](../../cookbook/python-flow/) for explicit hard termination.
