# Design Patterns

Sley does not ship separate Agent, RAG, MapReduce, or Supervisor classes.
Those patterns are graph shapes built from the same small runtime model.

| Pattern                           | Graph Shape                              | Main Data Channel                                 |
| --------------------------------- | ---------------------------------------- | ------------------------------------------------- |
| [Workflow](workflow.md)           | Linear or conditional links              | Shared state                                      |
| [Agent](agent.md)                 | Decision node with tool loops            | State plus named actions                          |
| [RAG](rag.md)                     | Indexing Flow followed by retrieval Flow | State for durable index, input/output for batches |
| [Map Reduce](mapreduce.md)        | Dispatch fan-out plus Flow combine       | Branch input and terminal output                  |
| [Structured Output](structure.md) | Parse before committing state/control    | Validated application value                       |
| [Multi-Agent](multi_agent.md)     | Nested role Flows and supervision links  | Explicit role messages and shared facts           |

Choose a graph shape because it matches the problem, not because the runtime
requires a named pattern. The [cookbook](../../cookbook/) contains complete
examples and deliberately keeps application/provider helpers outside Sley.
