# Core Model

Caskada has four author-facing parts:

| Part                        | Responsibility                                                                     |
| --------------------------- | ---------------------------------------------------------------------------------- |
| [Node](node.md)             | Run one ordinary function with retry and recovery policy                           |
| [Context](context.md)       | Expose state, branch input, and buffered control during one callback                |
| [State and Input](state.md) | Separate run-wide facts from branch-specific values                                |
| [Flow](flow.md)             | Own graph topology, a structured scope, concurrency, and branch combination        |

The graph describes allowed control movement. Application data is not inferred
from that graph: handlers decide whether a value belongs in shared state or in
one branch's input.

## One Small Example

```python
from caskada import Context, Flow, node


@node
def dispatch(context: Context) -> None:
    for number in context.state["numbers"]:
        context.emit("work", number)


@node
def square(context: Context) -> None:
    context.end(context.input**2)


def combine(context: Context, result) -> None:
    context.state["squares"] = list(result.outputs)


dispatch.link(square, "work")
squares = Flow(dispatch, combine=combine, concurrency=4)
```

`dispatch` creates branches, `square` hard-terminates each worker with an
output, and the Flow invokes `combine` once after all workers settle.

## Compilation And Execution

`Flow.compile()` validates and snapshots topology. A Flow may be compiled or
run repeatedly, including by concurrent invocations; each run owns its runtime
state, activation counters, scopes, and result.

Graph-definition and option errors are synchronous exceptions before a handle
exists. Failures encountered by scheduler-owned lifecycle work become typed
run results.
