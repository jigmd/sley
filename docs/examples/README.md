---
description: Find a complete Sley project by learning goal, language, and cognitive complexity.
---

# Example Projects

The tutorial gave you one evolving workflow. The cookbook lets you follow your
own problem instead. Pick the smallest project that resembles what you are
trying to build, run it, and change one decision before moving to a larger one.

These are complete applications rather than isolated fragments. Each project
has one primary lesson, its own installation instructions, and a real Sley graph
exercised by repository verification.

Complete the [Quickstart](../quickstart.md) first. Cookbook projects begin at
application level and may introduce terminal input, files, model providers, or
other services alongside Sley.

## Start with the mechanism you need

| Goal                       | Python                                                                                                      | TypeScript                                                                                                   |
| -------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Provider-free next project | [Shared run state](https://github.com/jigmd/sley/tree/main/cookbook/python-communication)                   | [Hello world](https://github.com/jigmd/sley/tree/main/cookbook/typescript-hello-world)                       |
| Retry and local recovery   | [Retry and recovery](https://github.com/jigmd/sley/tree/main/cookbook/python-node)                          | [Retry and recovery](https://github.com/jigmd/sley/tree/main/cookbook/typescript-retry-recovery)             |
| Named routing and a loop   | [Research agent](https://github.com/jigmd/sley/tree/main/cookbook/python-agent)                             | [Search agent](https://github.com/jigmd/sley/tree/main/cookbook/typescript-agent)                            |
| Fan-out and combine        | [Combine CSV chunks](https://github.com/jigmd/sley/tree/main/cookbook/python-batch-node)                    | [Service checks](https://github.com/jigmd/sley/tree/main/cookbook/typescript-batch)                          |
| Partial-result recovery    | [Resilient batch](https://github.com/jigmd/sley/tree/main/cookbook/python-resilient-batch)                  | [Resilient batch](https://github.com/jigmd/sley/tree/main/cookbook/typescript-resilient-batch)               |
| Nested Flows               | [Reusable batch Flow](https://github.com/jigmd/sley/tree/main/cookbook/python-batch-flow)                   | [Concurrent nested workers](https://github.com/jigmd/sley/tree/main/cookbook/typescript-nested-flow)         |
| Dynamic decomposition      | [Orchestrator–workers–editor](https://github.com/jigmd/sley/tree/main/cookbook/python-orchestrator-workers) | [Orchestrator and workers](https://github.com/jigmd/sley/tree/main/cookbook/typescript-orchestrator-workers) |
| Independent quality review | [Evaluator–optimizer supervisor](https://github.com/jigmd/sley/tree/main/cookbook/python-supervisor)        | [Bounded quality loop](https://github.com/jigmd/sley/tree/main/cookbook/typescript-quality-loop)             |
| Blind candidate selection  | [Blind best-of-N judge](https://github.com/jigmd/sley/tree/main/cookbook/python-best-of-n-judge)            | Start with the Python topology                                                                               |
| Reference parity capstone  | [Reference-grounded quality loop](https://github.com/jigmd/sley/tree/main/cookbook/python-quality-loop)     | [Bounded quality loop](https://github.com/jigmd/sley/tree/main/cookbook/typescript-quality-loop)             |

The [Python catalog](python.md) covers the broadest set of application patterns.
The [TypeScript catalog](typescript.md) provides a complete core path from one
node through composition, recovery, integrations, and bounded quality loops.

## Read complexity as cognitive load

Complexity is not a score or quality badge. It estimates how many concepts a
reader must hold at once. Lower is usually the right starting point; higher
examples combine more Sley and domain mechanisms.

Every project README stays beside the code it explains. The generated catalogs
combine README titles and complexity with curated lesson labels, and generation
fails when a project is missing or stale.
