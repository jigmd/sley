---
complexity: 3
---

# Retry and Recovery

This example summarizes text with one function-backed node. It shows the two
policies commonly attached to a node occurrence:

- `RetryPolicy(max_attempts=3)` retries a failed handler up to three total
  attempts.
- `recover=` runs after retry is declined or exhausted. Its `emit()` marks the
  failure handled and lets the Flow finish normally.

Retries repeat the whole handler, so perform validation before state changes or
external effects when those operations are not safe to repeat.

This is the second typed Python example after `python-hello-world`. Its small
state definition lives in `models.py`, leaving retry and recovery visible in
`flow.py`.

## Run

```bash
pip install -r requirements.txt
python main.py
```

Set your OpenAI API key in `utils/call_llm.py` before running against the live
service.
