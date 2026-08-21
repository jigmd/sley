# Caskada V3 Conformance

This directory is the executable interpretation of the accepted D10 serial
contract. It is deliberately independent of `python/caskada/__init__.py` and
`typescript/caskada.ts`; production runtimes must eventually consume these
fixtures through their own adapters rather than becoming the expected-value
oracle.

`fixtures/serial.json` contains a small declarative graph program and an exact
normalized expectation for every case. `fixture.schema.json` describes that
format. `fixtures/failure-recovery.json` and
`failure-recovery.schema.json` define a smaller serial packet machine for retry,
Node recovery, Flow recovery, replacement, and pass-through. Omitted values use
a fixture-level host-missing marker so omission stays different from explicit
JSON `null` in both languages.

`fixtures/scheduling-cancellation.json` and
`scheduling-cancellation.schema.json` define deterministic admission and fence
scenarios. Two independent references model the portable facts; production
adapters use real async gates without comparing elapsed host time.

`fixtures/events-reports-limits.json` and
`events-reports-limits.schema.json` define exact event publication, observer
diagnostic, report-presence, and resource-precedence cases.

`fixtures/runtime-scale.json` exercises both production runtimes at the
accepted nonrecursive scale boundaries: a 100,000-node run, 10,000 nested Flow
scopes, 20,000 fan-out arms, and 64 concurrent invocations of one compiled
graph. The fixture records exact portable counters and boundary values rather
than machine-dependent timings.

## Run

```bash
python3 conformance/run-all.py
```

The cross-port runner first verifies the accepted baseline manifest, then
executes both references and every completed production adapter, requires
byte-identical canonical JSON, and fails on the first structural mismatch.
Reference interpreters do not import production runtime modules.

The underlying commands remain useful while debugging one port:

```bash
python3 conformance/run-python.py
node --import=tsx conformance/run-typescript.mts
```

## Scope

Phase 0 covers deterministic serial author semantics and normalized topology:
implicit routing, explicit branch input, hard terminals, output presence,
fan-out, Flow combination and replacement, declared exits, unknown actions,
nested forwarding, state-copy isolation, event order, and exact basic stats.
Concurrency, retry packets, timers, cancellation, observers, and resource-bound
stress cases enter the corpus in the later RFC implementation phases identified
in `coverage.md`.

The failure/recovery corpus covers unhandled handler failure, `RunError` native
cause identity, retry success,
Node and Flow recovery consumption, exact zero-emission pass-through, universal
replacement with `previous`, nearest nested recovery, and combiner-failure
context. Its references are independent of both production runtimes.

`fixtures/definitions.json` is the first production-runtime corpus. It checks
the graph-definition layer without invoking compilation or execution;
host-specific constructor, dynamic-call, option-capture, and static-type cases
remain in each runtime's own tests.

The production compile adapters also build `S00_compile_nested` from
`fixtures/serial.json` and require both `describe()` results to equal its one
accepted full compiled description.

The production serial adapters execute twelve runtime fixtures through the real
Python and TypeScript kernels. They read each public `RunHandle` result, require
byte-equivalent state, terminal, and implemented failure projections, and then
compare that shared snapshot with the accepted fixture expectations.

The failure/recovery adapters execute ten additional packet fixtures and compare
normalized Failure identity, retry references, recovery observations, terminal
retention, and committed stats with both independent reference machines.

The scheduling/cancellation adapters execute thirteen cases covering automatic
and explicit callback ceilings, retry priority, cross-scope fairness, sibling
fencing, caller cancellation, buffer and ready-work discard, active-packet
retention, and post-signal suppression. Their snapshots include exact portable
observations and committed stats, but deliberately exclude wall-clock values.

The events/reports/limits adapters execute ten cases covering a complete serial
event trace, observer-driven invocation skip, observer disablement, report data
presence, report reentrancy and overflow, atomic transition overflow, capacity
priority, nested-depth admission, and attempt exhaustion.

The runtime-scale adapters execute four production-only cases through the real
Python and TypeScript kernels. They require exact agreement on committed
counters, terminal cardinality and ordering boundaries, and isolated state
carrier identity across concurrent reuse.
