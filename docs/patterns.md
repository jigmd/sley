---
description: Choose the smallest Sley graph pattern that fits a workflow, then open a complete tested example.
---

# Choose a Pattern

You know the mechanism you need; now you want to see it survive contact with a
real application. Choose the smallest complete project that answers your next
question. You do not need to climb the table in order.

Start with an ordinary function. Add a Sley graph when the workflow has visible
decisions, repeated work, a structured join, or a reusable scope.

| Need                        | Smallest graph shape                         | Complete example                                                                                        |
| --------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Fixed sequence              | Unlabelled links                             | [Article workflow](https://github.com/jigmd/sley/tree/main/cookbook/python-workflow)                    |
| Decision or loop            | Named emissions and links                    | [Research agent](https://github.com/jigmd/sley/tree/main/cookbook/python-agent)                         |
| Process many items          | One emission per item                        | [Sequential batch](https://github.com/jigmd/sley/tree/main/cookbook/python-batch)                       |
| Process and aggregate       | Fan-out, `end(value)`, Flow `combine`        | [Concurrent service checks](https://github.com/jigmd/sley/tree/main/cookbook/typescript-batch)          |
| Reuse a subgraph            | A nested Flow as a graph element             | [Reusable batch Flow](https://github.com/jigmd/sley/tree/main/cookbook/python-batch-flow)               |
| Keep partial successes      | Flow recovery with settled terminals         | [Partial batch recovery](https://github.com/jigmd/sley/tree/main/cookbook/python-resilient-batch)       |
| Map then reduce explicitly  | Map and Reduce application nodes             | [Resume qualification](https://github.com/jigmd/sley/tree/main/cookbook/python-map-reduce)              |
| Validate model output       | Parse before state or control changes        | [Structured output](https://github.com/jigmd/sley/tree/main/cookbook/python-structured-output)          |
| Pause for a person          | Application event or a later run             | [Web human review](https://github.com/jigmd/sley/tree/main/cookbook/python-fastapi-hitl)                |
| Retrieve context            | Offline indexing plus an online Flow         | [RAG](https://github.com/jigmd/sley/tree/main/cookbook/python-rag)                                      |
| Coordinate agents           | Separate Flows exchange application messages | [Multi-agent game](https://github.com/jigmd/sley/tree/main/cookbook/python-multi-agent)                 |
| Improve against a bar       | Builder, evaluator, and bounded revision     | [Evaluator–optimizer](https://github.com/jigmd/sley/tree/main/cookbook/python-supervisor)               |
| Decompose dynamic work      | Plan, fan-out, combine, and integration      | [Orchestrator–workers](https://github.com/jigmd/sley/tree/main/cookbook/python-orchestrator-workers)    |
| Select a qualitative result | Candidate fan-out and blind pairwise judge   | [Best-of-N judge](https://github.com/jigmd/sley/tree/main/cookbook/python-best-of-n-judge)              |
| Pursue reference parity     | Nested quality loops plus final integration  | [Reference-grounded quality loop](https://github.com/jigmd/sley/tree/main/cookbook/python-quality-loop) |

## Compose mechanisms, not framework roles

Sley has no special Agent, RAG, Batch, or Human-in-the-loop class. Those names
describe application structures made from the same small runtime model:

```python
decide.link(search, "search")
search.link(decide)
decide.link(answer, "answer")
```

Those three links reveal a search loop and its answer exit. Model calls,
databases, queues, and user interfaces remain ordinary dependencies inside or
around the handlers.

## Choose the feedback source first

The name of a quality workflow matters less than the evidence that can change
its next route. Use the strongest feedback the application can observe.

| Acceptance can be observed as | Prefer                                     | Example                                                                                        |
| ----------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Valid structure               | Parser, schema, or assertions              | [Structured output](https://github.com/jigmd/sley/tree/main/cookbook/python-structured-output) |
| Executable behavior           | Tests, execution, or simulation            | [Text to SQL](https://github.com/jigmd/sley/tree/main/cookbook/python-text2sql)                |
| Supported factual claims      | Retrieved evidence and a source audit      | [RAG](https://github.com/jigmd/sley/tree/main/cookbook/python-rag)                             |
| One convergent answer         | Independent samples and voting             | [Majority vote](https://github.com/jigmd/sley/tree/main/cookbook/python-majority-vote)         |
| Comparative quality           | Anonymous pairwise comparison              | [Best-of-N judge](https://github.com/jigmd/sley/tree/main/cookbook/python-best-of-n-judge)     |
| Improvement of one artifact   | Structured evaluator feedback and revision | [Evaluator–optimizer](https://github.com/jigmd/sley/tree/main/cookbook/python-supervisor)      |
| Consequential judgment        | Deterministic gates plus human approval    | [Web human review](https://github.com/jigmd/sley/tree/main/cookbook/python-fastapi-hitl)       |

Prefer a deterministic failure over a model opinion whenever both can express
the same requirement. A database error can identify invalid SQL directly. A
critic saying that the SQL looks plausible cannot.

## Treat agent patterns as compositions

Evaluator–optimizer is one visible cycle: build, evaluate, and either approve or
revise. Orchestrator–workers adds a serial plan, independent branch inputs, a
Flow-owned join, and an integration editor. Best-of-N replaces revision with
candidate search and selection. A reference-grounded quality loop composes all
three around a concrete benchmark.

Sley does not create an independent model context when you create a nested
Flow. If a critic must be fresh, the application must make a stateless request
or start a separate agent session without the builder's rationale. Sley makes
the handoff and its possible routes visible.

Keep comparison inputs equivalent. Strip candidate identity, randomize pair
order, ask for artifact evidence and a specific flip condition, and calibrate
model judgments against deterministic checks or human-scored examples when the
decision matters.

## Give every quality loop an honest stop

Normal acceptance is one exit, not the only exit. Decide before the run what
happens when the iteration cap is reached, two passes find the same material
gap, judges disagree, or the benchmark requires unavailable data or capability.
Record the residual gap instead of relabelling it as success.

These domain stops complement `max_activations` / `maxActivations`. The domain
condition explains why work is complete or cannot progress; the activation
guard catches broken routing.

## Prefer Flow combine for synchronization

Use a Flow combiner when reduction must wait for every branch in that Flow.
Shared counters duplicate scheduler knowledge and become fragile under failure
or concurrency. Keep explicit Map and Reduce nodes only when those roles are the
lesson or a reusable application abstraction.

## Put human waiting at an application boundary

For a short in-process review, an async handler can await an application event
while the run remains alive. For a durable review, persist the pending
application state, return control to the web or UI layer, and start a later run
after the decision arrives. Sley does not persist or resume a suspended run.

Browse the [example projects](examples/README.md) by learning goal and
complexity.
