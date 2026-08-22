# V3 Release Readiness

- Status: v3 specification and API frozen; publication deferred pending naming
- Evidence date: 2026-08-22
- Authority: [RFC 0001](rfcs/0001-caskada-v3-runtime.md)
- Reviewed revision: `96a0bff508e3389979f58554149391257fb457ef`

## Current Gates

| Gate | Status  | Evidence |
| ---- | ------- | -------- |
| Lean normative contract | Pass | RFC 0001 contains only retained v3 behavior and explicit non-goals. |
| Python runtime | Pass | 37 runtime tests, Ruff, strict mypy, Pyright, sdist, and wheel pass. |
| TypeScript runtime | Pass | 34 runtime tests, strict `tsc`, ESM, CommonJS, declarations, and package build pass. |
| Cross-port conformance | Pass | 19 exact retained-behavior cases pass through both public packages and match the accepted snapshots. |
| Author documentation | Pass | Root and package READMEs, core docs, guides, and migration material describe only the retained API. Local links and code fences pass. |
| Cookbook execution | Pass | All 38 isolated cookbook contracts execute their real graphs; strict Pyright passes for the two typed Python examples. |
| Package checks | Pass | Isolated ESM, CommonJS, declarations, tarball, sdist, wheel, and Chromium checks pass. The browser bundle contains no Node.js built-in import. |
| Independent review | Pass | Three independent critics found no blocker or major issue in the exact reviewed revision after focused re-verification. |

Every v3 specification and API gate passes. Tags, package uploads, and other
publication are intentionally deferred because the project may be renamed.
Naming changes must update package metadata and links and rerun package gates;
they do not reopen runtime semantics unless they alter the API contract.
