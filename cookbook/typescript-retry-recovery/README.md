---
complexity: 2.5
---

# Retry and Recovery in TypeScript

This example runs the same summarizer twice. A transient service succeeds on its
third attempt; a permanent failure exhausts the same retry policy and uses the
node's `recover` callback to provide a fallback.

Retries repeat the complete handler, so validation and non-repeatable side
effects should happen outside the retryable section. Recovery must make an
explicit control call to replace the failure; here `emit()` lets the leaf finish
normally after storing a fallback in state.

## Run

```bash
npm install
npm start
```
