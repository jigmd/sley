# Conformance

## Purpose

- Provide language-neutral executable contracts shared by Python and
  TypeScript without making either runtime the behavioral oracle.

## Ownership

- Owns the fixture schema, exact expected snapshots, production adapters,
  coverage map, and cross-port runner.

## Local Contracts

- JSON fixtures are the source of case ids, RFC requirements, and expected
  normalized snapshots.
- Python and TypeScript adapters implement every case independently using only
  their public package surface.
- Assertions are exact. Omitted terminal output remains distinguishable from an
  explicit null value through `has_output`.
- Fixture changes require a matching RFC or an explicit correction to the
  implementation of an existing rule.

## Work Guidance

- Keep cases direct and readable. Prefer a small named scenario over a general
  fixture language that reimplements the graph runner.
- Normalize only host-language spelling differences. Do not erase graph,
  terminal, failure, or ordering behavior merely to make ports agree.
- Reject missing, duplicate, unknown, or extra case ids immediately.

## Verification

- Run `python3 conformance/run-all.py`; it validates fixtures, executes both
  public runtimes, and compares each snapshot exactly with the fixture and the
  other port.
- Type-check the TypeScript adapter with the runtime's strict compiler settings.

## Child DOX Index

- No child AGENTS.md files are currently required.
