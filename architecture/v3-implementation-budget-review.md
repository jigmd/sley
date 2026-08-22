# V3 Implementation Budget Review

- Status: accepted
- Date: 2026-08-22

Tests, conformance tools, and cookbook examples are excluded. This budget is
for shipped runtime source because that is the code every maintainer must carry.

| Port       | Production files | Physical lines | Status            |
| ---------- | ---------------: | -------------: | ----------------- |
| Python     |                6 |          1,360 | Lean rewrite done |
| TypeScript |                6 |          1,250 | Lean rewrite done |

Python previously used nine files and 5,415 physical lines. Its public facade
now exports 24 names instead of roughly 100. The runner uses ordinary
`asyncio`, lists, tuples, and dictionaries; timing, observation, cancellation,
logging-adapter, and failure-collection modules were deleted.

TypeScript previously used nine files and 4,941 physical lines. Its runtime
facade now exports eight values; `CompiledFlow` is a type-only interface so
compiled scheduler records do not leak through declarations. Timing,
observation, cancellation, logging-adapter, and failure helper modules were
deleted.

Each port uses one small `context` module for callback-local validation and
intent buffering. Graph compilation and runner execution remain cohesive
rather than being split into utility or type-only layers.

## Budget Rule

- The public API stays thinner than the runner.
- The runner contains only accepted RFC behavior.
- A helper or abstraction must remove visible complexity now.
- A custom runtime structure requires evidence that native primitives fail.
- Verification size is not production-runtime size.
