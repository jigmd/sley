# Repository Integration Tests

## Purpose

- Verify behavior that crosses runtime, packaging, documentation, and example
  boundaries.

## Ownership

- Owns black-box cookbook contracts, their catalog, external-service fixtures,
  and isolated project runner.

## Local Contracts

- Cookbook contracts execute the example's real entry point and real Sley
  graph from a staged project copy.
- External API, search, audio, and network behavior is replaced only inside the
  test harness; teaching source must not contain smoke-test branches.
- Installed runs resolve Python `sley` and TypeScript `@jigging/sley` to the
  current checkout before validating each project's declared dependencies.

## Work Guidance

- Assert learner-visible output or artifacts, not implementation details.
- Keep catalog expectations specific enough to catch stale example behavior.

## Verification

- Run `python tests/cookbook/runner.py validate`.
- Run changed cookbook contracts with
  `python tests/cookbook/runner.py run <project> --install` in an isolated
  environment when dependency declarations change. Without `--install`,
  TypeScript contracts reuse the current workspace installation in the staged
  project.
- Run strict mypy and Pyright against cookbook examples that present themselves
  as typed; `tests/cookbook/pyrightconfig.json` owns the Pyright target set.

## Child DOX Index

- No child AGENTS.md files are currently required.
