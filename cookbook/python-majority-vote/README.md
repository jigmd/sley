---
complexity: 6
---

# Majority Vote Reasoning

The dispatcher emits several copies of one question. Each solver branch calls
`end(answer)`, publishing an answer as a terminal output.

After every branch settles, the Flow's `combine=` callback runs once. It reads
`result.outputs`, chooses the most frequent answer, stores it in shared state,
and calls `end(best_answer)`. That final call replaces the many worker terminals
with one aggregate terminal.

## Run

```bash
export ANTHROPIC_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py --tries 5
```
