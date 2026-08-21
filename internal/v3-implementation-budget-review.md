# V3 Implementation Budget Review

- Status: simplification in progress
- Date: 2026-08-21

Tests, conformance tools, and cookbook examples are excluded. This budget is
for shipped runtime source because that is the code every maintainer must carry.

| Port       | Production files | Physical lines | Status            |
| ---------- | ---------------: | -------------: | ----------------- |
| Python     |                5 |          1,349 | Lean rewrite done |
| TypeScript |                9 |          4,941 | Rewrite pending   |

Python previously used nine files and 5,415 physical lines. Its public facade
now exports 24 names instead of roughly 100. The runner uses ordinary
`asyncio`, lists, tuples, and dictionaries; timing, observation, cancellation,
logging-adapter, and failure-collection modules were deleted.

The TypeScript count remains the next blocker. Completion requires equivalent
removal there, not a waiver based on passing tests.

## Budget Rule

- The public API stays thinner than the runner.
- The runner contains only accepted RFC behavior.
- A helper or abstraction must remove visible complexity now.
- A custom runtime structure requires evidence that native primitives fail.
- Verification size is not production-runtime size.
