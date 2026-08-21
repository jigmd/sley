---
complexity: 5
---

# Parallel Batch Translation

This is the concurrent counterpart to `python-batch`. The graph is the same:
one dispatcher emits eight branch inputs and each translator ends its own branch
after writing a file.

The difference is local to the Flow definition:

```python
translation_flow = Flow(dispatch, concurrency=8)
```

The runtime-wide callback ceiling is derived from the compiled topology unless
the caller supplies a smaller `RunOptions.max_concurrency`.

The generated translations are intentionally not checked into the repository:
they describe whichever README version was translated and become stale quickly.
Running the example creates eight `translations/README_*.md` files; cookbook
verification checks that all eight are produced in an isolated project copy.

## Run

```bash
export ANTHROPIC_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
