# Rejected V3 Prototype Audit

- Status: non-normative evidence
- Date: 2026-08-20
- Baseline inspected: uncommitted workspace derived from `d60e29f`

## Disposition

The prototype runtime, its conformance runners, and its broad automatic cookbook
conversion were rejected as an implementation base. The reviewed eight-project
cookbook authoring experiment is separate and remains useful design evidence.

## Reusable lessons

- The scenario inventory usefully identified basic contract areas: linear
  routing, zero-emission continuation, hard ends, fan-out and combination,
  unknown actions, retries, nested Flows, limits, state-copy isolation, reports,
  concurrent runs, cancellation, and abandonment.
- Those scenario names are seeds only. Each case must be rewritten as one shared
  language-neutral fixture with an exact expected snapshot.
- Small cross-port smoke tests expose API ergonomics early, but passing smoke
  tests cannot substitute for the RFC's semantic and complexity matrix.

## Why the code was rejected

- The Python `check()` helper printed `OK` without asserting its condition, so a
  false result still passed. Several functions were duplicated after the runner.
- Python and TypeScript restated scenarios separately instead of consuming one
  contract, allowing their assertions and author grammar to diverge.
- Some handlers returned list-comprehension results even though successful v3
  callbacks return only `None` / `undefined`; the prototype silently ignored the
  invalid result.
- Assertions accepted several statuses or failure kinds and lower-bounded stats
  where the RFC specifies one exact outcome.
- TypeScript implemented `link(target, action = null)`, so an explicit
  `undefined` became an unlabelled link despite D9 making omission the only
  unlabelled spelling.
- The ports had radically different structures and incomplete semantics while
  presenting the same passing fixture list. Polling cancellation, flattened
  scope behavior, swallowed observer errors, and unchecked casts concealed
  missing scheduler contracts.

## Rule carried forward

Production code is not the oracle. Phase 0 first establishes shared fixture
data, independent serial reference interpreters, exact snapshot comparison, and
requirement coverage. Only then may the production compiler and scheduler begin.
