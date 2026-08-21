---
machine-display: false
---

# Migrating from Caskada v2 to v3

V3 is a deliberate API break. Migrate one Flow at a time and test its routing,
state, retry, and terminal behavior before composing it into a larger graph.

## Concept Map

| V2                                         | V3                                        |
| ------------------------------------------ | ----------------------------------------- |
| `Node` subclass                            | function wrapped by `node(...)` / `@node` |
| `prep` + `exec` + `post`                   | one handler receiving `Context`           |
| global Memory                              | `context.state`                           |
| local Memory / `forkingData`               | `context.input`                           |
| `trigger(action, data)`                    | `context.emit(action, data)`              |
| implicit/default trigger                   | zero emissions or `context.emit()`        |
| `source.next(target)` / `source >> target` | `source.link(target)`                     |
| `source.on(action, target)`                | `source.link(target, action)`             |
| terminal trigger propagation               | declared Flow exit                        |
| `ParallelFlow`                             | `Flow(..., concurrency=N)`                |
| shared counters for fan-in                 | Flow `combine` callback                   |
| `execFallback`                             | node `recover` callback                   |
| Flow `post` aggregation                    | Flow `combine` callback                   |
| execution tree from `run()`                | final shared state from `run()`           |
| no cancellable handle                      | `start()` and structured `RunResult`      |

## Replace Node Classes with Handlers

Before, in v2:

```python
class Answer(Node):
    async def prep(self, memory):
        return memory.question

    async def exec(self, question):
        return await model.answer(question)

    async def post(self, memory, question, answer):
        memory.answer = answer
        self.trigger("review")
```

After, in v3:

```python
@node
async def answer(context):
    question = require_question(context.state)
    response = await model.answer(question)
    context.state["answer"] = response
    context.emit("review")
```

Validation that lived in `prep` should happen before state writes or external
effects. A v3 retry invokes the whole handler, not only the old `exec` phase.

Configuration moves to `node(...)`:

```python
answer = node(
    answer_handler,
    retry=RetryPolicy(max_attempts=3, delay_ms=1_000),
    timeout_ms=30_000,
    recover=answer_recovery,
)
```

## Replace Memory with State and Input

V3 has one shared top-level state map per run. Branch-specific data travels as
input:

```python
def dispatch(context):
    for document in context.state["documents"]:
        context.emit("embed", document)


async def embed(context):
    vector = await embeddings.create(context.input)
    context.end(vector)
```

The initial top-level state is shallow-copied. Caskada never mutates the caller's
top-level object. Read the state returned by `run()`:

```python
state = await flow.run(initial_state)
```

Nested values remain borrowed references. Separate runs require explicit state
handoff, while nested Flows in one run share the same state automatically.

## Migrate Links and Actions

V3 links are target-first:

```python
source.link(target)
source.link(reviewer, "review")
```

A normal handler with zero buffered control calls follows the unlabelled link.
If no such link exists, it exits its current Flow normally.

V2's `DEFAULT_ACTION` and the literal `"default"` were often used as the default
sentinel. Translate that sentinel to zero emissions or `emit()`, and translate
its successor to an unlabelled `link(target)`. In v3,
`emit("default")` means a genuinely named action and requires a named link or
declared exit.

V2 allowed an action without a physical successor to propagate out of a Flow.
V3 requires intended named exits to be declared:

```python
review = Flow(entry, exits=("needs_input",))
```

An undeclared name with no link now fails as `unknown_action`. This turns an
accidental missing edge into data rather than silently propagating it.

Each source occurrence may have at most one physical target for a given action.
Use one router node that emits distinct actions, or fan out with several
emissions, when multiple destinations are intentional.

## Migrate Termination

V2 leaf termination was often inferred from a missing successor. V3 keeps that
ordinary Flow-exit behavior: a successful handler may emit nothing.

Use `context.end(value)` only for a hard branch terminal. It bypasses links and
crosses nested Flow boundaries until a combine callback replaces it. The call
buffers a terminal; it does not stop Python or JavaScript execution.

```python
def worker(context):
    context.end(process(context.input))
    return
```

An omitted End output differs from an explicit `None` / `undefined` output.

## Replace Fan-In Counters with `combine`

A Flow combine callback runs once after its child scope becomes quiet:

```python
def collect(context, result):
    context.state["vectors"] = list(result.outputs)
    context.emit()


batch = Flow(dispatch, concurrency=8, combine=collect)
dispatch.link(worker, "embed")
```

Worker `end(value)` outputs appear in `result.outputs`. Zero combine emissions
forward the original terminal set unchanged. Any combine emissions replace that
set with the newly emitted continuations.

An empty dispatch loop takes the normal zero-emission path. Use an explicit
`end()` when an empty batch must not route into a worker.

## Migrate Flow Subclasses

V2 Flow lifecycle hooks have no direct class override in v3:

- pre-Flow work becomes an explicit entry node or ordinary helper call;
- post-Flow aggregation and routing becomes the Flow combine callback;
- Flow failure fallback becomes the Flow recovery callback;
- custom `run_tasks` schedulers require redesign against v3 Flow concurrency or
  an extension outside the core runtime.

V3 Flow combine emissions replace the child terminal set. A v2 additive Flow
`post` must explicitly reproduce any outputs or exits it intends to retain.

## Migrate Retry and Loop Bounds

V2 `max_retries=N` already represented total attempts. Translate it to
`RetryPolicy(max_attempts=N)`, not `N + 1`.

V2 `wait=S` was seconds and accepted floats. V3 delay is an integer number of
milliseconds. `delay_ms=S * 1000` is semantics-preserving only when the result
is a nonnegative safe integer. Otherwise choose and document a rounding or
backoff policy manually.

V2 Flow `max_visits` defaulted to 15. V3 has no hidden visit default. Use a
Flow-local `max_activations` for direct work in that scope and run-wide
activation, transition, attempt, and deadline limits for the whole invocation.
Review cycles explicitly because the counters do not all measure the same thing.

## Migrate Results and Observation

Use `run()` for the common state projection:

```python
final_state = await flow.run(initial_state)
```

Use `start()` when terminal kinds, actions, outputs, failure packets,
cancellation, statistics, or events matter:

```python
handle = flow.start(initial_state, options=options)
result = await handle.result()
```

Static topology is available from `flow.compile().describe()`. Runtime facts
are delivered to a synchronous RunOptions observer; application code can add
facts with `context.report(...)`.

## Migration Checklist

1. Convert one lifecycle class to one function handler.
2. Separate shared state from branch input.
3. Convert links to target-first `link(target, action?)`.
4. Translate the v2 default sentinel to the unlabelled path.
5. Declare every intentional named Flow exit.
6. Replace fan-in counters with a Flow combine callback where applicable.
7. Re-evaluate whole-handler retry side effects and delay units.
8. Add explicit loop, work, and deadline bounds.
9. Capture the state returned by `run()`.
10. Test zero emission, named routes, empty fan-out, End, combine, and failure.
