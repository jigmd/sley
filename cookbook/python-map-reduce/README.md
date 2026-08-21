---
complexity: 8
---

# Resume Qualification with Map/Reduce

This project keeps Map and Reduce visible because that pattern is the lesson:

1. `map_resumes` emits one branch input per resume.
2. Each evaluator publishes `(filename, evaluation)` with `end(value)`.
3. The map Flow's `combine=` callback waits for all evaluators and emits one
   dictionary downstream.
4. `reduce_results` computes the final summary once.

The combiner supplies synchronization; no shared counters or generic map/reduce
base classes are needed.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
