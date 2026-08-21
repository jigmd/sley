import { readFileSync } from 'node:fs'
import { Flow, node } from '../typescript/caskada.ts'

import type { Context, Failure, RunEvent, RunResult, ScopeFailure } from '../typescript/caskada.ts'

const FIXTURE_PATH = new URL('./fixtures/scheduling-cancellation.json', import.meta.url)
const CANCEL_REASON = 'fixture-cancel'

type State = Record<string, unknown>
type Program = {
  readonly scenario: string
  readonly width?: number
  readonly max_concurrency?: number
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalize(item)]),
    )
  }
  return value
}

class FixtureError extends Error {}

function deferred(): { readonly promise: Promise<void>; readonly resolve: () => void } {
  let resolve!: () => void
  const promise = new Promise<void>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

function waitForCancellation(context: Context<State, unknown>): Promise<void> {
  return new Promise<void>((resolve) => {
    context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true })
  })
}

function blockFor(milliseconds: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds)
}

function portableReason(value: unknown): unknown {
  if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) return value
  if (typeof value === 'object') return value.constructor?.name ?? 'object'
  return typeof value
}

async function gatedWidth(
  width: number,
  options: { readonly nested: boolean; readonly maxConcurrency?: number },
): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  let active = 0
  let peak = 0
  const threshold = options.maxConcurrency ?? width
  const started = deferred()
  const release = deferred()
  const dispatch = node<State>(
    (context) => {
      for (let index = 0; index < width; index += 1) context.emit('work', index)
    },
    { name: 'dispatch' },
  )
  const work = node<State, number>(
    async () => {
      active += 1
      peak = Math.max(peak, active)
      if (active === threshold) started.resolve()
      await release.promise
      active -= 1
    },
    { name: 'work' },
  )
  dispatch.link(work, 'work')
  let flow = new Flow(dispatch, { name: 'parallel', concurrency: width })
  if (options.nested) flow = new Flow(flow, { name: 'root', concurrency: 1 })
  const handle = flow.start({}, options.maxConcurrency === undefined ? undefined : { maxConcurrency: options.maxConcurrency })
  await started.promise
  release.resolve()
  return [await handle.result, { peak }]
}

