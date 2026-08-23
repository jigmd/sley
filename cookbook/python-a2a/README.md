---
complexity: 12
---

# Agent-to-Agent Adapter

This example exposes a Sley research agent through the A2A JSON-RPC
protocol. The important integration point is `SleyTaskManager`:

1. Extract the question from the incoming A2A task.
2. Run the ordinary Sley Flow.
3. Read the answer from the state returned by `run()`.
4. Publish that answer as an A2A artifact.

The `common/` package contains the protocol types and HTTP infrastructure. The
Sley workflow remains independent in `nodes.py` and `flow.py`.

The example intentionally keeps the protocol adapter substantial. A2A task
creation, status updates, and artifacts are the lesson; reducing the project to
only the Flow would hide the boundary that a real external caller uses.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python a2a_server.py --port 10003
```

In another terminal:

```bash
python a2a_client.py --agent-url http://localhost:10003
```
