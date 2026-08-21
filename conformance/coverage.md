# Phase 0 Requirement Coverage

Every case names the D10 rule it fixes. Later implementation phases extend this
table rather than weakening an existing expectation.

| Fixture                      | D10 contract fixed by the case                                                                            |
| ---------------------------- | --------------------------------------------------------------------------------------------------------- |
| `S00_compile_nested`         | Breadth-first placement IDs; deferred nested entry; scope-local concurrency; target-first links           |
| `S01_implicit_default`       | Successful zero-emission Node handler synthesizes one unlabelled route; successful `run()` projects state |
| `S02_explicit_input`         | Emitted input becomes the successor's exact branch input and is forwarded on exit                         |
| `S03_hard_end`               | `end(value)` bypasses ordinary links and creates one output-bearing End                                   |
| `S04_output_presence`        | `end()` contributes no output while `end(null)` contributes explicit null                                 |
| `S05_fanout_combine`         | Ordered fan-out; worker Ends; `ScopeResult.outputs`; zero-emission combine pass-through                   |
| `S06_combine_replacement`    | A combiner emission replaces child terminals with one Flow continuation                                   |
| `S07_declared_exit`          | A matching named Flow exit succeeds and retains action/input                                              |
| `S08_unknown_action`         | An unmatched named emission fails atomically as `unknown_action`; `run()` projects it through `RunError`  |
| `S09_nested_forwarding`      | Nested unlabelled Exit resolves through the Flow occurrence's parent link                                 |
| `S10_event_stats`            | Serial callback/transition/terminal publication order and exact basic counters                            |
| `S11_state_copy`             | Run state is a shallow top-level copy; caller top-level bindings remain unchanged                         |
| `S12_explicit_null_input`    | Explicit null branch input/output remains distinct from omission                                          |
| `S13_atomic_batch_rejection` | Complete-buffer preflight rejects every arm before any transition commits                                 |

## Definition coverage

| Fixture                   | D10 contract fixed by the case                                                                        |
| ------------------------- | ----------------------------------------------------------------------------------------------------- |
| `D00_definition_defaults` | Function occurrence, inferred name, resolved retry defaults, Flow defaults, and empty immutable links |
| `D01_configured_topology` | Occurrence identity, captured configuration, target-first links, declaration order, and named default |

`S00_compile_nested` is also executed through both production compilers. Its
accepted full description fixes root reservations, breadth-first placement and
scope IDs, deferred nested entry allocation, kind-specific fields, and compiled
automatic concurrency.

| Fixture                | Compilation-scale contract fixed by the case                              |
| ---------------------- | ------------------------------------------------------------------------- |
| `C00_100k_node_chain`  | Iterative linear graph traversal and contiguous portable element IDs      |
| `C01_10k_nested_flows` | Iterative containment validation, scope traversal, and deferred entry IDs |

## Production serial coverage

Both production runtimes execute `S01` through `S09` and `S11` through `S13`
against the accepted result/state projections. This fixes successful FIFO Node
execution, callback-local buffered control, zero-emission routing, hard Ends,
output presence, fan-out, Flow combination, nested forwarding, declared exits,
shared run-state visibility, top-level copy-in, and explicit null data. Direct
port tests additionally cover closed Context capabilities, durable state aliases,
terminal identity metadata, async callbacks, and 1,500 nonrecursive nested scopes.
The production adapters consume the exact public `start()` result, fixing
successful handle settlement, root-terminal exposure, and one stored result
identity as the observation path for this corpus.
`S08` additionally fixes one portable `unknown_action` Failure, its source/action
detail, failed handle settlement, and the exact `RunError` projection.
`S13` fixes complete-buffer preflight: a later invalid arm leaves direct state
writes visible but commits no earlier transition, activation, or terminal from
that callback batch.
State-carrier tests extend `S02`, `S11`, and `S12` with host-specific assertions
for descriptor-safe initial capture, exact top-level identity, shallow nested and
self aliases, separate-run isolation, normal Python dictionary operations,
exact-string key rejection before hashing, TypeScript record reflection and
mutation guards, and thenable-safe exact `run()` fulfillment.

## Failure and recovery coverage

