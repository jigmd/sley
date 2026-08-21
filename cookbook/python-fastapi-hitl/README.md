---
complexity: 8
---

# Web Human Review

A FastAPI application that pauses a Caskada Flow until a user approves or
rejects its output.

`review` waits on an `asyncio.Event`. The feedback endpoint stores the decision
and sets that event; the node then emits either `"approved"` or `"rejected"`.
Rejected work loops back to `process`.

The server and Flow share one nested review channel. Caskada copies the
top-level initial state when the run starts, but nested values remain shared, so
the HTTP endpoint can safely signal the waiting node.

## Run

```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Open `http://127.0.0.1:8000`, submit text, then approve or reject the result.
