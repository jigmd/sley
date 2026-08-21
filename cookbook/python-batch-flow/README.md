---
complexity: 6
---

# Reusing a Flow for Batch Work

The dispatcher emits nine image/filter jobs into one nested `process_image`
Flow. Each nested invocation runs the same three handlers:

```text
load -> apply filter -> save
```

The job and intermediate image travel through `context.input`; shared run state
is unnecessary. Each save calls `end(path)`, ending that worker branch and
recording its output. The outer Flow uses concurrency one, so jobs run in order.

## Run

```bash
pip install -r requirements.txt
python main.py
```
