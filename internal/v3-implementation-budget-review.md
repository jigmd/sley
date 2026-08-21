# V3 Implementation Budget Review

- Status: accepted
- Date: 2026-08-21

Tests, conformance tools, and cookbook examples are excluded. This budget is
for shipped runtime source because that is the code every maintainer must carry.

| Port       | Production files | Physical lines | Status            |
| ---------- | ---------------: | -------------: | ----------------- |
| Python     |                5 |          1,349 | Lean rewrite done |
| TypeScript |                5 |          1,245 | Lean rewrite done |

Python previously used nine files and 5,415 physical lines. Its public facade
now exports 24 names instead of roughly 100. The runner uses ordinary
`asyncio`, lists, tuples, and dictionaries; timing, observation, cancellation,
logging-adapter, and failure-collection modules were deleted.

TypeScript previously used nine files and 4,941 physical lines. Its runtime
facade now exports eight values; `CompiledFlow` is a type-only interface so
compiled scheduler records do not leak through declarations. Timing,
observation, cancellation, logging-adapter, and failure helper modules were
deleted.

## Budget Rule

- The public API stays thinner than the runner.
- The runner contains only accepted RFC behavior.
- A helper or abstraction must remove visible complexity now.
- A custom runtime structure requires evidence that native primitives fail.
- Verification size is not production-runtime size.
