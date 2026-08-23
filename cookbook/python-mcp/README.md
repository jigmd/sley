---
complexity: 8
---

# Model Context Protocol Tools

An agent that discovers math tools from an MCP server, asks an LLM which tool
to use, then executes the selected tool.

Both MCP calls are asynchronous. `discover_tools` stores the server's tool
descriptions in run state; `decide_tool` sends one decision through
`context.input`; `execute_tool` publishes the answer in state and exits normally.

## Where MCP Ends and Sley Begins

`simple_server.py` owns the external tool protocol and exposes `add` and
`multiply`. The Sley Flow owns application order: discover the available
tools, ask the model for a structured selection, then execute exactly that tool.
This separation makes it possible to inspect the MCP server independently while
keeping graph control visible in `main.py`.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```

`simple_server.py` is started automatically over MCP's standard-input
transport.
