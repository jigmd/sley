# V3 Implementation Budget Review

- Status: simplification in progress; prior architecture verdict superseded
- Date: 2026-08-21
- Python ordered module-set SHA-256:
  `a23cc36c462fe34cd85e1a2698690e41ab092b8d2a84f7f60b626f7b1cd3dbb5`
- TypeScript ordered module-set SHA-256:
  `54c3bc655b8e4ba5f3bfd25e328437043d4dac6ac09c52f0b6189ed7cf8f0401`

Each digest hashes the ordered `sha256sum` records for the public facade,
contracts, definition, execution, state, failures, timing, observation, and
scheduling modules in that order.

## Budget Result

The RFC requires another architecture review when either v3 core exceeds three
times its v2 size. Both implementations cross that threshold.

The count below includes physical lines containing language tokens, excludes
blank lines and comments, and excludes Python docstring lines. It measures the
primary runtime source only, not tests, adapters, generated declarations, or
conformance runners.

| Port       | V2 lines | V3 lines | Ratio |
| ---------- | -------: | -------: | ----: |
| Python     |      207 |    4,798 | 23.2x |
| TypeScript |      296 |    4,536 | 15.3x |

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

The two ports now use the same responsibility map:

| Module      | Ownership                                                            |
| ----------- | -------------------------------------------------------------------- |
| Facade      | Exact intentional public exports                                     |
| Contracts   | Public data, protocols, options, results, and errors                 |
| Definition  | Graph construction, validation, compilation, and inspection          |
| Execution   | Public `Flow` lifecycle composition                                  |
| State       | Run-state validation and the persistent carrier                      |
| Failures    | Failure construction, packets, replacement, and retry policy         |
| Timing      | Cancellation, callback permits, deadlines, grace, and callback races |
| Observation | Event publication, failure fences, diagnostics, IDs, and statistics  |
| Scheduling  | The sole activation and structured-scope orchestration owner         |

The facade exposes execution and inert definitions; execution invokes the
scheduler; the scheduler depends only on focused leaf modules. No leaf module
imports or invokes the scheduler, and the scheduler does not depend on the
execution layer. Python publishes an exact `__all__`; both ports have facade
regression tests.

## Evidence Already Passing

- All 68 shared conformance fixtures and scale programs agree across ports.
- Python passes 141 runtime tests, strict mypy/Pyright fixtures, wheel/sdist
  rebuild, installed PEP 561 typing, and clean-package imports.
- TypeScript passes 146 runtime tests, strict declaration/example checks, a real
  Chromium bundle snapshot, and ESM/CommonJS/logging package imports.
- All 36 Python and two TypeScript cookbook contracts execute through staged
  projects with test-owned external-service fixtures.
- Both packages declare zero runtime dependencies.

## Review Status

The previous architecture verdict assessed superseded module hashes. Review the
lean implementation only after its deletion passes are complete; the cookbook
and author-API reviews remain separate evidence.
