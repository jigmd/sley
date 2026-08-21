# Python API

The Python package requires Python 3.13 or newer. The normative cross-language
contract is [RFC 0001](../internal/rfcs/0001-caskada-v3-runtime.md).

## Graph Definition

```python
node(
    handler=None,
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),
    timeout_ms: int | None = None,
    recover=None,
) -> Node
```

`node` accepts a handler directly or acts as `@node` / `@node(...)` decorator
sugar. Handlers and recovery callbacks may be synchronous or asynchronous and
must return `None`.

```python
@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    should_retry: Callable[[Failure], bool] = retry_all
    delay_ms: int | Callable[[int, Failure], int] = 0
```

```python
class GraphElement(Generic[StateT]):
    @property
    def name(self) -> str: ...
    def link(self, target, action: str = ...) -> None: ...
    def links(self) -> tuple[Link, ...]: ...
```

`Node` is final and created only by `node(...)`.

```python
Flow(
    entry,
    *,
    name: str | None = None,
    exits: Sequence[str] = (),
    concurrency: int = 1,
    max_activations: int | None = None,
    combine=None,
    recover=None,
)
```

`Flow` is also a `GraphElement`, so it may be nested or linked in a parent
graph.

## Context

```python
class Context(Protocol, Generic[StateT, InputT]):
    state: StateT
    input: InputT
    run_id: str
    scope_id: int
    activation_id: int
    parent_activation_id: int | None
    attempt: int | None
    phase: Phase
    cancellation: Cancellation

    def remaining_ms(self) -> int | None: ...
    def emit(self) -> None: ...
    def emit(self, *, input: object) -> None: ...
    def emit(self, action: str) -> None: ...
    def emit(self, action: str, input: object) -> None: ...
    def end(self) -> None: ...
    def end(self, output: object) -> None: ...
    def report(self, name: str) -> None: ...
    def report(self, name: str, data: object) -> None: ...
```

Python distinguishes unlabelled replacement input with
`context.emit(input=value)`. Omitted and explicit `None` values are distinct for
input, End output, and report data.

```python
class Cancellation(Protocol):
    cancelled: bool
    reason: object
    async def wait(self) -> None: ...
    def raise_if_cancelled(self) -> None: ...
```

## Execution

```python
class Flow:
    def compile(self) -> CompiledFlow: ...
    def start(self, initial_state, *, options: RunOptions | None = None) -> RunHandle: ...
    async def run(self, initial_state, *, options: RunOptions | None = None): ...
```

`start()` requires a running asyncio event loop. It validates options, compiles
the graph, captures state, and returns a handle synchronously. `run()` awaits
the handle, returns state for `Completed`, and raises `RunError` for every other
status.

```python
class RunHandle(Protocol):
    def cancel(self, reason: object = "cancelled") -> None: ...
    def done(self) -> bool: ...
    async def result(self) -> RunResult: ...
```

```python
@dataclass(frozen=True, slots=True)
class RunOptions:
    max_concurrency: int | None = None
    max_activations: int = 100_000
    max_attempts: int = 200_000
    max_transitions: int = 200_000
    max_ready: int = 100_000
    max_reports: int = 100_000
    max_depth: int = 32
    deadline_ms: int | None = None
    cancel_grace_ms: int = 1_000
    observer: Observer | None = None
    run_id: str | None = None
```

`CompiledFlow.describe()` returns the portable compiled graph description.
`CompiledFlow.start()` and `.run()` execute the same snapshot without
recompiling.

## Results And Failures

`RunResult` is the union of `Completed`, `Failed`, `Cancelled`, and `Abandoned`.
Every variant exposes the run-owned `state`, terminal collection, statistics,
and observer diagnostics. Failure-like variants add their structured cause and
suppressed failures.

`RunError.result` retains the exact non-completed result raised by `run()`. If a
native exception caused the controlling Failure, `RunError.__cause__` is that
exact exception.

`ScopeResult` exposes `terminals` and the value-only `outputs` projection to
Flow combine callbacks. `ScopeFailure` supplies structured boundary recovery
data.

`Failure` contains stable kind, canonical message, caught cause when one exists,
scope/activation/element/attempt provenance, structured detail, and a previous
replacement link. Compare Failure objects by identity.

## Events And Logging

`RunOptions.observer` receives synchronous `RunEvent` objects. Event kinds are:

- `run_started`, `run_finished`
- `scope_started`, `scope_finished`
- `callback_started`, `callback_finished`
- `retry_scheduled`
- `transition_committed`, `terminal_committed`
- `failure_recorded`, `failure_fenced`, `cancellation_fenced`
- `report`

The schema version is `RUN_EVENT_SCHEMA_VERSION`.

The optional standard logging adapter is separate from the core:

```python
from caskada_logging import logging_observer
```

## Errors

- `GraphDefinitionError`: invalid graph definition or callback configuration
- `DuplicateLinkError`: duplicate unlabelled or named link
- `OptionValidationError`: invalid run options or initial state capture
- `RunError`: a completed handle whose result is not `Completed`

Framework lifecycle failures are data in `RunResult`. Synchronous misuse of a
closed Context or invalid state-carrier operation raises at the call site.
