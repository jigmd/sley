# V3 Release Readiness

- Status: executable gates pass; independent review gates pending
- Evidence date: 2026-08-21
- Authority: [RFC 0001](rfcs/0001-caskada-v3-runtime.md)

## Gate Matrix

| Gate | Status         | Evidence                                                                                                                                                                                                                                                              |
| ---: | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|    1 | Pass           | `conformance/run-all.py` reports exact Python/TypeScript agreement across all 68 shared fixtures and scale programs.                                                                                                                                                  |
|    2 | Pass           | The Python public surface imports under CPython 3.13.11; strict TypeScript 5.9.3 compilation passes with exact optional properties and unchecked indexed access enabled.                                                                                              |
|    3 | Pass           | Serial topology, state, input, output, terminal, failure, event, and stats snapshots are byte-equivalent across ports.                                                                                                                                                |
|    4 | Pass           | Shared scale cases cover 100,000 nodes, 10,000 scopes, 20,000 fan-out arms, and concurrent compiled-graph reuse; port tests cover bounded failure representation and timer/packet behavior.                                                                           |
|    5 | Pass           | Python and TypeScript cancellation suites cover cooperative and uncooperative work, immutable fences, grace, and abandonment.                                                                                                                                         |
|    6 | Pass           | Current guides teach function-backed nodes, state/input, `emit`/`end`, target-first `link`, `Flow`, and direct `run()` state before policy.                                                                                                                           |
|    7 | Pass           | Official examples use buffered Context control and introduce input, output, topology, combine, and `start()` only where their lesson needs them.                                                                                                                      |
|    8 | Pass           | All 36 Python and two TypeScript cookbook contracts execute from staged projects with test-owned service fixtures. A fresh independent before/after API review accepted the complete migration after its pedagogy findings were resolved.                         |
|    9 | Pass           | The current-source scan is clean outside explicit migration/history and negative contract tests. Generated v2 translation artifacts were removed.                                                                                                                     |
|   10 | Pass           | Both packages declare zero runtime dependencies; the browser bundle passes a real Chromium snapshot; concurrency tests prove run-local framework state and distinct top-level state carriers.                                                                         |
|   11 | Pending review | Fresh independent author-API, kernel-semantics, and cross-port-implementability reviews have not yet been run against this implementation snapshot.                                                                                                                   |

## Port Evidence

Python:

- 142 runtime tests pass.
- Strict mypy 1.17.1 and Pyright 1.1.413 checks pass.
- The sdist and wheel build; the wheel installs cleanly; both public packages
  expose PEP 561 types; installed imports and strict mypy consumption pass.

TypeScript:

- 147 runtime tests pass through the package test script.
- Strict declarations, fixtures, and typed cookbook examples compile.
- The browser bundle contains no Node.js built-in import and passes the exact
  Chromium fan-out/combine/report snapshot.
- The packed artifact loads its core and logging exports through ESM and
  CommonJS.

Repository:

- All 38 cookbook contracts pass.
- The cookbook catalog, Python parsing, changed-file formatting, Markdown
  fences/local links, baseline hashes, and `git diff --check` pass.

## Freeze Blockers

The implementation is ready for the remaining independent reviews, not release
or API freeze. One review group remains:

- The author-API, kernel-semantics, and cross-port-implementability reviews
  required by release gate 11.

The size-triggered architecture review is accepted with no finding, as recorded
in [V3 Implementation Budget Review](v3-implementation-budget-review.md). The
fresh cookbook API review is also accepted with no finding. No executable
correctness, packaging, browser, cookbook, dependency, or stale model failure is
currently open.
