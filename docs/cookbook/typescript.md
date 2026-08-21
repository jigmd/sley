---
title: 'TypeScript Examples'
machine-display: false
---

# TypeScript Examples

The TypeScript projects use the same v3 control and runtime model as the Python
examples. Their state and handler types are collected in `types.ts` so readers
can focus on graph code first.

| Project                                                                                | Complexity | Primary lesson                                             |
| -------------------------------------------------------------------------------------- | ---------: | ---------------------------------------------------------- |
| [Terminal Chat](https://github.com/skadaai/caskada/tree/main/cookbook/typescript-chat) |        3.5 | A typed one-node self-loop and deliberate `end()`          |
| [Search Agent](https://github.com/skadaai/caskada/tree/main/cookbook/typescript-agent) |         11 | Typed state, named routes, a search loop, and final answer |

Both projects run their real Caskada graph in cookbook verification with
test-owned provider fakes.

See the [complexity rubric](./points.md) for how cognitive load is estimated and
[Python Examples](./python.md) for the broader pattern catalog.
