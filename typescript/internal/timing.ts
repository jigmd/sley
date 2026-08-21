// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// Cancellation, callback permits, deadlines, and callback races.

import { intrinsicPromiseThen, MAX_HOST_TIMER_DELAY_MS } from './contracts.js'
import { isFailureFence, ProducedFailure, RunAbandoned, RunCancelled } from './failures.js'

import type { Cancellation, Failure } from './contracts.js'

type CallbackCompletion = {
  readonly result: unknown
  readonly error: unknown
  readonly failed: boolean
  readonly settledMs: number
}

export class RuntimeDeadline {
  constructor(
    readonly originMs: number,
    readonly durationMs: number,
  ) {}

  due(nowMs = performance.now()): boolean {
    return nowMs - this.originMs >= this.durationMs
  }

  remainingMs(nowMs = performance.now()): number {
    return Math.max(0, Math.ceil(this.durationMs - (nowMs - this.originMs)))
  }
}

export class RuntimeCancellation implements Cancellation {
  private readonly controller = new AbortController()
  private readonly parent: RuntimeCancellation | undefined
  private readonly parentListener: (() => void) | undefined
  private runtimeDeadline = false
  private runtimeFencedAtMs: number | undefined

  constructor(parent?: RuntimeCancellation) {
    this.parent = parent
    if (parent === undefined) return
    const propagate = (): void => {
      this.cancel(parent.reason, parent.deadline, parent.fencedAtMs)
    }
    this.parentListener = propagate
    if (parent.cancelled) propagate()
    else parent.signal.addEventListener('abort', propagate, { once: true })
  }

  get cancelled(): boolean {
    return this.controller.signal.aborted
  }

  get reason(): unknown {
    return this.controller.signal.reason
  }

  get signal(): AbortSignal {
    return this.controller.signal
  }

  get deadline(): boolean {
    return this.runtimeDeadline
  }

  get fencedAtMs(): number | undefined {
    return this.runtimeFencedAtMs
  }

  throwIfCancelled(): void {
    if (this.cancelled) throw this.reason
  }

  cancel(reason: unknown, deadline = false, fencedAtMs = performance.now()): boolean {
    if (this.cancelled) return false
    this.runtimeDeadline = deadline
    this.runtimeFencedAtMs = fencedAtMs
    this.controller.abort(reason)
    return true
  }

  close(): void {
    if (this.parent !== undefined && this.parentListener !== undefined) {
      this.parent.signal.removeEventListener('abort', this.parentListener)
    }
  }
}

type CallbackGateWaiter = {
  readonly cancellation: RuntimeCancellation
  readonly resolve: () => void
  readonly reject: (reason: unknown) => void
  readonly abort: () => void
  readonly scopeId: number | undefined
  settled: boolean
}

class CallbackGate {
  private active = 0
  private readonly high: CallbackGateWaiter[] = []
  private readonly lowByScope = new Map<number, CallbackGateWaiter[]>()
  private readonly lowScopes: number[] = []
  private readonly lowMembers = new Set<number>()

  constructor(
    private readonly limit: number,
    private readonly runCancellation: RuntimeCancellation,
  ) {}

  acquire(readyCallback: boolean, cancellation: RuntimeCancellation, scopeId?: number): Promise<void> {
    this.discardSettled()
    if (!readyCallback && scopeId === undefined) throw new Error('new callback waiter has no scope')
    if (this.active < this.limit && this.high.length === 0 && (readyCallback || this.lowScopes.length === 0)) {
      this.active += 1
      return Promise.resolve()
    }
    return new Promise<void>((resolve, reject) => {
      let waiter!: CallbackGateWaiter
      const abort = (): void => {
        if (waiter.settled) return
        waiter.settled = true
        reject(cancellation.reason)
      }
      waiter = { cancellation, resolve, reject, abort, scopeId, settled: false }
      if (readyCallback) this.high.push(waiter)
      else {
        const resolvedScopeId = scopeId!
        const queue = this.lowByScope.get(resolvedScopeId) ?? []
        queue.push(waiter)
        this.lowByScope.set(resolvedScopeId, queue)
        if (!this.lowMembers.has(resolvedScopeId)) {
          this.lowMembers.add(resolvedScopeId)
          this.lowScopes.push(resolvedScopeId)
        }
      }
      cancellation.signal.addEventListener('abort', abort, { once: true })
      if (this.runCancellation !== cancellation) {
        this.runCancellation.signal.addEventListener('abort', abort, { once: true })
      }
      if (cancellation.cancelled || this.runCancellation.cancelled) abort()
    })
  }

