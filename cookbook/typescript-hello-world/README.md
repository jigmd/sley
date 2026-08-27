---
complexity: 1
---

# TypeScript Hello World

This smallest TypeScript example creates one typed node, updates shared run
state, and lets an ordinary leaf finish the Flow.

The handler does not need `emit()` or `end()`. With no outgoing link, its normal
return is the successful end of that branch. `run()` resolves to the completed
state, including the greeting written by the node.

## Run

```bash
npm install
npm start
```
