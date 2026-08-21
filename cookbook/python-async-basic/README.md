---
complexity: 7
---

# Async Recipe Finder

This example uses ordinary `async` handlers for three kinds of waiting:

1. Collect an ingredient from the user.
2. Fetch recipes and ask an LLM for a suggestion.
3. Ask whether to accept it or follow the `retry` link.

The handlers read and write the shared run state just like synchronous handlers.
`approve` emits only when retrying; a successful return with no emission exits
the Flow normally.

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