  release(): void {
    if (this.active <= 0) throw new Error('callback permit released without ownership')
    this.active -= 1
    this.admitWaiters()
  }

  private admitWaiters(): void {
    this.discardSettled()
    while (this.active < this.limit) {
      let waiter: CallbackGateWaiter | undefined
      if (this.high.length > 0) waiter = this.high.shift()
      else {
        const scopeId = this.lowScopes.shift()
        if (scopeId !== undefined) {
          this.lowMembers.delete(scopeId)
          const queue = this.lowByScope.get(scopeId)!
          waiter = queue.shift()
          if (queue.length > 0) {
            this.lowMembers.add(scopeId)
            this.lowScopes.push(scopeId)
          } else this.lowByScope.delete(scopeId)
        }
      }
      if (waiter === undefined) return
      if (waiter.settled) continue
      waiter.settled = true
      waiter.cancellation.signal.removeEventListener('abort', waiter.abort)
      this.runCancellation.signal.removeEventListener('abort', waiter.abort)
      this.active += 1
      waiter.resolve()
    }
  }

  private discardSettled(): void {
    while (this.high[0]?.settled) this.high.shift()
    for (const scopeId of [...this.lowScopes]) {
      const queue = this.lowByScope.get(scopeId)!
      while (queue[0]?.settled) queue.shift()
      if (queue.length > 0) continue
      this.lowByScope.delete(scopeId)
      this.lowMembers.delete(scopeId)
    }
    if (this.lowMembers.size !== this.lowScopes.length) {
      const live = this.lowScopes.filter((scopeId) => this.lowMembers.has(scopeId))
      this.lowScopes.length = 0
      this.lowScopes.push(...live)
    }
  }
}

export class CallbackController {
  active = 0
  peak = 0
  private readonly gate: CallbackGate

  constructor(limit: number, cancellation: RuntimeCancellation) {
    this.gate = new CallbackGate(limit, cancellation)
  }

  async acquire(readyCallback: boolean, cancellation: RuntimeCancellation, scopeId?: number): Promise<void> {
    await this.gate.acquire(readyCallback, cancellation, scopeId)
    this.active += 1
    this.peak = Math.max(this.peak, this.active)
  }

  release(): void {
    if (this.active <= 0) throw new Error('callback accounting lost its owner')
    this.active -= 1
    this.gate.release()
  }
}

export class RunCancellation {
  constructor(
    private readonly source: RuntimeCancellation,
    private readonly deadline: RuntimeDeadline | undefined,
    private readonly failureFence: () => ProducedFailure | undefined,
    private readonly publishCancellation: () => void,
  ) {}

  commitDeadlineIfDue(): void {
    if (!this.source.cancelled && this.deadline?.due()) this.source.cancel('deadline_exceeded', true)
  }

  check(suppressed: readonly Failure[] = Object.freeze([])): void {
    const fence = this.failureFence()
    if (fence !== undefined) throw fence
    this.commitDeadlineIfDue()
    if (!this.source.cancelled) return
    this.publishCancellation()
    throw new RunCancelled(Object.freeze(suppressed.slice()))
  }

  checkScope(scope: RuntimeCancellation, suppressed: readonly Failure[] = Object.freeze([])): void {
    this.check(suppressed)
    if (!scope.cancelled) return
    const reason = scope.reason
    if (isFailureFence(reason)) throw reason.produced
    throw new RunCancelled(suppressed)
  }
}

