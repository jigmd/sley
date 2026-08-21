---
complexity: 5
---

# SQLite Tool

Three nodes form a linear database workflow:

1. Initialize the SQLite schema.
2. Insert one task with bound query parameters.
3. Read the tasks into the final run state.

The SQLite functions stay in `tools/database.py`; the Caskada handlers only
adapt shared state to those tool calls. Successful handlers emit nothing, so
each follows its unlabelled link automatically.

## Run

```bash
pip install -r requirements.txt
python main.py
```
