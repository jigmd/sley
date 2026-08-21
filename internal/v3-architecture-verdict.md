# V3 Architecture Verdict

- Status: lean runtime accepted; implementation in progress
- Date: 2026-08-21
- Authority: [RFC 0001](rfcs/0001-caskada-v3-runtime.md)

## Verdict

V3 is a structured graph runner, not a general workflow operating system. The
accepted runtime consists of graph definition and compilation, shared state and
branch input, buffered `emit` / `end`, Flow-local concurrency, terminals,
combine, retry, recovery, and completed or failed run results.

The previous D10 implementation attempted to specify scheduler observation,
global admission and fairness, resource-limit matrices, deadlines, callback
timeouts, cancellation fences, grace periods, and abandonment. Those features
were not required by the author API and made the core substantially harder to
understand. D10 is superseded and is not an implementation base.

## Simplicity Boundary

The public facade contains contracts and delegation only. The graph runner is
the strictest production-code budget in the repository. Tests may be extensive,
and cookbook examples may retain detail that teaches a lesson; neither expands
the shipped runtime contract.

New runtime machinery requires a demonstrated requirement or measured limit and
a separate RFC. No scaffolding for a hypothetical feature belongs in v3.

## Accepted Module Shape

Each port keeps four responsibilities visible:

1. public contracts and facade;
2. inert graph definition, compilation, and description;
3. native shallow state capture;
4. one activation and Flow-scope runner.

Standard-library and platform collections, queues, tasks, and timers take
precedence over custom equivalents. Invalid public input and impossible runtime
states fail immediately.

## Current Evidence

Both ports implement the lean contract in five files. Python passes runtime,
Ruff, strict mypy, Pyright, sdist, and wheel checks. TypeScript passes runtime,
strict declarations, ESM, CommonJS, and package-build checks. Shared conformance
and repository author documentation still target parts of the superseded
contract, so v3 is not release-ready.
