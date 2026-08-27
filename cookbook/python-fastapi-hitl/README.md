---
complexity: 8
---

# Web Human Review

A FastAPI application that pauses a Sley Flow until a user approves or
rejects its output.

`review` waits on an `asyncio.Event`. The feedback endpoint stores the decision
and sets that event; the node then emits either `"approved"` or `"rejected"`.
Rejected work must include revision instructions. Those instructions change the
next `process` result, so the loop demonstrates repair rather than repeating the
same computation. The application permits three revisions and the Flow has an
independent activation backstop.

The server and Flow share one nested review channel. Sley copies the
top-level initial state when the run starts, but nested values remain shared, so
the HTTP endpoint can safely signal the waiting node.

## Run

```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Open `http://127.0.0.1:8000`, submit text, then approve or reject the result.

This teaching app keeps task state in one process. A deployed service would also
need persistent task storage, expiry, authentication, disconnect/cancellation
policy, and limits shared across workers.
