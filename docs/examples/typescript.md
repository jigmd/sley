---
description: Browse complete TypeScript projects by learning goal, Sley mechanism, and cognitive complexity.
---

# TypeScript Examples

Do not choose by ambition. Choose the smallest project that answers your next
question, run it, and change one behavior. Complexity estimates cognitive load,
not quality; lower is usually the more useful starting point.

## TypeScript projects

| Project                                                                                                                                                                                                                           | What it teaches                                                        | Sley mechanisms                        | Complexity |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | -------------------------------------- | ---------: |
| [Terminal Chat](https://github.com/jigmd/sley/tree/main/cookbook/typescript-chat)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-chat/README.md)                                                | Type shared state in a one-node loop with deliberate hard termination. | `named link`, `state`, `end`           |        3.5 |
| [Concurrent Service Checks](https://github.com/jigmd/sley/tree/main/cookbook/typescript-batch)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-batch/README.md)                                  | Check services concurrently and combine terminal outputs once.         | `emit`, `end`, `combine`               |        5.5 |
| [Recovering a Partially Completed Batch](https://github.com/jigmd/sley/tree/main/cookbook/typescript-resilient-batch)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-resilient-batch/README.md) | Recover a partial batch from settled terminal records.                 | `ScopeFailure`, `terminals`, `recover` |          6 |
| [Search Agent](https://github.com/jigmd/sley/tree/main/cookbook/typescript-agent)<br>[Read the lesson](https://github.com/jigmd/sley/blob/main/cookbook/typescript-agent/README.md)                                               | Type state and branch input across a bounded search loop.              | `emit`, `input`, `maxActivations`      |         11 |
