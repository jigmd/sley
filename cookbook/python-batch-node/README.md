---
complexity: 4.5
---

# Combine CSV Chunks

This example processes a sales CSV in chunks and combines their statistics into
one result.

## Run

```bash
pip install -r requirements.txt
python main.py
```

## What This Example Demonstrates

1. `dispatch_chunks` emits one branch input for each CSV chunk.
2. `process_chunk` calls `end(value)` to publish one output from its branch.
3. `combine_chunks` receives those values in `result.outputs` and sums them.
4. Its single `emit()` replaces all worker terminals with one continuation, so
   `show_stats` runs once.

`end(value)` ends only that worker branch. It does not stop sibling workers or
the whole run. The Flow's `combine` callback runs after every branch in that Flow
has settled. The outer Flow gives the combiner's single continuation a
`show_stats` node to follow.

```mermaid
flowchart LR
    Dispatch[dispatch_chunks] -->|chunk x N| Process[process_chunk]
    Process -->|end statistics| Combine[combine_chunks]
    Combine -->|one continuation| Show[show_stats]
```

## Files

- [`main.py`](./main.py): Runs the example
- [`flow.py`](./flow.py): Builds the fan-out Flow and defines its combiner
- [`nodes.py`](./nodes.py): Contains the three small handler functions
- [`data/sales.csv`](./data/sales.csv): Sample sales data
