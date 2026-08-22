# V3 Release Readiness

- Status: implementation complete; independent review pending
- Evidence date: 2026-08-22
- Authority: [RFC 0001](rfcs/0001-caskada-v3-runtime.md)

## Current Gates

| Gate | Status  | Evidence |
| ---- | ------- | -------- |
| Lean normative contract | Pass | RFC 0001 contains only retained v3 behavior and explicit non-goals. |
| Python runtime | Pass | 36 runtime tests, Ruff, strict mypy, Pyright, sdist, and wheel pass. |
| TypeScript runtime | Pass | 32 runtime tests, strict `tsc`, ESM, CommonJS, declarations, and package build pass. |
| Cross-port conformance | Pass | 18 exact retained-behavior cases pass through both public packages and match the accepted snapshots. |
| Author documentation | Pass | Root and package READMEs, core docs, guides, and migration material describe only the retained API. Local links and code fences pass. |
| Cookbook execution | Pass | All 38 isolated cookbook contracts execute their real graphs; strict Pyright passes for the two typed Python examples. |
| Package checks | Pass | ESM, CommonJS, declarations, tarball, sdist, wheel, and the Chromium browser snapshot pass. The browser bundle contains no Node.js built-in import. |
| Independent review | Pending | Review the completed lean kernel and cross-port behavior. |

The implementation is complete. Release and API-freeze sign-off still require
an independent review of the completed kernel.
