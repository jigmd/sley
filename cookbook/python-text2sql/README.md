---
complexity: 8
---

# Text to SQL

A Flow that reads a SQLite schema, asks an LLM for SQL, executes it, and asks
the LLM to repair failed queries.

The normal path uses unlabelled links:

```text
get_schema --> generate_sql --> execute_sql
```

An SQLite error emits `"debug"`; the corrected query follows another
unlabelled link back to `execute_sql`. A successful execution emits nothing, so
it leaves the Flow normally. The application-level attempt count prevents an
endless repair loop.

## Why the Repair Loop Is Visible

Generating valid SQL is application behavior, not a transient handler failure.
The failed SQL and SQLite error become input to `debug_sql`, and the repaired
query returns to the normal execution node. Keeping that loop in the graph lets
readers see the attempted query and decide how many repairs the application
allows; a runtime retry would simply repeat the same model call without this
extra context.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py "total products per category"
```
