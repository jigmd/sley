---
title: 'Python Examples'
machine-display: false
---

# Python Examples

The [cookbook](https://github.com/jigmd/sley/tree/main/cookbook) teaches one
pattern at a time. Start with the smallest example that introduces the concept
you need; complexity metadata is a rough navigation aid, not a quality score.

## Start Here

| Project                                                                                    | Complexity | Primary lesson                                  |
| ------------------------------------------------------------------------------------------ | ---------: | ----------------------------------------------- |
| [Hello World](https://github.com/jigmd/sley/tree/main/cookbook/python-hello-world)         |        2.5 | `@node`, state, and a normal zero-emission leaf |
| [Retry and Recovery](https://github.com/jigmd/sley/tree/main/cookbook/python-node)         |          3 | Node retry and local recovery                   |
| [Text Converter Flow](https://github.com/jigmd/sley/tree/main/cookbook/python-flow)        |          4 | Unlabelled links and deliberate `end()`         |
| [Shared Run State](https://github.com/jigmd/sley/tree/main/cookbook/python-communication)  |          4 | Communication through `context.state`           |
| [Article Workflow](https://github.com/jigmd/sley/tree/main/cookbook/python-workflow)       |        6.5 | A readable three-node linear workflow           |
| [Async Recipe Finder](https://github.com/jigmd/sley/tree/main/cookbook/python-async-basic) |        4.5 | Async handlers and ordinary awaited I/O         |

## Branching, Loops, and Combining

| Project                                                                                                             | Complexity | Primary lesson                              |
| ------------------------------------------------------------------------------------------------------------------- | ---------: | ------------------------------------------- |
| [Sequential Batch Translation](https://github.com/jigmd/sley/tree/main/cookbook/python-batch)                       |          4 | Repeated emissions with serial scheduling   |
| [Combine CSV Chunks](https://github.com/jigmd/sley/tree/main/cookbook/python-batch-node)                            |        4.5 | Worker `end(value)` and Flow combine        |
| [Parallel Batch Translation](https://github.com/jigmd/sley/tree/main/cookbook/python-parallel-batch)                |          5 | The same fan-out with local concurrency     |
| [Reusable Batch Flow](https://github.com/jigmd/sley/tree/main/cookbook/python-batch-flow)                           |          6 | Reusing a nested Flow for branch work       |
| [Sequential and Parallel Nested Flows](https://github.com/jigmd/sley/tree/main/cookbook/python-parallel-batch-flow) |          7 | Local nested-scope concurrency              |
| [Majority Vote](https://github.com/jigmd/sley/tree/main/cookbook/python-majority-vote)                              |          6 | Combining several terminal outputs          |
| [Explicit Map/Reduce](https://github.com/jigmd/sley/tree/main/cookbook/python-map-reduce)                           |          8 | Map and Reduce as visible application nodes |
| [Nested Batch](https://github.com/jigmd/sley/tree/main/cookbook/python-nested-batch)                                |        9.5 | Two levels of scoped fan-out and combine    |
| [Partial Batch Recovery](https://github.com/jigmd/sley/tree/main/cookbook/python-resilient-batch)                   |          6 | Flow recovery with settled branch terminals |

## Agents and Reasoning

| Project                                                                                   | Complexity | Primary lesson                                        |
| ----------------------------------------------------------------------------------------- | ---------: | ----------------------------------------------------- |
| [Research Agent](https://github.com/jigmd/sley/tree/main/cookbook/python-agent)           |          7 | Named decisions, search loop, and answer path         |
| [Chain of Thought](https://github.com/jigmd/sley/tree/main/cookbook/python-thinking)      |          7 | A bounded reasoning self-loop and whole-handler retry |
| [Multi-Agent Taboo](https://github.com/jigmd/sley/tree/main/cookbook/python-multi-agent)  |          7 | Independent Flows communicating through queues        |
| [MCP Tools](https://github.com/jigmd/sley/tree/main/cookbook/python-mcp)                  |          8 | Tool discovery, selection, and execution              |
| [Research Supervisor](https://github.com/jigmd/sley/tree/main/cookbook/python-supervisor) |         13 | Nested Flow exits and supervisor retry                |
| [Agent-to-Agent Adapter](https://github.com/jigmd/sley/tree/main/cookbook/python-a2a)     |         12 | Exposing a Flow through an external task protocol     |

## Retrieval and Structured Data

| Project                                                                                           | Complexity | Primary lesson                              |
| ------------------------------------------------------------------------------------------------- | ---------: | ------------------------------------------- |
| [Structured Output](https://github.com/jigmd/sley/tree/main/cookbook/python-structured-output)    |          3 | Parse and validate before committing state  |
| [SQLite Tool](https://github.com/jigmd/sley/tree/main/cookbook/python-tool-database)              |          5 | A linear database workflow                  |
| [Text to SQL](https://github.com/jigmd/sley/tree/main/cookbook/python-text2sql)                   |          8 | Schema inspection and a repair loop         |
| [Chat with Memory Retrieval](https://github.com/jigmd/sley/tree/main/cookbook/python-chat-memory) |          7 | Recent history plus vector retrieval        |
| [RAG](https://github.com/jigmd/sley/tree/main/cookbook/python-rag)                                |         16 | Offline indexing and online retrieval Flows |

## Tools and Media

| Project                                                                                      | Complexity | Primary lesson                                   |
| -------------------------------------------------------------------------------------------- | ---------: | ------------------------------------------------ |
| [OpenAI Embeddings](https://github.com/jigmd/sley/tree/main/cookbook/python-tool-embeddings) |          3 | Keeping a provider call outside graph definition |
| [Web Search](https://github.com/jigmd/sley/tree/main/cookbook/python-tool-search)            |          5 | Linear search and analysis tools                 |
| [PDF Vision Batch](https://github.com/jigmd/sley/tree/main/cookbook/python-tool-pdf-vision)  |          6 | Page fan-out and vision extraction               |
| [Web Crawler](https://github.com/jigmd/sley/tree/main/cookbook/python-tool-crawler)          |        9.5 | Crawl, analyze, combine, and report              |
| [LLM Streaming](https://github.com/jigmd/sley/tree/main/cookbook/python-llm-streaming)       |          4 | Provider streaming and user interruption         |
| [Voice Chat](https://github.com/jigmd/sley/tree/main/cookbook/python-voice-chat)             |          7 | Speech input, response, and playback loop        |
| [Flow Visualization](https://github.com/jigmd/sley/tree/main/cookbook/python-visualization)  |          7 | Rendering `compile().describe()` topology        |

## Interactive Applications

| Project                                                                                          | Complexity | Primary lesson                                    |
| ------------------------------------------------------------------------------------------------ | ---------: | ------------------------------------------------- |
| [Simple Chat](https://github.com/jigmd/sley/tree/main/cookbook/python-chat)                      |          3 | One node with a named self-link                   |
| [Travel Chat Guardrail](https://github.com/jigmd/sley/tree/main/cookbook/python-chat-guardrail)  |          5 | Validation before a model call                    |
| [Streamlit Human Review](https://github.com/jigmd/sley/tree/main/cookbook/python-streamlit-hitl) |          4 | UI-owned staged human review                      |
| [FastAPI Human Review](https://github.com/jigmd/sley/tree/main/cookbook/python-fastapi-hitl)     |          8 | Waiting for external approval in an async handler |

The projects intentionally mix typed and untyped code. Types live in one file
when they clarify the lesson; they are omitted when they would obscure it.

See the [complexity rubric](./points.md) for how cognitive load is estimated.
