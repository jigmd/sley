---
complexity: 2.5
---

# Inspect a Compiled Flow

`compile().describe()` returns a portable description of a Flow's scopes,
elements, and links. This example reads that public data before running the same
compiled graph.

The description is useful for visualizers, diagnostics, and tooling. It is not
a live view of mutable Node or Flow internals. `start().result()` then exposes
the run's explicit `completed` or `failed` status; use the simpler `run()` when
only completed state is needed.

## Run

```bash
npm install
npm start
```
