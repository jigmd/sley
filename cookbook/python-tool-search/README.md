---
complexity: 5
---

# Web Search with Analysis

This linear Flow separates orchestration from tools:

1. `search` calls SerpAPI and stores the results.
2. Its unlabelled link runs `analyze`, which asks an LLM for a YAML summary.

The Sley handlers in `nodes.py` make the workflow visible; API-specific code
stays in `tools/`.

## Run

```bash
export SERPAPI_API_KEY="your-serpapi-key"
export OPENAI_API_KEY="your-openai-key"
pip install -r requirements.txt
python main.py
```
