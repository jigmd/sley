---
complexity: 4
---

# Concurrent Nested Workers

This example fans three jobs into the same nested worker Flow:

```text
dispatch --job--> [load -> transform -> save -> end(result)]
                         nested worker x 3
                                  |
                               combine -> report
```

The worker keeps its multi-step lifecycle together. The owning Flow admits two
worker branches at a time, then `combine` replaces their terminals with one
sorted result list for the report node. Only the combiner writes shared results,
which avoids concurrent state updates inside workers.

## Run

```bash
npm install
npm start
```
