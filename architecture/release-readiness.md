# Sley 0.0.1 Release Readiness

- Status: identity, specification, API, and package reset complete; publication deferred
- Evidence date: 2026-08-24
- Authority: [RFC 0001](rfcs/0001-sley-runtime.md)
- Semantic review revision: `96a0bff508e3389979f58554149391257fb457ef`

## Current Gates

| Gate                    | Status | Evidence                                                                                                                               |
| ----------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Identity                | Pass   | Product, Python package/imports, repository links, and CLI use Sley / `sley`; npm and TypeScript imports use `@jigging/sley`.          |
| Lean normative contract | Pass   | RFC 0001 contains only retained behavior and explicit non-goals.                                                                       |
| Python runtime          | Pass   | 37 runtime tests, Ruff, strict mypy, Pyright, sdist, source-rebuilt wheel, and isolated wheel imports pass.                            |
| TypeScript runtime      | Pass   | 34 runtime tests, strict `tsc`, ESM, CommonJS, declarations, package build, isolated package imports, and Chromium pass.               |
| Cross-port conformance  | Pass   | 19 exact retained-behavior cases pass through both public packages and match the accepted snapshots.                                   |
| Author documentation    | Pass   | Root and package READMEs, core docs, guides, and migration material use the Sley package surface.                                      |
| Cookbook execution      | Pass   | All 41 contracts pass isolated installation runs; catalog source compilation and strict Pyright pass.                                  |
| Independent review      | Pass   | Three independent critics found no blocker or major issue in the semantic review revision; the rename does not alter runtime behavior. |

Every Sley 0.0.1 implementation gate passes. Tags, package uploads, GitHub
releases, and other publication remain intentionally deferred. The canonical
public website is `https://sley.jig.md`; deploying it is not required for package
readiness.
