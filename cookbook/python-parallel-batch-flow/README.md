---
complexity: 7
---

# Sequential and Parallel Nested Flows

This example builds the same reusable image-processing Flow twice. One outer
Flow has `concurrency=1`; the other has `concurrency=9`.

Each emitted image/filter input starts a nested Flow:

```text
load -> apply filter -> save -> end(path)
```

The graph and handlers do not change between the sequential and parallel runs.
Only the owning Flow's local concurrency cap changes. Fresh node occurrences are
created for each graph because links belong to occurrences, not handler
functions.

Image reads, transforms, and writes use `asyncio.to_thread`, so async handlers
yield while blocking library work runs outside the event-loop thread. Increasing
Flow concurrency would not create useful overlap if those calls blocked the
event loop directly.

## Run

```bash
pip install -r requirements.txt
python main.py
```
