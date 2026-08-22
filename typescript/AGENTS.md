# TypeScript Runtime

## Purpose

- Implement the accepted Caskada v3 contract for TypeScript and JavaScript.

## Ownership

- Owns the TypeScript public API, runtime internals, package output,
  browser-compatibility checks, and TypeScript-specific tests.
- `caskada.ts` is the public facade. `contracts.ts` owns public values,
  `graph.ts` graph definitions and compilation, `context.ts` callback-local
  control, `state.ts` state capture, and `runner.ts` graph execution.

## Local Contracts

- `architecture/rfcs/0001-caskada-v3-runtime.md` is normative.
- Shared semantics consume language-neutral conformance fixtures. TypeScript
  tests add dynamic JavaScript, Promise, browser, and static typing coverage.
- Invalid public options fail immediately. Application throws become runtime
  `Failure` records only where retry or recovery can act on them.
- Initial state is a plain string-keyed object; invalid containers fail before
  callbacks run.

## Work Guidance

- Keep `caskada.ts` to intentional exports; scheduler logic is private.
- Keep the shipped runner smaller than its verification. Use native objects,
  arrays, Maps, Promises, and timers before custom runtime machinery.
- Definitions store no invocation state. `runner.ts` is the only
  activation and scope orchestrator.
- `context.ts` only validates callback control and records `emit` and `end`
  intents; it does not route or schedule them.
- `state.ts` performs only start-boundary validation, native shallow
  copy, and temporary Promise-thenable masking.
- Preserve browser compatibility and avoid Node.js runtime imports.
- Catch application values only at callbacks and declared policy boundaries.
  Reject impossible compiled states instead of hiding defects.

## Verification

- Run `pnpm --dir typescript test` for definition, routing, state/input,
  terminals, nested Flow, combine, atomic control, results, retry, recovery,
  concurrency, and cycle limits.
- Build ESM, CommonJS, and declarations with `pnpm --dir typescript build`.
- Run strict `tsc` over `typescript/tsconfig.json` after the build so typed
  cookbook projects can resolve the linked local package; the check includes
  `tests/runtime.v3.types.ts`.
- Run `python typescript/tests/run-browser-v3.py` inside `shell.nix`; the bundle
  must contain no Node.js built-in import.
- Run `python3 conformance/run-all.py` after shared semantic changes.

## Child DOX Index

- No child AGENTS.md files are currently required.
