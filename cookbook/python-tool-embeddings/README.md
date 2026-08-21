---
complexity: 3
---

# OpenAI Embeddings

This example keeps the OpenAI call in `tools/embeddings.py` and wraps it with a
single Caskada handler. The handler reads text from `context.state` and stores
the embedding in the same run state. `run()` returns that final state to the
caller.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
