# Python Runtime

## Purpose

- Implement the accepted Caskada v3 contract for Python 3.13.

## Ownership

- Owns the Python public API, runtime internals, packaging metadata, and
  Python-specific tests.
- `caskada_logging` is a non-core standard-library logging adapter package; it must
  remain a synchronous projection of `RunEvent` and must not add scheduler
  buffering or delivery policy.

## Local Contracts

- `internal/rfcs/0001-caskada-v3-runtime.md` is the normative behavior source.
- Shared semantics must consume the language-neutral conformance fixtures;
  Python-specific tests may add only host-language construction and typing
  assertions.
- Public definitions use exact runtime validation where the RFC requires it;
  Python coercion and subclass acceptance must not silently widen the contract.
- Implementation phases land in RFC order. A later scheduler phase must not be
  used to conceal an incomplete earlier layer.

## Work Guidance

- Keep public imports stable through `caskada/__init__.py`. Split runtime internals
  into focused modules when doing so makes ownership and control flow easier to
  understand.
- Keep `py.typed` markers in both public packages so installed mypy and Pyright
  consumers receive the same inline types verified from source.
- Prefer explicit private helpers over framework abstractions that are not part
  of the accepted contract.
- Raise immediately on invalid public input and impossible kernel states; do not
  conceal defects with fallback behavior.

## Verification

- Run `PYTHONPATH=python python3 -m unittest python.tests.test_v3_definitions
python.tests.test_v3_compile python.tests.test_v3_serial
python.tests.test_v3_state python.tests.test_v3_results
python.tests.test_v3_failures python.tests.test_v3_atomic
python.tests.test_v3_retry python.tests.test_v3_flow_recovery
python.tests.test_v3_cancellation python.tests.test_v3_timers
python.tests.test_v3_limits python.tests.test_v3_concurrency
python.tests.test_v3_stats python.tests.test_v3_events
python.tests.test_v3_reports python.tests.test_v3_logging
python.tests.test_v3_scale` for definition,
  compilation, deterministic serial execution, state-carrier semantics,
  result/handle behavior, portable failure normalization, and atomic callback
  settlement, retry policy, retry delays, Node recovery, and Flow failure/recovery
  propagation, caller cancellation, cooperative callback cancellation, and
  cancellation suppression, run deadlines, Node attempt timeouts, grace,
  abandonment, and run-wide and scope-local resource admission limits.
  Topology-aware concurrency coverage fixes automatic and explicit global
  ceilings, local scope slots, retry permit release and priority, fair
  cross-scope admission, and sibling fencing before Flow recovery.
  Stats coverage fixes committed counters and the frozen terminal duration for
  completed, failed, cancelled, and abandoned results.
  Event coverage fixes the public event schema, one-based sequence, opening and
  terminal bundles, callback dispositions, transition and terminal payloads,
  nested scope closure, failure/retry references, synchronous cancellation
  publication, observer disablement/diagnostics, and terminal-time exclusion.
  Report coverage fixes omission versus explicit data, accepted accounting with
  or without an observer, name and budget precedence, reentrant observer
  disablement, callback-phase availability, fence delivery, timer checkpoints,
  and Context-lifetime closure.
  Logging-adapter coverage fixes one synchronous standard-library log record per
  event, fixed severity mapping, exact event retention without application-data
  formatting, and nonfatal sink failure.
  Scale coverage fixes iterative 100,000-node, 10,000-scope, and 20,000-arm
  execution through shared conformance, plus bounded representation and
  identity semantics for a 10,000-Failure replacement chain.
- Run strict mypy and Pyright against `python/tests/v3_definitions_typing.py`
  `python/tests/v3_serial_typing.py`, `python/tests/v3_results_typing.py`,
  `python/tests/v3_retry_typing.py`, and
  `python/tests/v3_flow_recovery_typing.py`, and
  `python/tests/v3_cancellation_typing.py`, and
  `python/tests/v3_timers_typing.py`, and
  `python/tests/v3_limits_typing.py`, and
  `python/tests/v3_events_typing.py`, and
  `python/tests/v3_reports_typing.py`, and
  `python/tests/v3_logging_typing.py`.
  `python/tests/pyrightconfig.json` owns the strict Pyright target and source
  path for this fixture set.
- Build both the source distribution and wheel from `python/`; the wheel must
  rebuild successfully from the generated source archive.
- Run `python3 conformance/run-all.py` after shared semantic changes.

## Child DOX Index

- No child AGENTS.md files are currently required.
