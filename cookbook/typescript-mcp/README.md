---
complexity: 5.5
---

# MCP Tool Discovery and Execution

This example connects a Sley Flow to a local MCP server over stdio:

```text
discover tools -> choose one -> call it -> validate result
```

The server uses a Zod input schema, so the MCP SDK validates arguments before
the tool handler runs. The client separately checks the tool-level error flag
and requires a text content block before committing the answer to run state.

Tool selection is deterministic here to keep the integration provider-free. In
a model-backed host, pass the discovered tool definitions to the model, validate
its selected name and arguments, then keep the same execution node.

The stdio transport owns the child server. `client.close()` in `finally` ensures
that the process is released even when the Flow fails. The server logs only to
stderr because stdout belongs to the MCP protocol.

## Run

```bash
npm install
npm start
```
