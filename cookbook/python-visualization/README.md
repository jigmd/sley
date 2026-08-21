---
complexity: 7
---

# Flow Visualization

Generate Mermaid text and an interactive D3 graph from a compiled Caskada
Flow.

The important API is:

```python
description = flow.compile().describe()
```

`describe()` returns stable element IDs, scopes, and links. The
visualizer converts that public data to JSON instead of inspecting live Node or
Flow internals.

The sample order pipeline contains three linked subflows. Each subflow's leaf
emits nothing, so its normal exit follows the enclosing unlabelled link to the
next subflow.

Running the example writes both a Mermaid view for quick inspection and an
interactive D3 view for exploring element and scope metadata. The visualization
logic is intentionally more substantial than the sample graph: translating the
portable description into useful developer tooling is the example's lesson.

## Run

```bash
pip install -r requirements.txt
python visualize.py
```
