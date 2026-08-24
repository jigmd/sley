---
complexity: 4
---

# Sequential Batch Translation

`dispatch` emits one `(text, language)` input for every requested translation.
Those emissions create independent branches, but `Flow(dispatch)` has the
default concurrency of one, so the translator handles them sequentially.

Each worker calls `end()` after writing its file. That ends only that branch;
the other translations continue until the Flow has no live work.

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
