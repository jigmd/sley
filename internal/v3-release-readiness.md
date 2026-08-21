# V3 Release Readiness

- Status: implementation in progress
- Evidence date: 2026-08-21
- Authority: [RFC 0001](rfcs/0001-caskada-v3-runtime.md)

## Current Gates

| Gate | Status  | Evidence |
| ---- | ------- | -------- |
| Lean normative contract | Pass | RFC 0001 contains only retained v3 behavior and explicit non-goals. |
| Python runtime | Pass | 36 runtime tests, Ruff, strict mypy, Pyright, sdist, and wheel pass. |
| TypeScript runtime | Pending | The port still implements the superseded scheduler contract. |
| Cross-port conformance | Pending | Fixtures and adapters still contain deleted feature groups. |
| Author documentation | Pending | Repository guides still describe removed features. |
| Cookbook execution | Pending | Examples require verification against both final packages. |
| Package checks | Pending | Final ESM, CommonJS, browser, wheel, and installed typing checks remain. |
| Independent review | Pending | Review the completed lean kernel and cross-port behavior. |

The implementation is not ready for release or API freeze until every pending
gate is regenerated against the lean runtime. Evidence from the superseded D10
implementation is not release evidence.
