import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node, RUN_EVENT_SCHEMA_VERSION } from '../caskada'

import type { Context, Observer, RunEvent, RunHandle, ScopeResult } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 run events', () => {
  it('publishes the exact successful opening and terminal order', async () => {
    const events: RunEvent[] = []
    const first = node<State>((context) => context.emit('next', 7))
    const second = node<State>((context) => context.end(context.input))
    first.link(second, 'next')

    const result = await new Flow(first).start(
      {},
      {
        observer: (event): undefined => {
          events.push(event)
          return undefined
        },
        runId: 'events',
      },
    ).result

    assert.equal(RUN_EVENT_SCHEMA_VERSION, 1)
    assert.equal(result.status, 'completed')
    assert.deepEqual(
      events.map((event) => event.sequence),
      Array.from({ length: 11 }, (_unused, index) => index + 1),
    )
    assert.deepEqual(new Set(events.map((event) => event.runId)), new Set(['events']))
    assert.deepEqual(
      events.map((event) => event.kind),
      [
        'run_started',
        'scope_started',
        'callback_started',
        'callback_finished',
        'transition_committed',
        'callback_started',
        'callback_finished',
        'transition_committed',
        'terminal_committed',
        'scope_finished',
        'run_finished',
      ],
    )
    const route = events[4]!
    assert.equal(route.kind, 'transition_committed')
    if (route.kind !== 'transition_committed') return
    assert.equal(route.payload.transition.kind, 'route')
    assert.equal(route.payload.transition.destination.type, 'activation')
    const end = events[7]!
    assert.equal(end.kind, 'transition_committed')
    if (end.kind !== 'transition_committed') return
    assert.equal(end.payload.transition.kind, 'end')
    const terminal = events[8]!
    assert.equal(terminal.kind, 'terminal_committed')
    if (terminal.kind !== 'terminal_committed') return
    assert.equal(terminal.payload.terminalSequence, end.payload.transition.destination.sequence)
  })

  it('drains a fanout bundle before observer cancellation is published', async () => {
    const events: RunEvent[] = []
    const fanout = node<State>((context) => {
      context.end(1)
      context.end(2)
    })
    let handle!: RunHandle<State>
    const observer: Observer = (event): undefined => {
      events.push(event)
      if (event.kind === 'transition_committed' && event.payload.branchIndex === 0) handle.cancel('observer')
      return undefined
    }

    handle = new Flow(fanout).start({}, { observer })
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    const kinds = events.map((event) => event.kind)
    const firstTransition = kinds.indexOf('transition_committed')
    const cancellation = kinds.indexOf('cancellation_fenced')
    assert.deepEqual(kinds.slice(firstTransition, cancellation), [
      'transition_committed',
      'terminal_committed',
      'transition_committed',
      'terminal_committed',
    ])
    const finished = events[firstTransition - 1]!
    assert.equal(finished.kind, 'callback_finished')
    if (finished.kind !== 'callback_finished') return
    assert.deepEqual(finished.payload.disposition, { kind: 'outcome', outcome: 'fanout' })
  })

  it('closes a combined child with its pre-combine terminal ids', async () => {
    const events: RunEvent[] = []
    const worker = node<State>((context) => context.end(1))
    const child = new Flow(worker, {
      combine(context: Context<State>, result: ScopeResult): void {
        context.emit({ input: [...result.outputs] })
      },
    })
    const finish = node<State>((context) => context.end(context.input))
    child.link(finish)

    const result = await new Flow(child).start(
      {},
      {
        observer: (event): undefined => {
          events.push(event)
          return undefined
        },
      },
    ).result

    assert.equal(result.status, 'completed')
    const childFinished = events.find((event) => event.kind === 'scope_finished' && event.payload.scopeId === 2)
    assert.ok(childFinished !== undefined && childFinished.kind === 'scope_finished')
    assert.deepEqual(childFinished.payload.terminalSequences, [1])
    const index = events.indexOf(childFinished)
    const boundary = events[index - 1]!
    assert.equal(boundary.kind, 'transition_committed')
    if (boundary.kind !== 'transition_committed') return
    assert.equal(boundary.payload.scopeId, 1)
    assert.equal(boundary.payload.transition.kind, 'forward_exit')
  })

  it('records one failure before its callback and retry references', async () => {
    const events: RunEvent[] = []
    let attempts = 0
    const retried = node<State>(
      () => {
        attempts += 1
        if (attempts === 1) throw new Error('retry')
      },
      { retry: { maxAttempts: 2 } },
    )

    const result = await new Flow(retried).start(
      {},
      {
        observer: (event): undefined => {
          events.push(event)
          return undefined
        },
      },
    ).result

    assert.equal(result.status, 'completed')
    const kinds = events.map((event) => event.kind)
    assert.ok(kinds.indexOf('failure_recorded') < kinds.indexOf('callback_finished'))
    assert.ok(kinds.indexOf('callback_finished') < kinds.indexOf('retry_scheduled'))
    const failureEvent = events.find((event) => event.kind === 'failure_recorded')
    const retryEvent = events.find((event) => event.kind === 'retry_scheduled')
    assert.ok(failureEvent !== undefined && failureEvent.kind === 'failure_recorded')
    assert.ok(retryEvent !== undefined && retryEvent.kind === 'retry_scheduled')
    assert.equal(retryEvent.payload.failureId, failureEvent.payload.failure.failureId)
  })

  it('lets a callback-start observer skip application invocation', async () => {
    const events: RunEvent[] = []
    let calls = 0
    const handler = node<State>(() => {
      calls += 1
    })
    let handle!: RunHandle<State>
    const observer: Observer = (event): undefined => {
      events.push(event)
      if (event.kind === 'callback_started') handle.cancel('stop')
      return undefined
    }

    handle = new Flow(handler).start({}, { observer })
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.equal(calls, 0)
    assert.deepEqual(
      events.map((event) => event.kind),
      [
        'run_started',
        'scope_started',
        'callback_started',
        'cancellation_fenced',
        'callback_finished',
        'scope_finished',
        'run_finished',
      ],
    )
  })

  it('publishes cancel before return and ignores cancel after terminal commit', async () => {
    const events: RunEvent[] = []
    let entered!: () => void
    const enteredPromise = new Promise<void>((resolve) => {
      entered = resolve
    })
    const handler = node<State>(async (context) => {
      entered()
      await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
    })
    let handle!: RunHandle<State>
    const observer: Observer = (event): undefined => {
      events.push(event)
      if (event.kind === 'run_finished') handle.cancel('too_late')
      return undefined
    }

    handle = new Flow(handler).start({}, { observer })
    await enteredPromise
    handle.cancel('caller')
    assert.equal(events.at(-1)?.kind, 'cancellation_fenced')
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.equal(events.at(-1)?.kind, 'run_finished')
    assert.equal(events.filter((event) => event.kind === 'cancellation_fenced').length, 1)
  })

  it('disables a throwing observer and retains one diagnostic', async () => {
    const cause = { source: 'observer' }
    let calls = 0
    const result = await new Flow(node<State>(() => {})).start(
      {},
      {
        observer: (): undefined => {
          calls += 1
          throw cause
        },
      },
    ).result

    assert.equal(result.status, 'completed')
    assert.equal(calls, 1)
    assert.equal(result.diagnostics.length, 1)
    assert.equal(result.diagnostics[0]!.eventSequence, 1)
    assert.equal(result.diagnostics[0]!.message, 'Observer raised')
    assert.equal(result.diagnostics[0]!.cause, cause)
  })

  it('drains a native async observer result and disables it', async () => {
    let calls = 0
    let bodyRan = false
    const asyncObserver = async (): Promise<void> => {
      bodyRan = true
    }
    const observer = ((): Promise<void> => {
      calls += 1
      return asyncObserver()
    }) as unknown as Observer

    const result = await new Flow(node<State>(() => {})).start({}, { observer }).result
    await Promise.resolve()

    assert.equal(result.status, 'completed')
    assert.equal(calls, 1)
    assert.equal(bodyRan, true)
    assert.equal(result.diagnostics[0]!.message, 'Observer must return synchronously')
  })

  it('excludes terminal observer time from duration', async () => {
    const observer: Observer = (event): undefined => {
      if (event.kind === 'run_finished') {
        const until = performance.now() + 50
        while (performance.now() < until) {
          // Deliberately block the synchronous observer.
        }
      }
      return undefined
    }

    const started = performance.now()
    const result = await new Flow(node<State>(() => {})).start({}, { observer }).result
    const elapsedMs = performance.now() - started

    assert.equal(result.status, 'completed')
    assert.ok(elapsedMs >= 45)
    assert.ok(elapsedMs - result.stats.durationMs >= 35)
  })
})
