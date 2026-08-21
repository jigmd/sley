# TypeScript Runtime

## Purpose

- Implement the accepted Caskada v3 contract for TypeScript and JavaScript.

## Ownership

- Owns the TypeScript public API, runtime internals, package output, and
  TypeScript-specific tests.
- `caskada-logging.ts` is a non-core browser-safe logging adapter; it must remain
  a synchronous `RunEvent` projection with no Node.js runtime dependency,
  buffering, or delivery policy.

## Local Contracts

- `internal/rfcs/0001-caskada-v3-runtime.md` is the normative behavior source.
- Shared semantics must consume the language-neutral conformance fixtures;
  TypeScript-specific tests may add only host-language construction, dynamic
  JavaScript, and static typing assertions.
- Public option records are captured and validated exactly as specified; JavaScript
  coercion must not silently widen the contract.
- Implementation phases land in RFC order. A later scheduler phase must not be
  used to conceal an incomplete earlier layer.

## Work Guidance

- Keep `caskada.ts` as the stable public entry point. Split runtime internals into
  focused modules when doing so makes ownership and control flow easier to
  understand.
- Preserve browser compatibility and avoid Node.js runtime dependencies.
- Throw immediately on invalid public input and impossible kernel states; do not
  conceal defects with fallback behavior.

## Verification

- Run `tests/definitions.v3.test.ts`, `tests/compile.v3.test.ts`,
  `tests/serial.v3.test.ts`, `tests/state.v3.test.ts`, and
  `tests/results.v3.test.ts`, `tests/failures.v3.test.ts`, and
  `tests/atomic.v3.test.ts`, `tests/retry.v3.test.ts`, and
  `tests/flow-recovery.v3.test.ts`, `tests/cancellation.v3.test.ts`,
  `tests/timers.v3.test.ts`, `tests/limits.v3.test.ts`, and
  `tests/concurrency.v3.test.ts`, `tests/stats.v3.test.ts`, and
  `tests/events.v3.test.ts`, `tests/reports.v3.test.ts`, and
  `tests/logging.v3.test.ts`, `tests/scale.v3.test.ts`, plus strict type checking of
  `tests/definitions.v3.types.ts`, `tests/serial.v3.types.ts`,
  `tests/results.v3.types.ts`, `tests/retry.v3.types.ts`, and
  `tests/flow-recovery.v3.types.ts`, and `tests/cancellation.v3.types.ts`.
  Include `tests/timers.v3.types.ts`, `tests/limits.v3.types.ts`, and
  `tests/events.v3.types.ts`, `tests/reports.v3.types.ts`, and
  `tests/logging.v3.types.ts` in the same strict check.
  Concurrency tests must cover topology-auto and explicit global ceilings,
  local scope slots, retry permit release and priority, cross-scope rotation,
  and sibling fencing before Flow recovery.
  Stats tests must cover committed counters and frozen terminal duration across
  every result status.
  Event tests must cover the public schema and sequence, contiguous bundles,
  callback/transition/terminal payloads, nested closure, failure/retry
  references, synchronous cancellation publication, observer diagnostics, and
  terminal-time exclusion.
  Report tests must cover data presence, observer-independent accounting, name
  and capacity precedence, reentrant observer disablement, every callback
  phase, cancellation and deadline checkpoints, and closed Context rejection.
  Logging-adapter tests must cover fixed severity mapping, exact event retention
  without application-data coercion, synchronous delivery, and nonfatal logger
  failure.
- Run `python3 tests/run-browser-v3.py` from the repository root in a Python
  environment containing Playwright after installing Chromium with
  `playwright install --with-deps chromium`. The harness must bundle the public
  runtime for a browser, reject Node.js built-in imports, and compare its exact
  fan-out/combine/report and `run()` snapshot. On hosts that provision Chromium
  separately, set `CASKADA_BROWSER_EXECUTABLE` to its executable path.
- Scale coverage must include the shared 100,000-node, 10,000-scope, and
  20,000-arm execution fixtures, concurrent compiled-graph reuse, and bounded
  reference-identity behavior for a 10,000-Failure replacement chain.
- Run `python3 conformance/run-all.py` after shared semantic changes.

## Child DOX Index

- No child AGENTS.md files are currently required.
