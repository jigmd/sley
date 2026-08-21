# V3 Implementation Budget Review

- Status: implementation evidence; independent architecture approval pending
- Date: 2026-08-21
- Python source SHA-256:
  `9bc77c1bea30d20eabcaf6d1694ac9d3b1fde291b128d0e81087b6c7ef6030e1`
- TypeScript source SHA-256:
  `f606020ed912e989d33c36b4e86568a8078917e4916aa6a3abc828ac49867ef9`

## Budget Result

The RFC requires another architecture review when either v3 core exceeds three
times its v2 size. Both implementations cross that threshold.

The count below includes physical lines containing language tokens, excludes
blank lines and comments, and excludes Python docstring lines. It measures the
primary runtime source only, not tests, adapters, generated declarations, or
conformance runners.

| Port       | V2 lines | V3 lines | Ratio |
| ---------- | -------: | -------: | ----: |
| Python     |      207 |    4,766 | 23.0x |
| TypeScript |      296 |    4,556 | 15.4x |

The increase is not evidence of an equally large author model. It is primarily
the cost of making the cross-language scheduler, failure lifecycle, limits,
cancellation, observation, and type surfaces exact. It is still a material
maintenance and comprehension risk and cannot be waived by passing tests.

## Public Abstraction Budget

Every public family maps to one accepted contract responsibility:

| Family              | Public abstractions                                                                   | Required responsibility                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Authoring           | `node`, `Node`, `Flow`, `GraphElement`, `Link`, `Context`                             | Function-backed work, topology ownership, structured scope, branch input, shared state, and buffered control |
| Policy              | `RetryPolicy`, `RunOptions`                                                           | Explicit retry, timing, concurrency, and bounded-work configuration                                          |
| Execution           | `CompiledFlow`, `RunHandle`, `Cancellation`                                           | Definition snapshot, advanced lifecycle access, and cooperative cancellation                                 |
| Results             | `Completed`, `Failed`, `Cancelled`, `Abandoned`, `RunError`, `RunStats`               | Total cross-language settlement without hiding failure, cancellation, or abandonment                         |
| Scope and terminals | `ScopeResult`, `ScopeFailure`, `EndTerminal`, `ExitTerminal`                          | Structured join input, failure recovery input, hard terminal output, and Flow exit metadata                  |
| Failure data        | `Failure` and the bounded detail records                                              | Stable failure identity, provenance, suppression, limits, and machine-readable reasons                       |
| Observation         | `RunEvent`, its typed payload/disposition/transition records, `ObserverDiagnostic`    | Exact synchronous event schema and nonfatal observer diagnostics                                             |
| Inspection          | `CompiledDescription` and its typed component records                                 | Portable, language-neutral compiled topology inspection                                                      |
| Definition errors   | `CaskadaError`, `GraphDefinitionError`, `DuplicateLinkError`, `OptionValidationError` | Synchronous construction and pre-start failure boundaries                                                    |

The logging exports remain optional adapters rather than core scheduler
abstractions. No public persistence, stream, transaction, patch, branch-state,
or dynamic-graph concept was added.

## Internal Complexity

The main implementation cost is concentrated in six kernel responsibilities:

1. Exact definition capture and breadth-first compilation with portable IDs.
2. One persistent, validated run-owned state carrier.
3. Structured scope queues, callback permits, fairness, and bounded admission.
4. Failure packets, retry, Node recovery, Flow recovery, and suppression.
5. Deadline, timeout, cancellation, grace, and abandonment races.
6. Atomic event bundles, reports, diagnostics, statistics, and terminal results.

The Python and TypeScript files intentionally retain parallel organization so
semantic comparison remains possible. That helps parity but leaves each core too
large to fit comfortably in one reading session. A module split is justified
only along the responsibilities above and must preserve one public entry point,
avoid circular scheduler ownership, and keep cross-port section correspondence.

## Evidence Already Passing

- All 68 shared conformance fixtures and scale programs agree across ports.
- Python passes 141 runtime tests, strict mypy/Pyright fixtures, wheel/sdist
  rebuild, installed PEP 561 typing, and clean-package imports.
- TypeScript passes 146 runtime tests, strict declaration/example checks, a real
  Chromium bundle snapshot, and ESM/CommonJS/logging package imports.
- All 36 Python and two TypeScript cookbook contracts execute through staged
  projects with test-owned external-service fixtures.
- Both packages declare zero runtime dependencies.

## Review Required

This document satisfies the RFC requirement to publish counts and justify the
public abstraction families. It does not satisfy the required independent
architecture review or the three independent release reviews. Before API freeze,
reviewers must decide whether the kernel responsibilities justify the size,
whether an internal module split would reduce understanding cost, and whether
any public family can be removed without weakening the accepted contract.
