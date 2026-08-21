---
complexity: 7
---

# Research Agent

This agent has three function-backed nodes:

```text
decide --search--> search --decide--> decide
   |
   +--answer--> answer
```

The decision node validates the LLM's YAML before emitting a named action.
Search results accumulate in shared run state. The answer node emits nothing,
so it exits the Flow normally and `run()` returns the final state.

Open [the Colab tutorial](https://colab.research.google.com/github/skadaai/caskada/blob/main/cookbook/python-agent/demo.ipynb)
to build and run the same agent one step at a time in the browser. Run
`python utils.py` locally to try the LLM and search integrations without the
Flow.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
python main.py --"What is quantum computing?"
```
