---
complexity: 4.5
---

# Async Recipe Finder

This example uses ordinary `async` handlers for real local I/O:

1. Collect an ingredient from the terminal without blocking the event loop.
2. Read a local recipe catalog without blocking the event loop.
3. Ask whether to accept the suggestion or follow the `retry` link.

The Flow deliberately mixes async I/O handlers with a synchronous suggestion
handler. All of them read and write the same run state. `approve` emits only
when retrying; a successful return with no emission exits the Flow normally.

```python
fetch.link(suggest, "suggest")
suggest.link(approve, "approve")
approve.link(suggest, "retry")
```

## Run

```bash
pip install -r requirements.txt
python main.py
```
