---
description: Build a mental model of nodes, links, Context, and Flows that stays useful as your graph grows.
---

# The Core Model

Your first graph was deliberately boring: prepare, then publish. That is useful.
A graph does not become a different kind of program. It makes the shape of an
ordinary program explicit.

You only need four pieces to reason about Sley.

## Four questions, four pieces

| Ask this question                          | Sley answers with |
| ------------------------------------------ | ----------------- |
| What unit of work runs?                    | **Node**          |
| Where may work go next?                    | **Link**          |
| What can the current node read and decide? | **Context**       |
| What work belongs in one boundary?         | **Flow**          |

### A Node does one meaningful piece of work

`node(handler)` wraps one synchronous or asynchronous function. The function
can validate data, call a service, or update state just as it would outside a
graph.

A useful node boundary gives the work one name and one reason to change. If a
function has no meaningful decision or boundary around it, it may not need to
be a separate node.

### A Link makes one allowed path visible

```python
prepare.link(publish)
```

The source owns the link. The target comes first because it is required; an
optional action label comes second. Nodes and nested Flows can both be link
targets.

One source can have one unlabelled link and one link for each named action. A
duplicate fails immediately instead of leaving routing ambiguous.

### Context belongs to one node run

When a node runs, it receives `context`:

- `context.state` contains facts shared for this run;
- `context.input` contains the message carried by this branch;
- `context.emit(...)` chooses where work goes next.

A node may run more than once, but each occurrence gets its own Context.

### A Flow owns a settlement boundary

```python
release = Flow(prepare)
```

A Flow names an entry point and waits for every path created inside its boundary
to finish.

The entry node returning is not enough when that node created more work. The
Flow completes only after those paths finish or fail. Later lessons add precise
names for those outcomes when fan-out makes the distinction useful.

## Keep work and movement separate

This is the first design principle worth carrying beyond Sley:

- node bodies explain **what happens**;
- links and control calls explain **where work goes**.

When those concerns are mixed across nested conditionals and callbacks, a
reader must execute the program in their head to discover its possible paths.
A graph earns its keep when it makes those paths readable before execution.

Do not turn every function into a node. Normal function calls remain the best
tool for local implementation detail. Create a node when the step matters to
the workflow's topology, policy, or failure boundary.

## Predict one change

Start from the Quickstart and add one node:

```python
@node
def announce(context):
    context.state["message"] = "release announced"


publish.link(announce)
```

Before running it, predict which function changes the slug, which function
changes the status, and which link makes `announce` run. The same change in
TypeScript uses `const announce = node(...)` and the identical
`publish.link(announce)` call.

Now look back at the Quickstart and answer these without running it:

1. Which element is the Flow entry?
2. Why does `publish` run when `prepare` makes no control call?
3. What must finish before the Flow completes?
4. Which code would you change to insert approval without editing `prepare`?

If you can answer those, you already understand the linear runtime model.

The release still publishes every time. [Links and routing](routing.md) adds the
first real graph decision while keeping the four-piece model intact.
