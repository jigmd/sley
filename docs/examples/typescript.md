---
description: Browse complete TypeScript projects by learning goal, Sley mechanism, and cognitive complexity.
---

# TypeScript Examples

Do not choose by ambition. Choose the smallest project that answers your next
question, run it, and change one behavior. Complexity estimates cognitive load,
not quality; lower is usually the more useful starting point.

## Start here

| Project                                                                                                                                                                                                   | What it teaches                                                          | Sley mechanisms                | Complexity |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------ | ---------: |
| [TypeScript Hello World](https://github.com/jigmd/sley/tree/main/cookbook/typescript-hello-world)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-hello-world/README.md) | Create one typed node, update shared state, and finish an ordinary leaf. | `node`, `state`, `run`         |          1 |
| [A Small Typed Workflow](https://github.com/jigmd/sley/tree/main/cookbook/typescript-workflow)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-workflow/README.md)       | Model a small three-step application as explicit topology.               | `node`, `link`, `Flow`         |          2 |
| [Inspect a Compiled Flow](https://github.com/jigmd/sley/tree/main/cookbook/typescript-inspection)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-inspection/README.md)  | Inspect portable compiled topology and an explicit run result.           | `compile`, `describe`, `start` |        2.5 |

## Composition and failure

| Project                                                                                                                                                                                                                           | What it teaches                                                      | Sley mechanisms                         | Complexity |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------- | ---------: |
| [Retry and Recovery in TypeScript](https://github.com/jigmd/sley/tree/main/cookbook/typescript-retry-recovery)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-retry-recovery/README.md)         | Retry a complete handler and recover locally after attempts fail.    | `retry`, `recover`, `Failure`           |        2.5 |
| [Concurrent Service Checks](https://github.com/jigmd/sley/tree/main/cookbook/typescript-batch)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-batch/README.md)                                  | Check services concurrently and combine terminal outputs once.       | `emit`, `end`, `combine`                |        5.5 |
| [Concurrent Nested Workers](https://github.com/jigmd/sley/tree/main/cookbook/typescript-nested-flow)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-nested-flow/README.md)                      | Run a multi-step nested worker concurrently and combine its results. | `nested Flow`, `concurrency`, `combine` |          4 |
| [Recovering a Partially Completed Batch](https://github.com/jigmd/sley/tree/main/cookbook/typescript-resilient-batch)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-resilient-batch/README.md) | Recover a partial batch from settled terminal records.               | `ScopeFailure`, `terminals`, `recover`  |          6 |

## Agents and integrations

| Project                                                                                                                                                                                                                       | What it teaches                                                         | Sley mechanisms                            | Complexity |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------ | ---------: |
| [Terminal Chat](https://github.com/jigmd/sley/tree/main/cookbook/typescript-chat)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-chat/README.md)                                            | Type shared state in a one-node loop with deliberate hard termination.  | `unlabelled link`, `end`, `maxActivations` |        3.5 |
| [Search Agent](https://github.com/jigmd/sley/tree/main/cookbook/typescript-agent)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-agent/README.md)                                           | Type state and branch input across a bounded search loop.               | `emit`, `input`, `maxActivations`          |         11 |
| [MCP Tool Discovery and Execution](https://github.com/jigmd/sley/tree/main/cookbook/typescript-mcp)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-mcp/README.md)                           | Discover, validate, and invoke one MCP tool in a linear Flow.           | `async handler`, `input`, `validation`     |        5.5 |
| [Orchestrator and Workers](https://github.com/jigmd/sley/tree/main/cookbook/typescript-orchestrator-workers)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-orchestrator-workers/README.md) | Freeze a dynamic plan, fan sections out, and integrate the results.     | `emit`, `input`, `combine`                 |        4.5 |
| [A Bounded Quality Loop](https://github.com/jigmd/sley/tree/main/cookbook/typescript-quality-loop)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-quality-loop/README.md)                   | Compose benchmarked component loops, integration, and final evaluation. | `nested Flow`, `combine`, `maxActivations` |          7 |
