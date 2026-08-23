---
title: 'TypeScript Examples'
machine-display: false
---

# TypeScript Examples

The TypeScript projects use the same Sley control and runtime model as the Python
examples. Their state and handler types are collected in `types.ts` so readers
can focus on graph code first.

| Project                                                                                               | Complexity | Primary lesson                                             |
| ----------------------------------------------------------------------------------------------------- | ---------: | ---------------------------------------------------------- |
| [Terminal Chat](https://github.com/jigmd/sley/tree/main/cookbook/typescript-chat)                     |        3.5 | A typed one-node self-loop and deliberate `end()`          |
| [Search Agent](https://github.com/jigmd/sley/tree/main/cookbook/typescript-agent)                     |         11 | Typed state, named routes, a search loop, and final answer |
| [Concurrent Service Checks](https://github.com/jigmd/sley/tree/main/cookbook/typescript-batch)        |        5.5 | Fan-out, local concurrency, `end(value)`, and `combine`    |
| [Partial Batch Recovery](https://github.com/jigmd/sley/tree/main/cookbook/typescript-resilient-batch) |          6 | Flow recovery with settled branch terminals                |

Every project runs its real Sley graph in cookbook verification. External
providers are replaced by test-owned fakes where needed.

See the [complexity rubric](./points.md) for how cognitive load is estimated and
[Python Examples](./python.md) for the broader pattern catalog.
