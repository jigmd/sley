---
complexity: 12
---

# External Task Protocol Adapter

This example exposes a Sley research agent through a bundled, educational
JSON-RPC task protocol. The important integration point is `SleyTaskManager`:

1. Extract the question from the incoming A2A task.
2. Run the ordinary Sley Flow.
3. Read the answer from the state returned by `run()`.
4. Publish that answer as an A2A artifact.

The `common/` package contains the protocol types and HTTP infrastructure. The
Sley workflow remains independent in `nodes.py` and `flow.py`.

The example intentionally keeps the protocol adapter substantial. A2A task
creation, status updates, and artifacts are the lesson; reducing the project to
only the Flow would hide the boundary that a real external caller uses.

The bundled `common/` code is a narrow teaching fixture, not an official A2A SDK
or a claim of current protocol conformance. For an interoperable service, keep
the Sley boundary shown here but implement the transport with the official SDK
and its conformance tests.

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