| Fixture                         | D10 contract fixed by the case                                                        |
| ------------------------------- | ------------------------------------------------------------------------------------- |
| `F00_unhandled_handler`         | Canonical handler Failure, exact unrecovered root packet, and native cause projection |
| `F01_retry_success`             | Retry references the failed attempt and its exact Failure before successful retry     |
| `F02_node_recovery_consumes`    | Node recovery receives the packet/input and consumes it only through committed End    |
| `F03_node_recovery_passes`      | Zero-emission Node recovery propagates the exact original Failure                     |
| `F04_node_recovery_replaces`    | Throwing Node recovery creates one replacement with `previous` identity               |
| `F05_flow_recovery_consumes`    | Nearest nested Flow recovery receives controlling input and failing activation        |
| `F06_flow_recovery_passes`      | Zero-emission Flow recovery preserves and propagates the exact child packet           |
| `F07_flow_recovery_replaces`    | Throwing Flow recovery replaces once at the producing Flow                            |
| `F08_combine_recovery_consumes` | Combiner Failure exposes its exact result, pre-fence terminals, and null child ID     |
| `F09_combine_recovery_passes`   | Unhandled combiner Failure retains terminals while propagating the exact packet       |

Both independent references and both production adapters emit one byte-identical
snapshot for all ten fixtures. The snapshot includes canonical Failure messages,
IDs, source names, attempt provenance, `previous` identity, retry references,
recovery-visible state, terminal retention, and selected committed stats.

## Scheduling and cancellation coverage

| Fixture                              | D10 contract fixed by the case                                          |
| ------------------------------------ | ----------------------------------------------------------------------- |
| `Q00_auto_width`                     | Omitted global ceiling derives the root scope's declared callback width |
| `Q01_nested_auto_width`              | A serial parent does not throttle a parallel nested scope               |
| `Q02_global_ceiling`                 | Explicit global concurrency throttles a wider local scope               |
| `Q03_retry_ready_priority`           | Due retry admission precedes a waiting fresh activation                 |
| `Q04_fair_scope_rotation`            | Fresh callback admission rotates across eligible child scopes           |
| `Q05_sibling_signal_before_recovery` | A failed scope signals live siblings before entering Flow recovery      |
| `K00_cancel_before_admission`        | Pre-admission cancellation invokes no application callback              |
| `K01_cancel_after_buffer`            | Cancellation discards a live callback's buffered control                |
| `K02_post_signal_suppression`        | An unrelated post-signal handler error is suppressed exactly once       |
| `K03_prior_terminal_ready_discard`   | Committed terminals survive while later ready work is discarded         |
| `K04_cancel_retry_delay`             | Cancellation wakes a retry delay and retains its active packet          |
| `K05_cancel_node_recovery`           | Node-recovery cancellation retains the handler packet as suppression    |
| `K06_cancel_flow_recovery`           | Flow-recovery cancellation retains the handler packet as suppression    |

All thirteen cases are derived by two independent models and executed by both
production runtimes. The exact snapshots include status, state, terminal output
projection, suppression, portable scheduler observations, and committed stats.
Host elapsed time and native waiter-cancellation behavior stay in direct port
tests because they are not language-neutral values.

## Events, reports, observers, and limits coverage

| Fixture                   | D10 contract fixed by the case                                           |
| ------------------------- | ------------------------------------------------------------------------ |
| `E00_successful_trace`    | Exact versioned serial event order and transition/terminal linkage       |
| `E01_observer_skip`       | Synchronous callback-start cancellation skips application invocation     |
| `E02_observer_throw`      | First observer exception disables observation and retains one diagnostic |
| `R00_report_presence`     | Omitted report data remains distinct from explicit null                  |
| `R01_report_reentrant`    | Reentrant report publication is rejected and disables the observer       |
| `R02_report_overflow`     | First report beyond capacity commits one unrecoverable limit fence       |
| `L00_transition_overflow` | Buffered transition overflow commits no partial control arm              |
| `L01_capacity_priority`   | Run activation capacity wins before scope and ready capacity             |
| `L02_depth_limit`         | Nested-depth rejection allocates no child scope                          |
| `L03_attempt_limit`       | Exhausted attempt capacity invokes no target callback                    |

Both references and both runtimes emit one exact snapshot for all ten cases.
The event cases include complete kind and sequence order; report cases include
presence metadata and diagnostics; limit cases include exact detail,
provenance, committed counters, and application-observed interruption.

## Runtime-scale coverage

