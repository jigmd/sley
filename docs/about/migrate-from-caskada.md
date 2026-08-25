---
description: Convert a Caskada v2 Flow to Sley one behavior at a time, including Memory, links, termination, fan-in, retry, and results.
---

# Migrate from Caskada v2

You do not need to redesign an entire Caskada application at once. Choose one
Flow whose behavior you can observe, move that boundary, and keep the old and
new results comparable while you learn the different model.

Sley is a deliberate successor, not an import-compatible release. Preserve the
Flow's routes, data, effects, and failure behavior before composing it into a
larger graph.

## Translate the vocabulary

| Caskada v2                                 | Sley                                                       |
| ------------------------------------------ | ---------------------------------------------------------- |
| PyPI `caskada` package                     | `sley` package                                             |
| npm `caskada` package                      | `@jigging/sley` package                                    |
| `Node` subclass                            | Function wrapped by `node(...)` or `@node`                 |
| `prep` + `exec` + `post`                   | One handler receiving `Context`                            |
| Global `Memory`                            | `context.state`                                            |
| Local `Memory` / `forkingData`             | `context.input`                                            |
| `trigger(action, data)`                    | `context.emit(action, data)`                               |
| `source.next(target)` / `source >> target` | `source.link(target)`                                      |
| `source.on(action, target)`                | `source.link(target, action)`                              |
| Terminal trigger propagation               | Declared Flow exit                                         |
| `ParallelFlow`                             | `Flow(..., concurrency=N)`                                 |
| Shared fan-in counters                     | Flow `combine` callback                                    |
| `execFallback`                             | Node `recover` callback                                    |
| Flow `post`                                | Flow `combine` callback                                    |
| Execution tree from `run()`                | Final state from `run()`; structured result from `start()` |

## Replace lifecycle classes with handlers

Caskada separated preparation, execution, and post-processing:

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

Sley makes that order visible in one function:

```python
@node
async def answer(context):
    question = require_question(context.state)
    response = await model.answer(question)
    context.state["answer"] = response
    context.emit("review")
```

Validate before state writes or effects. Sley retry invokes the complete handler,
not only the old `exec` phase.

## Separate shared facts from branch messages

Sley shallow-copies the initial top-level state once. Every branch sees that
same run-owned mapping. Branch-specific work travels as input:

{% tabs %}
{% tab title="Python" %}

```python
@node
def dispatch(context):
    for document in context.state["documents"]:
        context.emit("embed", document)


@node
async def embed(context):
    context.end(await embeddings.create(context.input))
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
interface State {
  documents: string[]
  vectors?: unknown[]
}

const dispatch = node<State>((context) => {
  for (const document of context.state.documents) {
    context.emit('embed', document)
  }
})

const embed = node<State, string>(async (context) => {
  context.end(await embeddings.create(context.input))
})
```

{% endtab %}
{% endtabs %}

Nested state values remain borrowed references. Sley has no local/global proxy
fallback and does not deep-copy branch data.

## Convert links target first

{% tabs %}
{% tab title="Python" %}

```python
source.link(next_node)
source.link(reviewer, "review")
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
source.link(nextNode)
source.link(reviewer, 'review')
```

{% endtab %}
{% endtabs %}

A normal handler with no control call follows the unlabelled link. If none
exists, the branch exits its current Flow normally.

Caskada's `DEFAULT_ACTION` and literal `"default"` often meant this ordinary
path. Translate them to no control call or `emit()`. In Sley,
`emit("default")` is a real named action.

## Declare names that leave a Flow

Caskada allowed an unmatched terminal trigger to propagate outward. Sley makes
that boundary part of the Flow definition:

```python
review = Flow(entry, exits=("needs_input",))
```

```typescript
const review = new Flow(entry, { exits: ['needs_input'] })
```

An unmatched, undeclared name fails as `unknown_action`. A physical link wins
when the same name is also declared as an exit.

One source occurrence can have only one physical target per action. Replace a
Caskada broadcast with several explicit `emit()` calls, or route distinct names
to distinct targets.

## Keep ordinary leaves ordinary

A successful handler with no outgoing link already exits its Flow. It does not
need `end()`.

Use `end(value)` only for a hard branch terminal. It bypasses links and crosses
nested Flow boundaries until a combiner replaces it. The call buffers the
terminal; it does not return from Python or JavaScript.

```python
def worker(context):
    context.end(process(context.input))
    return
```

`end()` has no output. `end(None)` or `end(undefined)` carries an explicit
output whose value is `None` or `undefined`.

## Replace fan-in counters with `combine`

The runtime already knows when every branch in a Flow has settled:

{% tabs %}
{% tab title="Python" %}

```python
def collect(context, result):
    context.state["vectors"] = list(result.outputs)


dispatch.link(embed, "embed")
batch = Flow(dispatch, concurrency=8, combine=collect)
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
dispatch.link(embed, 'embed')
const batch = new Flow(dispatch, {
  concurrency: 8,
  combine(context, result) {
    context.state.vectors = [...result.outputs]
  },
})
```

{% endtab %}
{% endtabs %}

`result.outputs` includes output-bearing End and Flow-exit terminals. A silent
combiner preserves child terminals. Any combiner control calls replace the
entire child terminal set.

An empty dispatcher follows the ordinary unlabelled path. Call `end()` when an
empty batch must produce no worker branch or output.

## Recheck retry, cycles, and results

- Caskada `max_retries=N` represented total attempts. Use
  `max_attempts=N` / `maxAttempts: N`, not `N + 1`.
- Caskada `wait` used seconds. Sley `delay_ms` / `delayMs` uses nonnegative
  integer milliseconds.
- Caskada defaulted `max_visits` to 15. Sley has no hidden cycle bound. Set
  `max_activations` / `maxActivations` on deliberate cycles.
- `run()` now returns final state and raises or rejects `RunError` on failure.
  Use `start().result()` for terminal and failure records.
- `compile().describe()` is static topology, not Caskada's execution tree.

## Migration checklist

1. Convert one lifecycle class to one handler.
2. Separate shared state from branch input.
3. Convert links to `link(target, action?)`.
4. Translate the default sentinel to the unlabelled path.
5. Declare every named Flow exit.
6. Replace accidental broadcast with explicit emissions.
7. Replace fan-in counters with Flow combine where synchronization is required.
8. Audit whole-handler retry effects and delay units.
9. Add explicit activation limits to cycles.
10. Capture the state returned by `run()` and test structured failure through
    `start()`.

Use [Runtime semantics](../reference/runtime-semantics.md) when a legacy edge
case needs an exact destination.