export async function waitRetryDelay(delayMs: number, cancellation: RuntimeCancellation): Promise<boolean> {
  let remaining = delayMs
  if (remaining === 0) return await waitTimerChunk(0, cancellation)
  while (remaining > 0) {
    const chunk = Math.min(remaining, MAX_HOST_TIMER_DELAY_MS)
    if (!(await waitTimerChunk(chunk, cancellation))) return false
    remaining -= chunk
  }
  return true
}

export async function waitRuntimeDeadline(deadline: RuntimeDeadline, signal: AbortSignal): Promise<boolean> {
  while (!signal.aborted) {
    const remaining = deadline.remainingMs()
    if (remaining === 0) return true
    if (!(await waitSignalTimerChunk(Math.min(remaining, MAX_HOST_TIMER_DELAY_MS), signal))) return false
  }
  return false
}

function isCooperativeCancellation(error: unknown, cancellation: RuntimeCancellation): boolean {
  if (!cancellation.cancelled) return false
  if (error === cancellation.reason) return true
  try {
    return typeof DOMException !== 'undefined' && error instanceof DOMException && error.name === 'AbortError'
  } catch {
    return false
  }
}

function waitTimerChunk(delayMs: number, cancellation: RuntimeCancellation): Promise<boolean> {
  return waitSignalTimerChunk(delayMs, cancellation.signal)
}

