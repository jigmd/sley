# Python Runtime

## Purpose

- Implement the accepted Sley contract for Python 3.13.

## Ownership

- Owns the Python public API, runtime internals, packaging, inline types, and
  Python-specific tests.
- `sley/__init__.py` is the public facade. `_contracts.py` owns public values,
  `_graph.py` graph definitions and compilation, `_context.py` callback-local
  control, `_state.py` state capture, and `_runner.py` graph execution.

## Local Contracts

- `architecture/rfcs/0001-sley-runtime.md` is normative.
- Release changesets name the public package `sley`.
- Shared semantics consume language-neutral conformance fixtures. Python tests
  add host-language validation, asyncio, and typing coverage.
- Public definitions fail immediately on invalid values. Application failures
  become runtime `Failure` records only where retry or recovery can act on them.
- Compilation revalidates reachable mutable definitions before snapshotting.
- Compiled description records are public `TypedDict` contracts with the
  portable version 1 snake_case shape.

## Work Guidance

- Keep `sley/__init__.py` to imports and `__all__`; scheduler logic is private.
- Keep the shipped runner smaller than its verification. Use ordinary `dict`,
  `asyncio` tasks, lists, and tuples before custom runtime machinery.
- Definitions store no invocation state. `_runner.py` is the only activation
  and scope orchestrator; leaf modules do not call back into it.
- `_context.py` only validates callback control and records `emit` and `end`
  intents; it does not route or schedule them.
- `_state.py` performs only start-boundary validation and a native shallow copy.
- Preserve `sley/py.typed` so installed mypy and Pyright users receive the
  verified inline types.
- Let `BaseException` keep native behavior. Catch ordinary application
  exceptions only at callbacks and declared policy boundaries, and always close
  the callback Context before propagation.
- Raise on impossible compiled states; do not hide runtime defects in fallback
  outcomes.

## Verification

- Run `PYTHONPATH=python python -m unittest discover -s python/tests -p
'test_*.py'` for definition, routing, state/input, terminals, nested Flow,
  combine, atomic control, results, retry, recovery, concurrency, and cycle
  limits.
- Run strict mypy and Pyright against `python/tests/typing.py`.
- Run Ruff checks and formatting over `python/sley`, `python/tests`, and
  `python/setup.py`.
- Build the source distribution and wheel from `python/`; the wheel must rebuild
  from the generated source archive.
- Run `python3 conformance/run-all.py` after shared semantic changes.

## Child DOX Index

- No child AGENTS.md files are currently required.
