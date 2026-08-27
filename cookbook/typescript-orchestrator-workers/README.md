---
complexity: 4.5
---

# Orchestrator and Workers

This example separates dynamic planning, parallel section work, and final
integration:

```text
plan -> dispatch --section x N--> write -> end(section)
                              workers combine -> edit
```

The planner freezes a small shared foundation and derives section tasks from the
requested topic. The dispatcher passes each task as branch input to a worker
Flow. Workers do not mutate shared results; they publish independently judgeable
sections with `end(section)`. The combiner sorts those sections and emits one
continuation to the editor.

The local writing functions are deterministic. They can be replaced with model
calls without changing the graph or the ownership boundaries.

## Run

```bash
npm install
npm start
```