function waitSignalTimerChunk(delayMs: number, signal: AbortSignal): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    if (signal.aborted) {
      resolve(false)
      return
    }
    let settled = false
    const finish = (elapsed: boolean): void => {
      if (settled) return
      settled = true
      signal.removeEventListener('abort', onAbort)
      resolve(elapsed)
    }
    const timer = setTimeout(() => finish(true), delayMs)
    const onAbort = (): void => {
      clearTimeout(timer)
      finish(false)
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

export function disposeNativePromise(value: object): void {
  try {
    Reflect.apply(intrinsicPromiseThen, value, [(): undefined => undefined, (): undefined => undefined])
  } catch {
    // Arbitrary thenables and hostile Promise species are outside best-effort cleanup.
  }
}

type LifecycleContext = {
  readonly scopeId: number
  readonly activationId: number
  readonly attempt: number | null
  close(): unknown
  abandon(): void
}

export class CallbackExecutor {
  constructor(
    private readonly cancellation: RuntimeCancellation,
    private readonly runDeadline: RuntimeDeadline | undefined,
    private readonly cancelGraceMs: number,
    private readonly cancellationPolicy: RunCancellation,
    private readonly failureFence: () => ProducedFailure | undefined,
    private readonly publishAttemptTimeout: (context: LifecycleContext, failure: Failure) => void,
  ) {}

  remainingMs(callbackSource: RuntimeCancellation, attemptDeadline: RuntimeDeadline | undefined): number | undefined {
    const nowMs = performance.now()
    const remaining: number[] = []
    if (!this.cancellation.cancelled && this.runDeadline !== undefined) {
      remaining.push(this.runDeadline.remainingMs(nowMs))
    }
    if (!callbackSource.cancelled && attemptDeadline !== undefined) {
      remaining.push(attemptDeadline.remainingMs(nowMs))
    }
    for (const source of [callbackSource, this.cancellation]) {
      if (source.cancelled && source.fencedAtMs !== undefined) {
        remaining.push(new RuntimeDeadline(source.fencedAtMs, this.cancelGraceMs).remainingMs(nowMs))
      }
    }
    return remaining.length === 0 ? undefined : Math.min(...remaining)
  }

  private async captureCallback(callback: () => unknown): Promise<CallbackCompletion> {
    let result: unknown
    let error: unknown
    let failed = false
    try {
      result = await callback()
    } catch (caught) {
      error = caught
      failed = true
    }
    const completion = Object.create(null) as {
      result: unknown
      error: unknown
      failed: boolean
      settledMs: number
    }
    completion.result = result
    completion.error = error
    completion.failed = failed
    completion.settledMs = performance.now()
    return Object.freeze(completion)
  }

  async awaitLifecycleCallback(
    context: LifecycleContext,
    callbackSource: RuntimeCancellation,
    callback: () => unknown,
    classify: (error: unknown, selected: Failure | null) => Failure,
    options: {
      readonly active?: readonly Failure[]
      readonly attemptDeadline?: RuntimeDeadline
      readonly timeoutFailure?: () => Failure
    } = {},
  ): Promise<unknown> {
    const active = options.active ?? Object.freeze([])
    const failureFence = (): ProducedFailure | undefined => {
      const reason = callbackSource.reason
      return isFailureFence(reason) ? reason.produced : undefined
    }
    const fencedProduced = (fence: ProducedFailure, completion: CallbackCompletion): ProducedFailure => {
      const suppressed = [...fence.suppressed]
      if (completion.failed && !isCooperativeCancellation(completion.error, callbackSource)) {
        suppressed.push(classify(completion.error, fence.failure))
      }
      return new ProducedFailure(fence.failure, suppressed)
    }
    this.cancellationPolicy.check(active)
    if (options.attemptDeadline?.due()) {
      if (options.timeoutFailure === undefined) throw new Error('attempt timeout has no Failure factory')
      const failure = options.timeoutFailure()
      callbackSource.cancel('attempt_timeout')
      this.publishAttemptTimeout(context, failure)
      callbackSource.close()
      context.close()
      throw new ProducedFailure(failure)
    }

    let completion: CallbackCompletion | undefined
    const callbackPromise = this.captureCallback(callback).then((settled) => {
      completion = settled
      return settled
    })
    let sourceListener: (() => void) | undefined
    const sourceWake = new Promise<void>((resolve) => {
      if (callbackSource.cancelled) resolve()
      else {
        sourceListener = resolve
        callbackSource.signal.addEventListener('abort', sourceListener, { once: true })
      }
    })
    const attemptStop = new AbortController()
    const stopAttempt = (): void => attemptStop.abort()
    callbackSource.signal.addEventListener('abort', stopAttempt, { once: true })
    const attemptWake =
      options.attemptDeadline === undefined
        ? undefined
        : waitRuntimeDeadline(options.attemptDeadline, attemptStop.signal).then((elapsed) => {
            if (elapsed && completion === undefined) callbackSource.cancel('attempt_timeout')
          })
    try {
      await Promise.race(attemptWake === undefined ? [callbackPromise, sourceWake] : [callbackPromise, sourceWake, attemptWake])

      if (completion !== undefined) {
        const attemptWon =
          options.attemptDeadline !== undefined &&
          completion.settledMs - options.attemptDeadline.originMs >= options.attemptDeadline.durationMs &&
          !this.cancellation.cancelled
        if (attemptWon) callbackSource.cancel('attempt_timeout')
        else if (!this.cancellation.cancelled) {
          const fence = failureFence()
          if (fence !== undefined) throw fencedProduced(fence, completion)
          if (completion.failed) {
            throw new ProducedFailure(classify(completion.error, null), active.length > 0 ? active.slice(1) : [])
          }
          return completion.result
        }
      }

      const localTimeout = callbackSource.cancelled && callbackSource.reason === 'attempt_timeout'
      const timeoutPrimary = localTimeout && options.timeoutFailure !== undefined ? options.timeoutFailure() : undefined
      if (timeoutPrimary !== undefined) this.publishAttemptTimeout(context, timeoutPrimary)

      while (completion === undefined) {
        const graceDeadlines: RuntimeDeadline[] = []
        if (callbackSource.cancelled && callbackSource.fencedAtMs !== undefined) {
          graceDeadlines.push(new RuntimeDeadline(callbackSource.fencedAtMs, this.cancelGraceMs))
        }
        if (this.cancellation.cancelled && this.cancellation.fencedAtMs !== undefined) {
          graceDeadlines.push(new RuntimeDeadline(this.cancellation.fencedAtMs, this.cancelGraceMs))
        }
        if (graceDeadlines.length === 0) throw new Error('signalled callback has no grace deadline')
        let earliest = graceDeadlines[0]!
        for (const candidate of graceDeadlines.slice(1)) {
          if (candidate.remainingMs() < earliest.remainingMs()) earliest = candidate
        }
        const graceCancellation = new AbortController()
        const graceWake = waitRuntimeDeadline(earliest, graceCancellation.signal)
        const runWake = this.cancellation.cancelled
          ? undefined
          : new Promise<void>((resolve) => {
              this.cancellation.signal.addEventListener('abort', () => resolve(), { once: true })
            })
        await Promise.race(runWake === undefined ? [callbackPromise, graceWake] : [callbackPromise, graceWake, runWake])
        graceCancellation.abort()
        if (completion !== undefined) break
        if (earliest.due()) {
          context.abandon()
          void callbackPromise.then(
            () => undefined,
            () => undefined,
          )
          const runFence = this.failureFence()
          if (runFence !== undefined) throw new RunAbandoned(runFence.failure, runFence.suppressed)
          if (this.cancellation.cancelled) {
            const cancellation = Object.freeze({
              reason: this.cancellation.reason,
              deadline: this.cancellation.deadline,
            })
            const suppressed = timeoutPrimary === undefined ? active : [timeoutPrimary, ...active.slice(1)]
            throw new RunAbandoned(cancellation, suppressed)
          }
          const fence = failureFence()
          if (fence !== undefined) throw new RunAbandoned(fence.failure, fence.suppressed)
          if (timeoutPrimary === undefined) throw new Error('local grace expired without timeout')
          throw new RunAbandoned(timeoutPrimary, active.slice(1))
        }
      }

      if (completion === undefined) throw new Error('callback wakeup lost its settlement')
      const protectedSources = [callbackSource, this.cancellation].filter(
        (source) => source.cancelled && source.fencedAtMs !== undefined,
      )
      const graceExpired = protectedSources.some((source) => completion!.settledMs - source.fencedAtMs! >= this.cancelGraceMs)
      if (graceExpired) {
        context.abandon()
        const runFence = this.failureFence()
        if (runFence !== undefined) throw new RunAbandoned(runFence.failure, runFence.suppressed)
        if (this.cancellation.cancelled) {
          const cancellation = Object.freeze({
            reason: this.cancellation.reason,
            deadline: this.cancellation.deadline,
          })
          const suppressed = timeoutPrimary === undefined ? active : [timeoutPrimary, ...active.slice(1)]
          throw new RunAbandoned(cancellation, suppressed)
        }
        const fence = failureFence()
        if (fence !== undefined) throw new RunAbandoned(fence.failure, fence.suppressed)
        if (timeoutPrimary === undefined) throw new Error('expired grace has no controlling timeout')
        throw new RunAbandoned(timeoutPrimary, active.slice(1))
      }
      const runFence = this.failureFence()
      if (runFence !== undefined) throw fencedProduced(runFence, completion)
      if (this.cancellation.cancelled) {
        const suppressed = [...(timeoutPrimary === undefined ? active : [timeoutPrimary, ...active.slice(1)])]
        if (completion.failed && !isCooperativeCancellation(completion.error, callbackSource)) {
          suppressed.push(classify(completion.error, timeoutPrimary ?? active[0] ?? null))
        }
        throw new RunCancelled(suppressed)
      }
      const fence = failureFence()
      if (fence !== undefined) throw fencedProduced(fence, completion)
      if (timeoutPrimary === undefined) throw new Error('attempt signal has no timeout Failure')
      const suppressed = [...active.slice(1)]
      if (completion.failed && !isCooperativeCancellation(completion.error, callbackSource)) {
        suppressed.push(classify(completion.error, timeoutPrimary))
      }
      throw new ProducedFailure(timeoutPrimary, suppressed)
    } finally {
      attemptStop.abort()
      if (sourceListener !== undefined) callbackSource.signal.removeEventListener('abort', sourceListener)
      callbackSource.signal.removeEventListener('abort', stopAttempt)
      callbackSource.close()
    }
  }
}
