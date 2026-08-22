# Architecture

## Purpose

- Hold Caskada's normative specifications, architecture decisions, accepted
  implementation baselines, and non-normative design evidence.

## Ownership

- Owns `rfcs/`, architecture verdicts, baseline manifests, implementation budget
  reviews, release-readiness evidence, and prototype audits.
- Runtime source and executable conformance remain owned by their respective
  repository areas.

## Local Contracts

- An accepted RFC is the semantic authority. Implementations and examples do
  not silently redefine it.
- A semantic change requires an RFC amendment and a matching conformance-fixture
  diff before either runtime adopts it.
- Baseline manifests identify authoritative files by content hash.
- Prototype audits are evidence only and must say explicitly that rejected code
  is not an implementation base.

## Work Guidance

- Keep normative rules separate from historical arguments and rejected
  prototypes.
- Distinguish implementation acceptance from release readiness; executable
  release gates do not prevent freezing an implementation baseline.
- Prefer the smallest complete semantic model. New concepts and special cases
  must reduce overall implementation and authoring complexity, not merely move it.
- Record intentional behavior ceilings and application-owned responsibilities
  in architecture decisions so issue triage can distinguish defects from
  optimization or feature requests.

## Verification

- Format Markdown and run `git diff --check`.
- Recompute every hash in an implementation-baseline manifest after changing an
  authoritative file; `python3 conformance/run-all.py` verifies the manifest.

## Child DOX Index

- No child AGENTS.md files are currently required.
