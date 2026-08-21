# Conformance

## Purpose

- Provide the language-neutral executable contract shared by Python and
  TypeScript before either production runtime becomes the behavioral oracle.

## Ownership

- Owns fixture schemas, JSON cases, coverage records, reference interpreters,
  and cross-port snapshot runners.

## Local Contracts

- JSON fixtures are the shared source of scenario inputs and expected normalized
  snapshots; port-specific test code must not restate expected behavior.
- Reference interpreters must not import either production runtime.
- Assertions are exact. Alternative statuses, broad failure-kind sets, minimum
  counters, and presence-only event checks require an explicit normative reason.
- Omission and explicit null are different fixture values and must remain
  distinguishable through input and output normalization.
- Every fixture maps to named RFC requirements. Semantic fixture changes require
  a corresponding RFC amendment.
- Prototype-derived scenarios must be rewritten against the accepted grammar;
  rejected prototype code is never copied into a reference interpreter.
- The failure/recovery fixture language covers serial packet lifecycle only.
  Scheduling, timer, cancellation, and concurrent-suppression operations belong
  in their own later fixture groups rather than expanding that reference model.
- The scheduling/cancellation fixture language owns normalized admission,
  fairness, fencing, discard, and suppression facts. Raw elapsed time and
  host-specific cancellation exceptions remain port-specific checks.
- The events/reports/limits fixture language owns exact portable publication,
  diagnostic, report-presence, and capacity-precedence snapshots. Reflection
  traps and native async-result disposal remain host-specific tests.
- Runtime-scale fixtures own exact cross-port counts and boundary observations
  for large execution graphs, wide fan-out, and concurrent compiled-graph reuse.

## Work Guidance

- Keep the fixture language smaller than the runtime API and limited to behavior
  needed by the covered requirements.
- Prefer deterministic serial cases and complete snapshots before adding
  concurrency, timers, or host scheduling.
- Keep reference execution explicit and modular; reject malformed fixtures and
  impossible interpreter states immediately.

## Verification

- Run `python3 conformance/run-all.py`; it verifies the accepted baseline,
  executes both references and the completed production adapters, and requires
  byte-equivalent normalized snapshots, including the failure/recovery and
  scheduling/cancellation corpora and the events/reports/limits corpus.
- `run-all.py` also executes the 100,000-node, 10,000-scope, 20,000-arm, and
  concurrent-reuse runtime-scale fixtures. Keep these cases iterative and free
  of host timing assertions.
- Type-check the TypeScript reference with strict, exact-optional, and
  unchecked-index compiler flags.

## Child DOX Index

- No child AGENTS.md files are currently required.
