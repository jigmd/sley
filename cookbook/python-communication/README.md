---
complexity: 4
---

# Shared Run State

This word counter shows how nodes communicate through `context.state`.
`read_text` initializes a nested statistics dictionary, `count_words` updates
it, and `show_stats` reads it before linking back for another input.

All nodes in one run see the same top-level state object. Caskada shallow-copies
the initial dictionary when `run()` starts and returns the run-owned state when
the Flow finishes.

## Run

```bash
pip install -r requirements.txt
python main.py
```

Enter text to update the totals, or `q` to finish the Flow.
