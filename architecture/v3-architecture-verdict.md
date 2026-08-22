# V3 Architecture Verdict

- Status: lean runtime accepted and independently reviewed
- Date: 2026-08-22
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

Each port keeps five responsibilities visible:

1. public contracts and facade;
2. inert graph definition, compilation, and description;
3. callback-local control validation and intent buffering;
4. native shallow state capture;
5. one activation and Flow-scope runner.

Standard-library and platform collections, queues, tasks, and timers take
precedence over custom equivalents. Invalid public input and impossible runtime
states fail immediately.

## Intentional Tradeoffs

These are accepted simplicity boundaries and should be checked before treating
related reports as runtime defects:

- **Bounded-wave concurrency:** each Flow admits up to its local `concurrency`
  limit and waits for that wave before admitting more. The contract guarantees
  an upper bound, not work-conserving scheduling or fairness. Improving
  utilization requires measured need and must preserve the small runner.
- **Host-language data behavior:** Caskada validates control, not application
  schemas. Missing Python mapping keys raise `KeyError`; missing TypeScript
  properties normally produce `undefined`. Applications validate trust
  boundaries rather than the runtime imposing proxies or cross-link schemas.
- **Host-language invalid-call behavior:** portable control calls have the same
  meaning, but invalid Python arity is a native `TypeError` while TypeScript
  validates dynamic arguments as `invalid_outcome`. Invalid calls are outside
  the portable author contract.
- **Borrowed mutable state and effects:** only the initial top-level state is
  shallow-copied. Nested references remain shared, concurrent writes require
  application coordination, and retries do not roll back state or external
  effects.
- **Application-owned operations:** provider timeouts, shared rate limits,
  logging, persistence, and cancellation use host-language or service-client
  facilities. Their absence from Caskada is intentional unless concrete usage
  justifies a separate RFC.
- **TypeScript Promise assimilation:** `run()` temporarily masks an application
  state field named `then` when it is callable. Making that callable property
  immutable before completion makes `run()` reject; `start().result()` remains
  available without Promise-projecting the state itself.

## Current Evidence

Both ports implement the lean contract in six files. Python passes runtime,
Ruff, strict mypy, Pyright, sdist, and wheel checks. TypeScript passes runtime,
strict declarations, ESM, CommonJS, and package-build checks. Nineteen exact
shared scenarios pass through both public packages. Author documentation now
matches the retained surface. The previously verified 38 cookbook contracts are
unchanged, and three added batch examples pass isolated installation runs.
Three independent critics found no blocker or major issue in revision
`96a0bff508e3389979f58554149391257fb457ef`.
