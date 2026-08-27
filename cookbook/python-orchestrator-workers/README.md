---
complexity: 10
---

# Orchestrator–Workers–Editor

A lead model creates a foundation and a dynamic section plan for a comparison
brief. Sley fans those sections out to independent workers, waits for every
section, and sends the assembled result through one integration editor.

```text
plan --> worker Flow: dispatch --> write
                    \-- combine --> editor
```

The planner runs before fan-out because every worker must agree on the audience,
thesis, and terminology. It returns section-specific goals and allowed source
IDs rather than vague roles. Each worker receives one section as branch input
and publishes its draft with `end(value)`; the Flow combiner owns synchronization
and forwards the ordered sections to the editor.

The source pack, model calls, and citation policy remain ordinary application
concerns. Sley owns only the visible plan, fan-out, join, and integration path.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
