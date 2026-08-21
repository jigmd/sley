---
complexity: 3
---

# Structured Output

This single-node Flow asks an LLM for YAML, parses it, validates the required
shape, and only then stores the result in `context.state`.

The node uses `RetryPolicy(max_attempts=3)`. V3 retries the whole handler, so the
validation happens before the state write. A malformed response can be retried
without publishing partial structured data.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```

Edit `data.txt` to try another resume.
