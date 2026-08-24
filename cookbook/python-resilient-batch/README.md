---
complexity: 6
---

# Recovering a Partially Completed Batch

This example imports three records in order. The first succeeds, the second has
an invalid amount, and the third is never started after the Flow fails.

The worker publishes each successful import with `end(value)`. When the next
worker raises, the Flow's `recover=` callback receives a `ScopeFailure` whose
`terminals` contain the already-completed import. Recovery keeps that result and
calls `end(summary)`, explicitly replacing the failure with one successful batch
terminal.

The example uses `start(...).result()` instead of the everyday `run()` shortcut
so the final `Completed` or `Failed` status and terminals remain visible.

```text
record 1 -> end(imported record)
record 2 -> failure
record 3 -> not admitted
                 |
                 v
              recover -> end(partial summary)
```

## Run

```bash
pip install -r requirements.txt
python main.py
```

Removing the recovery control call would leave the failure unhandled and produce
a `Failed` result instead.