| Fixture              | D10 contract fixed by the case                                               |
| -------------------- | ---------------------------------------------------------------------------- |
| `X00_100k_node_run`  | Iterative execution of a 100,000-node chain with exact committed counters    |
| `X01_10k_nested_run` | Iterative entry, closure, and forwarding across 10,000 nested Flow scopes    |
| `X02_20k_fanout_run` | Bounded wide admission and exact ordered retention of 20,000 terminal arms   |
| `X03_64_reused_runs` | Concurrent compiled-graph reuse creates 64 isolated run-owned state carriers |

Both production runtimes execute the same scale fixture collection and emit
one byte-identical snapshot. Direct port stress tests separately fix bounded
representation and reference identity across a 10,000-Failure replacement
chain. The TypeScript browser harness bundles the public runtime for Chromium,
rejects Node.js built-in imports, and compares an exact fan-out/combine/report
and `run()` projection snapshot with `globalThis.process` absent.

## Later-phase coverage

- Definition and compilation coverage includes rejection, occurrence reuse,
  cycles, portable bounds, and large nonrecursive graphs. Runtime-scale
  coverage now fixes the corresponding execution boundaries and compiled-graph
  reuse; performance thresholds remain release evidence rather than semantic
  fixture values.
- The remaining shared corpus expands recovery/suppression, cancellation
  outcomes, and cross-port event snapshots. Direct port tests already fix
  successful `Completed` envelopes, portable serial handler/combine failures,
  handle deferral/identity, run projection, serial counter meanings, Node
  attempt ordinals, retry policy ordering and exact validation, chunked retry
  delays, failure `previous` chains, Node-recovery consume/pass-through, nearest
  Flow recovery, combiner-result failure context, controlling-input propagation,
  iterative nested packet escalation, cooperative caller cancellation, durable
  cancellation tokens, cancellation-aware retry delay, active-packet retention,
  post-signal suppression, cancellation-time ready-work discard, run deadlines,
  attempt timeouts, grace equality, post-timeout suppression, fresh retry and
  recovery tokens, advisory remaining time, and immutable abandonment.
  Mirrored resource-limit suites fix transition-buffer hard fencing, synthetic
  default and terminal-forwarding charges, atomic activation/ready/scope-cap
  rejection, nested-depth admission, attempt exhaustion, exact limit detail,
  normative priority, and no increments for rejected work.
  Mirrored scheduler suites additionally fix topology-derived callback width,
  explicit global throttling, nested local caps, the all-serial invariant,
  release during retry delay, callback-ready priority, fair rotation between
  eligible scopes, and sibling signalling before Flow recovery.
  Mirrored RunStats suites fix all committed counter meanings for Completed,
  Failed, Cancelled, and Abandoned results and freeze duration at terminal
  linearization before late abandoned work can finish.
  Mirrored event suites fix the versioned public schema, one-based run sequence,
  contiguous opening/transition/terminal publication, callback dispositions,
  nested pre-combine scope metadata, failure and retry references, synchronous
  cancellation delivery, nonfatal observer disablement/diagnostics, and the
  exclusion of terminal-observer time from duration.
  Mirrored report suites fix omission versus explicit nullish data, accepted
  accounting with and without observers, invalid-name and budget precedence,
  exact first-overflow fencing, observer reentrancy and cancellation, timer
  checkpoints after observer work, all lifecycle callback phases, and Context
  closure.
  Companion logging-adapter suites fix a synchronous one-record-per-event
  projection, matching severity policy, exact event retention without
  application-value formatting, and observer-diagnostic containment of sink
  errors. Adapter buffering and persistence remain outside core conformance.
- Phase 3 cross-port fixtures now fix retry scheduling, packet identity, Node and
  Flow recovery, replacement, and serial pass-through. Concurrent suppression
  snapshots remain in the scheduling/fence corpus.
- Phase 4 shared snapshots now fix callback ceilings, retry priority,
  ready-queue fairness, sibling fencing, caller cancellation, discard, and
  active-packet suppression. Overlapping timer fences and capacity ordering
  remain for the next shared corpus.
- Phase 5 shared snapshots now fix serial event publication, observer skip and
  disablement, report presence/reentrancy/budgets, and core capacity priority.
  Complete host-specific payload/reflection cases and browser/runtime parity
  remain direct checks; reference logging adapters are already mirrored.
