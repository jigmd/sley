# V3 Release Readiness

- Status: implementation in progress
- Evidence date: 2026-08-21
- Authority: [RFC 0001](rfcs/0001-caskada-v3-runtime.md)

## Current Gates

| Gate | Status  | Evidence |
| ---- | ------- | -------- |
| Lean normative contract | Pass | RFC 0001 contains only retained v3 behavior and explicit non-goals. |
| Python runtime | Pass | 36 runtime tests, Ruff, strict mypy, Pyright, sdist, and wheel pass. |
| TypeScript runtime | Pass | 32 runtime tests, strict `tsc`, ESM, CommonJS, declarations, and package build pass. |
| Cross-port conformance | Pass | 18 exact retained-behavior cases pass through both public packages and match the accepted snapshots. |
| Author documentation | Pending | Repository guides still describe removed features. |
| Cookbook execution | Pending | Examples require verification against both final packages. |
| Package checks | Partial | ESM, CommonJS, declarations, tarball, sdist, and wheel pass. The browser bundle builds without Node.js imports, but Chromium cannot launch on this host because `libglib-2.0.so.0` is unavailable. |
| Independent review | Pending | Review the completed lean kernel and cross-port behavior. |

The implementation is not ready for release or API freeze until every pending
gate is regenerated against the lean runtime. Evidence from the superseded D10
implementation is not release evidence.
