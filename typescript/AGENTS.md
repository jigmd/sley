# TypeScript Runtime

## Purpose

- Implement the accepted Sley contract for TypeScript and JavaScript.

## Ownership

- Owns the TypeScript public API, runtime internals, package output,
  browser-compatibility checks, and TypeScript-specific tests.
- `sley.ts` is the public facade. `contracts.ts` owns public values,
  `graph.ts` graph definitions and compilation, `context.ts` callback-local
  control, `state.ts` state capture, and `runner.ts` graph execution.

## Local Contracts

- `architecture/rfcs/0001-sley-runtime.md` is normative.
- The published npm package and public import specifier are `@jigging/sley`;
  internal facade and artifact basenames remain `sley`.
- Release changesets name the public package `@jigging/sley`.
- Shared semantics consume language-neutral conformance fixtures. TypeScript
  tests add dynamic JavaScript, Promise, browser, and static typing coverage.
- Invalid public options fail immediately. Application throws become runtime
  `Failure` records only where retry or recovery can act on them.
- Initial state is a plain string-keyed object; invalid containers fail before
  callbacks run.
- Compiled description records are public discriminated interfaces with the
  portable version 1 snake_case shape.
- Published JavaScript and declarations target ES2022. Node 24 is the only
  CI-tested server runtime; the repository Chromium runtime check covers an
  ES2022 browser bundle, not browsers generally. Bun, Deno, and other browsers
  are unverified.
- `package.json` intentionally omits `engines` until a minimum Node version is
  tested; the package is not Node-specific.

## Work Guidance

- Keep `sley.ts` to intentional exports; scheduler logic is private.
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
- After building, `pnpm --dir typescript check:declarations` verifies the
  generated declarations with the ES2022 library and `skipLibCheck` disabled.
- Run strict `tsc` over `typescript/tsconfig.json` after the build so typed
  cookbook projects can resolve the linked local package; the check includes
  `tests/runtime.types.ts`.
- Run `python typescript/tests/run-browser.py` inside `shell.nix`; the bundle
  must contain no Node.js built-in import.
- Run `python3 conformance/run-all.py` after shared semantic changes.

## Child DOX Index

- No child AGENTS.md files are currently required.
