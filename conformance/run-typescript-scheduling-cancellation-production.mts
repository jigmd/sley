import { readFileSync } from 'node:fs'
import { Flow, node } from '../typescript/caskada.ts'

import type { Context, Failure, RunResult, ScopeFailure } from '../typescript/caskada.ts'

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
  return [await flow.start({}).result, { sibling_signalled: siblingSignalled }]
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
  if (program.scenario === 'cancel_before_admission') return cancelBeforeAdmission()
  if (program.scenario === 'cancel_after_buffer') return cancelAfterBuffer()
  if (program.scenario === 'post_signal_suppression') return postSignalSuppression()
  if (program.scenario === 'prior_terminal_ready_discard') return priorTerminalReadyDiscard()
  if (program.scenario === 'cancel_retry_delay') return cancelRetryDelay()
  if (program.scenario === 'cancel_node_recovery') return cancelRecovery('node')
  if (program.scenario === 'cancel_flow_recovery') return cancelRecovery('flow')
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