async function retryReadyPriority(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const order: string[] = []
  const blockerStarted = deferred()
  const retryScheduled = deferred()
  const releaseBlocker = deferred()
  const dispatch = node<State>(
    (context) => {
      context.emit('work', 'retry')
      context.emit('work', 'blocker')
      context.emit('work', 'new')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    async (context) => {
      order.push(`${context.input}:${context.attempt}`)
      if (context.input === 'retry' && context.attempt === 1) throw new FixtureError('retry')
      if (context.input === 'blocker') {
        blockerStarted.resolve()
        await releaseBlocker.promise
      }
    },
    {
      name: 'work',
      retry: {
        maxAttempts: 2,
        delayMs(_attempt: number, _failure: Failure): number {
          retryScheduled.resolve()
          return 1
        },
      },
    },
  )
  dispatch.link(work, 'work')
  const handle = new Flow(dispatch, { concurrency: 3 }).start({}, { maxConcurrency: 1 })
  await blockerStarted.promise
  await retryScheduled.promise
  await new Promise((resolve) => setTimeout(resolve, 10))
  releaseBlocker.resolve()
  return [await handle.result, { order }]
}

async function fairScopeRotation(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const order: Array<readonly [string, number]> = []
  const rootDispatch = node<State>(
    (context) => {
      context.emit('batch', 'A')
      context.emit('batch', 'B')
    },
    { name: 'root_dispatch' },
  )
  const childDispatch = node<State, string>(
    (context) => {
      for (let index = 0; index < 3; index += 1) context.emit('work', [context.input, index] as const)
    },
    { name: 'child_dispatch' },
  )
  const work = node<State, readonly [string, number]>(
    async (context) => {
      order.push(context.input)
      await Promise.resolve()
    },
    { name: 'work' },
  )
  childDispatch.link(work, 'work')
  rootDispatch.link(new Flow(childDispatch, { name: 'child', concurrency: 3 }), 'batch')
  const result = await new Flow(rootDispatch, { concurrency: 2 }).start({}, { maxConcurrency: 1 }).result
  const b0 = order.findIndex(([label, index]) => label === 'B' && index === 0)
  const a2 = order.findIndex(([label, index]) => label === 'A' && index === 2)
  return [result, { work_count: order.length, b0_before_a2: b0 < a2 }]
}

async function siblingSignal(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  let siblingSignalled = false
  let scopeReason: unknown = null
  const dispatch = node<State>(
    (context) => {
      context.emit('work', 'failure')
      context.emit('work', 'sibling')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    async (context) => {
      if (context.input === 'failure') {
        await Promise.resolve()
        throw new FixtureError('failure')
      }
      await waitForCancellation(context)
      siblingSignalled = context.cancellation.cancelled
      scopeReason = context.cancellation.reason
    },
    { name: 'work' },
  )
  dispatch.link(work, 'work')
  const flow = new Flow(dispatch, {
    concurrency: 2,
    recover(context: Context<State>, _failure: ScopeFailure): void {
      context.state.recovered = true
      context.end()
    },
  })
  return [await flow.start({}).result, { scope_reason: portableReason(scopeReason), sibling_signalled: siblingSignalled }]
}

async function parkedRetryPacket(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const retryScheduled = deferred()
  const parkedCause = new FixtureError('parked')
  const controllerCause = new FixtureError('controller')
  const dispatch = node<State>(
    (context) => {
      context.emit('work', 'parked')
      context.emit('work', 'controller')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    async (context) => {
      if (context.input === 'parked') throw parkedCause
      await retryScheduled.promise
      throw controllerCause
    },
    {
      name: 'work',
      retry: {
        maxAttempts: 2,
        shouldRetry: (failure) => failure.cause === parkedCause,
        delayMs() {
          retryScheduled.resolve()
          return 4_294_967_295
        },
      },
    },
  )
  dispatch.link(work, 'work')
  const result = await new Flow(dispatch, { concurrency: 2 }).start({}, { maxConcurrency: 2 }).result
  return [
    result,
    {
      primary_is_controller: result.status === 'failed' && result.failure.cause === controllerCause,
      suppressed_is_parked: 'suppressed' in result && result.suppressed.length === 1 && result.suppressed[0]!.cause === parkedCause,
    },
  ]
}

async function attemptLimitBeforePermit(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const calls: string[] = []
  const dispatch = node<State>(
    (context) => {
      calls.push('source')
      context.emit('work', 'first')
      context.emit('work', 'second')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    async (context) => {
      calls.push(context.input)
      await waitForCancellation(context)
      context.cancellation.throwIfCancelled()
    },
    { name: 'work' },
  )
  dispatch.link(work, 'work')
  const result = await new Flow(dispatch, { concurrency: 2 }).start({}, { maxAttempts: 2, maxConcurrency: 2 }).result
  const detail = result.status === 'failed' ? result.failure.detail : null
  return [result, { calls, limit: detail?.type === 'limit' ? detail.limit : null }]
}

async function retryPriority(observerDelay: boolean): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const order: string[] = []
  const dispatch = node<State>(
    (context) => {
      context.emit('work', 'retry')
      context.emit('work', 'peer')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    (context) => {
      order.push(`${context.input}:${context.attempt}`)
      if (context.input === 'retry' && context.attempt === 1) throw new FixtureError('retry')
    },
    {
      name: 'work',
      retry: { maxAttempts: 2, delayMs: observerDelay ? 1 : 0 },
    },
  )
  dispatch.link(work, 'work')
  const observer = observerDelay
    ? (event: RunEvent): undefined => {
        if (event.kind === 'retry_scheduled') blockFor(10)
        return undefined
      }
    : undefined
  const result = await new Flow(dispatch, { concurrency: 2 }).start({}, { maxConcurrency: 1, observer }).result
  return [result, { order }]
}

async function nodeRecoveryPriority(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const order: string[] = []
  const dispatch = node<State>(
    (context) => {
      context.emit('work', 'bad')
      context.emit('work', 'peer')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    (context) => {
      order.push(`handle:${context.input}`)
      if (context.input === 'bad') throw new FixtureError('bad')
    },
    {
      name: 'work',
      recover(context) {
        order.push(`recover:${context.input}`)
        context.end('recovered')
      },
    },
  )
  dispatch.link(work, 'work')
  const result = await new Flow(dispatch, { concurrency: 2 }).start({}, { maxConcurrency: 1 }).result
  return [result, { order }]
}

async function readyWaiterCapacity(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const calls: string[] = []
  const dispatch = node<State>(
    (context) => {
      calls.push('dispatch')
      context.emit('run', 'active')
      context.emit('run', 'waiting')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    async (context) => {
      calls.push(context.input)
      if (context.input === 'active') {
        await Promise.resolve()
        context.emit('child', 1)
        context.emit('child', 2)
      }
    },
    { name: 'work' },
  )
  work.link(
    node<State, number>(() => undefined, { name: 'child' }),
    'child',
  )
  dispatch.link(work, 'run')
  const result = await new Flow(dispatch, { concurrency: 2 }).start({}, { maxConcurrency: 1, maxReady: 2 }).result
  const detail = result.status === 'failed' ? result.failure.detail : null
  return [result, { calls, limit: detail?.type === 'limit' ? detail.limit : null }]
}

async function cancelBeforeAdmission(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  let called = false
  const handle = new Flow(
    node<State>(
      () => {
        called = true
      },
      { name: 'work' },
    ),
  ).start({})
  handle.cancel(CANCEL_REASON)
  return [await handle.result, { called }]
}

async function cancelAfterBuffer(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const started = deferred()
  const work = node<State>(
    async (context) => {
      context.end('discarded')
      started.resolve()
      await waitForCancellation(context)
    },
    { name: 'work' },
  )
  const handle = new Flow(work).start({})
  await started.promise
  handle.cancel(CANCEL_REASON)
  return [await handle.result, {}]
}

async function postSignalSuppression(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const started = deferred()
  const work = node<State>(
    async (context) => {
      started.resolve()
      await waitForCancellation(context)
      throw new FixtureError('after signal')
    },
    { name: 'work' },
  )
  const handle = new Flow(work).start({})
  await started.promise
  handle.cancel(CANCEL_REASON)
  return [await handle.result, {}]
}

async function priorTerminalReadyDiscard(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const waiting = deferred()
  const dispatch = node<State>(
    (context) => {
      context.emit('done', 1)
      context.emit('wait', 2)
      context.emit('late', 3)
    },
    { name: 'dispatch' },
  )
  dispatch.link(
    node<State, number>((context) => context.end(context.input), { name: 'done' }),
    'done',
  )
  dispatch.link(
    node<State, number>(
      async (context) => {
        waiting.resolve()
        await waitForCancellation(context)
      },
      { name: 'wait' },
    ),
    'wait',
  )
  dispatch.link(
    node<State, number>(
      (context) => {
        context.state.late = context.input
      },
      { name: 'late' },
    ),
    'late',
  )
  const handle = new Flow(dispatch).start({})
  await waiting.promise
  handle.cancel(CANCEL_REASON)
  const result = await handle.result
  return [result, { late_present: 'late' in result.state }]
}

async function cancelRetryDelay(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const scheduled = deferred()
  const work = node<State>(
    () => {
      throw new FixtureError('retry')
    },
    {
      name: 'work',
      retry: {
        maxAttempts: 2,
        delayMs(): number {
          scheduled.resolve()
          return 4_294_967_295
        },
      },
    },
  )
  const handle = new Flow(work).start({})
  await scheduled.promise
  handle.cancel(CANCEL_REASON)
  return [await handle.result, {}]
}

async function cancelRecovery(layer: 'node' | 'flow'): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const started = deferred()
  const fail = (): never => {
    throw new FixtureError('handler')
  }
  const nodeRecovery = async (context: Context<State>, _failure: Failure): Promise<void> => {
    started.resolve()
    await waitForCancellation(context)
    context.cancellation.throwIfCancelled()
  }
  const flowRecovery = async (context: Context<State>, _failure: ScopeFailure): Promise<void> => {
    started.resolve()
    await waitForCancellation(context)
    context.cancellation.throwIfCancelled()
  }
  const entry = node<State>(fail, { name: 'work', recover: layer === 'node' ? nodeRecovery : undefined })
  const flow = new Flow(entry, { recover: layer === 'flow' ? flowRecovery : undefined })
  const handle = flow.start({})
  await started.promise
  handle.cancel(CANCEL_REASON)
  return [await handle.result, {}]
}

function fenceObserver(fences: string[]): (event: RunEvent) => undefined {
  return (event) => {
    if (event.kind === 'failure_fenced' || event.kind === 'cancellation_fenced') {
      fences.push(`${event.kind}:${event.payload.target.kind}`)
    } else if (event.kind === 'run_finished') {
      fences.push(`run_finished:${event.payload.status}`)
    }
    return undefined
  }
}

async function failureGraceAbandonment(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const siblingStarted = deferred()
  const releaseSibling = deferred()
  const fences: string[] = []
  let recoveryCalled = false
  const dispatch = node<State>(
    (context) => {
      context.emit('work', 'sibling')
      context.emit('work', 'failure')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    async (context) => {
      if (context.input === 'sibling') {
        siblingStarted.resolve()
        await releaseSibling.promise
        return
      }
      await siblingStarted.promise
      throw new FixtureError('failure')
    },
    { name: 'work' },
  )
  dispatch.link(work, 'work')
  const flow = new Flow(dispatch, {
    concurrency: 2,
    recover(context) {
      recoveryCalled = true
      context.end()
    },
  })
  let result: RunResult<State>
  try {
    result = await flow.start({}, { maxConcurrency: 2, cancelGraceMs: 0, observer: fenceObserver(fences) }).result
  } finally {
    releaseSibling.resolve()
    await Promise.resolve()
  }
  return [result, { fences, recovery_called: recoveryCalled }]
}

async function retrySuppressionUnique(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const lateAttemptOne = new FixtureError('late attempt one')
  const secondAttempt = new FixtureError('second attempt')
  const work = node<State>(
    async (context) => {
      if (context.attempt === 1) {
        await waitForCancellation(context)
        throw lateAttemptOne
      }
      throw secondAttempt
    },
    { name: 'work', timeoutMs: 1, retry: { maxAttempts: 2 } },
  )
  const result = await new Flow(work).start({}, { cancelGraceMs: 100 }).result
  const primary = result.status === 'failed' ? result.failure : null
  const suppressed = 'suppressed' in result ? result.suppressed : []
  return [
    result,
    {
      primary_is_second_attempt: primary?.kind === 'handler' && primary.attempt === 2 && primary.cause === secondAttempt,
      previous_is_timeout: primary?.previous?.kind === 'handler_timeout',
      suppression_is_unique:
        suppressed.length === 1 &&
        suppressed[0]!.kind === 'handler' &&
        suppressed[0]!.attempt === 1 &&
        suppressed[0]!.cause === lateAttemptOne,
    },
  ]
}

async function concurrentCancelAbandonment(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  let active = 0
  const bothStarted = deferred()
  const releaseStuck = deferred()
  const fences: string[] = []
  const dispatch = node<State>(
    (context) => {
      context.emit('work', 'cooperative')
      context.emit('work', 'stuck')
    },
    { name: 'dispatch' },
  )
  const work = node<State, string>(
    async (context) => {
      active += 1
      if (active === 2) bothStarted.resolve()
      if (context.input === 'stuck') {
        await releaseStuck.promise
        return
      }
      await waitForCancellation(context)
      context.cancellation.throwIfCancelled()
    },
    { name: 'work' },
  )
  dispatch.link(work, 'work')
  const handle = new Flow(dispatch, { concurrency: 2 }).start(
    {},
    { maxConcurrency: 2, cancelGraceMs: 0, observer: fenceObserver(fences) },
  )
  await bothStarted.promise
  handle.cancel(CANCEL_REASON)
  let result: RunResult<State>
  try {
    result = await handle.result
  } finally {
    releaseStuck.resolve()
    await Promise.resolve()
  }
  return [result, { fences }]
}

async function syncRetryPolicyGrace(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  let handle!: ReturnType<Flow<State>['start']>
  const recordedFailureKinds: string[] = []
  const worker = node<State>(
    () => {
      throw new FixtureError('handler')
    },
    {
      name: 'work',
      retry: {
        maxAttempts: 2,
        shouldRetry() {
          handle.cancel(CANCEL_REASON)
          blockFor(10)
          throw new FixtureError('late retry policy')
        },
      },
    },
  )
  handle = new Flow(worker).start(
    {},
    {
      cancelGraceMs: 0,
      observer(event) {
        if (event.kind === 'failure_recorded') recordedFailureKinds.push(event.payload.failure.kind)
        return undefined
      },
    },
  )
  return [await handle.result, { recorded_failure_kinds: recordedFailureKinds }]
}

async function routePacketCancellation(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  let handle!: ReturnType<Flow<State>['start']>
  const work = node<State>(
    async (context) => {
      if (context.attempt === 1) {
        await waitForCancellation(context)
        throw new FixtureError('after timeout')
      }
      context.end('discarded')
    },
    { name: 'work', timeoutMs: 1, retry: { maxAttempts: 2 } },
  )
  handle = new Flow(work).start(
    {},
    {
      cancelGraceMs: 100,
      observer(event) {
        if (event.kind === 'callback_finished' && event.payload.phase === 'handle' && event.payload.attempt === 2) {
          handle.cancel(CANCEL_REASON)
        }
        return undefined
      },
    },
  )
  return [await handle.result, {}]
}

async function nestedScopeFailureStatus(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  const scopeFinishes: string[] = []
  const child = new Flow(
    node<State>((context) => context.end(), { name: 'leaf' }),
    {
      name: 'child',
      combine() {
        throw new FixtureError('combine')
      },
    },
  )
  const root = new Flow(child, {
    name: 'root',
    concurrency: 2,
    recover(context) {
      context.state.recovered = true
      context.end()
    },
  })
  const result = await root.start(
    {},
    {
      observer(event) {
        if (event.kind === 'scope_finished') scopeFinishes.push(`${event.payload.scopeId}:${event.payload.status}`)
        return undefined
      },
    },
  ).result
  return [result, { scope_finishes: scopeFinishes }]
}

async function openingObserverDeadline(): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  let called = false
  const work = node<State>(
    () => {
      called = true
    },
    { name: 'work' },
  )
  const handle = new Flow(work).start(
    {},
    {
      deadlineMs: 1,
      cancelGraceMs: 100,
      observer(event) {
        if (event.kind === 'run_started') blockFor(10)
        return undefined
      },
    },
  )
  const doneOnReturn = handle.done
  return [await handle.result, { called, done_on_return: doneOnReturn }]
}

async function runProgram(program: Program): Promise<readonly [RunResult<State>, Record<string, unknown>]> {
  if (program.scenario === 'auto_width' || program.scenario === 'nested_auto_width' || program.scenario === 'global_ceiling') {
    if (program.width === undefined) throw new Error('width is required')
    return gatedWidth(program.width, {
      nested: program.scenario === 'nested_auto_width',
      ...(program.max_concurrency === undefined ? {} : { maxConcurrency: program.max_concurrency }),
    })
  }
  if (program.scenario === 'retry_ready_priority') return retryReadyPriority()
  if (program.scenario === 'fair_scope_rotation') return fairScopeRotation()
  if (program.scenario === 'sibling_signal_before_recovery') return siblingSignal()
  if (program.scenario === 'parked_retry_packet') return parkedRetryPacket()
  if (program.scenario === 'attempt_limit_before_permit') return attemptLimitBeforePermit()
  if (program.scenario === 'zero_delay_retry_priority') return retryPriority(false)
  if (program.scenario === 'observer_retry_delay') return retryPriority(true)
  if (program.scenario === 'node_recovery_priority') return nodeRecoveryPriority()
  if (program.scenario === 'ready_waiter_capacity') return readyWaiterCapacity()
  if (program.scenario === 'cancel_before_admission') return cancelBeforeAdmission()
  if (program.scenario === 'cancel_after_buffer') return cancelAfterBuffer()
  if (program.scenario === 'post_signal_suppression') return postSignalSuppression()
  if (program.scenario === 'prior_terminal_ready_discard') return priorTerminalReadyDiscard()
  if (program.scenario === 'cancel_retry_delay') return cancelRetryDelay()
  if (program.scenario === 'cancel_node_recovery') return cancelRecovery('node')
  if (program.scenario === 'cancel_flow_recovery') return cancelRecovery('flow')
  if (program.scenario === 'failure_grace_abandonment') return failureGraceAbandonment()
  if (program.scenario === 'retry_suppression_unique') return retrySuppressionUnique()
  if (program.scenario === 'concurrent_cancel_abandonment') return concurrentCancelAbandonment()
  if (program.scenario === 'sync_retry_policy_grace') return syncRetryPolicyGrace()
  if (program.scenario === 'route_packet_cancellation') return routePacketCancellation()
  if (program.scenario === 'nested_scope_failure_status') return nestedScopeFailureStatus()
  if (program.scenario === 'opening_observer_deadline') return openingObserverDeadline()
  throw new Error(`unknown scheduling/cancellation scenario ${program.scenario}`)
}

function normalize(result: RunResult<State>, observations: Record<string, unknown>): Record<string, unknown> {
  const suppressed =
    'suppressed' in result ? result.suppressed.map((failure) => ({ kind: failure.kind, attempt: failure.attempt })) : []
  const normalizedResult: Record<string, unknown> = {
    status: result.status,
    state: { ...result.state },
    terminal_count: result.terminals.length,
    outputs: result.terminals.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.output),
    suppressed,
  }
  if (result.status === 'cancelled') {
    normalizedResult.cancellation = {
      reason: result.cancellation.reason,
      deadline: result.cancellation.deadline,
    }
  } else if (result.status === 'abandoned') {
    normalizedResult.cause =
      'kind' in result.cause
        ? { type: 'failure', kind: result.cause.kind, attempt: result.cause.attempt }
        : { type: 'cancellation', reason: result.cause.reason, deadline: result.cause.deadline }
  }
  return {
    result: normalizedResult,
    observations,
    stats: {
      activations: result.stats.activations,
      attempts: result.stats.attempts,
      transitions: result.stats.transitions,
      retries: result.stats.retries,
      scopes: result.stats.scopes,
      peak_callbacks: result.stats.peakCallbacks,
    },
  }
}

const collection = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8')) as {
  readonly fixtures: ReadonlyArray<{ readonly id: string; readonly program: Program }>
}
const fixtures: Array<Record<string, unknown>> = []
for (const fixture of collection.fixtures) {
  const [result, observations] = await runProgram(fixture.program)
  fixtures.push({ id: fixture.id, snapshot: normalize(result, observations) })
}
process.stdout.write(JSON.stringify(canonicalize({ schema_version: 1, fixtures })) + '\n')
