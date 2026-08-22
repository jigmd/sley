# Python API

The package requires Python 3.13 or newer. The normative contract is
[RFC 0001](../architecture/rfcs/0001-caskada-v3-runtime.md).

## Graphs

```python
node(
    handler=None,
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy | None = None,
    recover=None,
) -> Node
```

`node` accepts a handler directly or acts as `@node` / `@node(...)`. Handlers
and recovery callbacks may be synchronous or asynchronous and return `None`.

```python
@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    should_retry: Callable[[Failure], bool] = retry_all
    delay_ms: int | Callable[[int, Failure], int] = 0
```

Every `Node` and `Flow` is a `GraphElement`:

```python
source.link(target)
source.link(target, "review")
source.links()  # declaration-ordered tuple[Link, ...]
```

A source has at most one unlabelled link and one link per named action.

```python
Flow(
    entry,
    *,
    name: str = "Flow",
    exits: Iterable[str] = (),
    concurrency: int = 1,
    max_activations: int | None = None,
    combine=None,
    recover=None,
)
```

Flows may be nested and linked like Nodes. `compile()` snapshots reachable
topology. `CompiledFlow.describe()` returns plain topology and policy records.

## Context

```python
class Context(Protocol, Generic[StateT, InputT]):
    state: StateT
    input: InputT

    def emit(self) -> None: ...
    def emit(self, *, input: object) -> None: ...
    def emit(self, action: str) -> None: ...
    def emit(self, action: str, input: object) -> None: ...
    def end(self) -> None: ...
    def end(self, output: object) -> None: ...
```

`state` is one shallow-copied mapping shared by the run. `input` is one branch
message. An omitted emission input forwards the current input. `end()` and
`end(None)` differ: the first has no output and the second outputs `None`.

## Execution

```python
compiled = flow.compile()
handle = compiled.start(initial_state)
result = await handle.result()
state = await compiled.run(initial_state)
```

`start()` requires a running asyncio loop and returns immediately. A handle has
only `done()` and async `result()`. `run()` returns state for `Completed` and
raises `RunError` with the exact `Failed` result otherwise.

`RunResult` has two variants:

```text
Completed(state, terminals, status="completed")
Failed(state, terminals, failure, status="failed")
```

`ScopeResult.terminals` contains all settled branch terminals.
`ScopeResult.outputs` projects only output-bearing values for `combine`.
`ScopeFailure` gives Flow recovery the primary Failure, settled terminals, an
optional failed combine result, and the failing activation id.

## Errors

- `GraphDefinitionError`: invalid definition or callback policy
- `DuplicateLinkError`: duplicate unlabelled or named link
- `RunError`: unhandled workflow failure projected by `run()`
- `TypeError`: invalid initial state carrier

Application exceptions become `Failure` records for retry and recovery.
Invalid definitions, control arguments, callback returns, policy returns, and
closed Context access fail at their boundary.
