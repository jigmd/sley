---
complexity: 7
---

# A Bounded Quality Loop

This capstone combines a concrete benchmark, parallel component loops, an
integration editor, and a whole-artifact evaluator:

```text
set bar -> component Flow x N -> combine -> integrate -> judge
                ^      |                              |      |
                |revise|                              <-revise
                +------+                              ->approved/stopped
```

Each builder receives one required phrase from the same checked-in quality bar.
Its evaluator returns an actionable gap and sends the branch back once before
accepting it. Only accepted component outputs reach the combiner. The integration
judge then requests one whole-artifact revision before declaring parity.

The domain rules cap component and integration attempts. Both cyclic scopes also
set `maxActivations` as a runtime backstop. The deterministic benchmark makes the
stopping behavior observable; production systems can replace the local builders
and evaluators with models, tests, retrieval, or other external evidence.

## Run

```bash
npm install
npm start
```
