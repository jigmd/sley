import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'

import type { Context, RunEvent, RunHandle, ScopeFailure, ScopeResult } from '../caskada'

type State = { [key: string]: unknown }

describe('v3 reports', () => {
  it('preserves omission and explicit undefined', async () => {
    const events: RunEvent[] = []
    const handler = node<State>((context) => {
      context.report('started')
      context.report('value', undefined)
    })
    const result = await new Flow(handler).start(
      {},
      {
        observer(event): undefined {
          events.push(event)
          return undefined
        },
      },
    ).result
    const reports = events.filter((event) => event.kind === 'report')

    assert.equal(result.status, 'completed')
    assert.equal(result.stats.reports, 2)
    assert.deepEqual(
      reports.map((event) => event.payload.name),
      ['started', 'value'],
    )
    assert.equal(reports[0]!.payload.hasData, false)
    assert.equal(reports[0]!.payload.data, undefined)
    assert.equal(reports[1]!.payload.hasData, true)
    assert.equal(reports[1]!.payload.data, undefined)
  })

  it('counts reports without an observer', async () => {
    const result = await new Flow(node<State>((context) => context.report('progress', { step: 1 }))).start({}).result

    assert.equal(result.status, 'completed')
    assert.equal(result.stats.reports, 1)
  })

  it('does not charge invalid names and normalizes an uncaught name', async () => {
    const events: RunEvent[] = []
    const caught = node<State>((context) => {
      assert.throws(() => context.report(''))
      context.report('valid')
    })
    const caughtResult = await new Flow(caught).start(
      {},
      {
        maxReports: 1,
        observer(event): undefined {
          events.push(event)
          return undefined
        },
      },
    ).result

    assert.equal(caughtResult.status, 'completed')
    assert.equal(caughtResult.stats.reports, 1)
    assert.equal(events.filter((event) => event.kind === 'report').length, 1)

    const failed = await new Flow(node<State>((context) => context.report(1 as never))).start({}).result
    assert.equal(failed.status, 'failed')
    if (failed.status !== 'failed') throw new Error('invalid report name must fail')
    assert.equal(failed.failure.kind, 'invalid_outcome')
    assert.deepEqual(failed.failure.detail, { type: 'invalid_outcome', reason: 'report_name' })
    assert.equal(failed.stats.reports, 0)
  })

  it('commits one unrecoverable limit on report overflow', async () => {
    const events: RunEvent[] = []
    let caught = 0
    const handler = node<State>((context) => {
      context.report('first')
      for (const name of ['overflow', 'already_fenced']) {
        try {
          context.report(name)
        } catch {
          caught += 1
        }
      }
    })
    const result = await new Flow(handler).start(
      {},
      {
        maxReports: 1,
        observer(event): undefined {
          events.push(event)
          return undefined
        },
      },
    ).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('report overflow must fail')
    assert.equal(result.failure.kind, 'limit')
    assert.deepEqual(result.failure.detail, { type: 'limit', limit: 'max_reports' })
    assert.equal(result.failure.attempt, 1)
    assert.equal(result.stats.reports, 1)
    assert.equal(caught, 2)
    assert.equal(events.filter((event) => event.kind === 'report').length, 1)
    assert.equal(events.filter((event) => event.kind === 'failure_fenced').length, 1)
  })

  it('disables an observer that reports reentrantly', async () => {
    const events: RunEvent[] = []
    let active: Context<State> | undefined
    const result = await new Flow(
      node<State>((context) => {
        active = context
        context.report('outer')
      }),
    ).start(
      {},
      {
        observer(event): undefined {
          events.push(event)
          if (event.kind === 'report') active!.report('nested')
          return undefined
        },
      },
    ).result
    const reports = events.filter((event) => event.kind === 'report')

    assert.equal(result.status, 'completed')
    assert.equal(result.stats.reports, 1)
    assert.equal(reports.length, 1)
    assert.equal(result.diagnostics.length, 1)
    assert.equal(result.diagnostics[0]!.message, 'Observer reentrancy disabled')
    assert.equal(result.diagnostics[0]!.eventSequence, reports[0]!.sequence)
  })

  it('prevents callback resumption after a report observer cancels', async () => {
    const events: RunEvent[] = []
    let resumed = false
    let handle!: RunHandle<State>
    const handler = node<State>((context) => {
      context.report('checkpoint')
      resumed = true
    })
    handle = new Flow(handler).start(
      {},
      {
        observer(event): undefined {
          events.push(event)
          if (event.kind === 'report') handle.cancel('observer')
          return undefined
        },
      },
    )
    const result = await handle.result

    assert.equal(result.status, 'cancelled')
    assert.equal(resumed, false)
    const reportIndex = events.findIndex((event) => event.kind === 'report')
    assert.equal(events[reportIndex + 1]!.kind, 'cancellation_fenced')
  })

  it('counts report observer time against an attempt timeout', async () => {
    let resumed = false
    const handler = node<State>(
      (context) => {
        context.report('slow')
        resumed = true
      },
      { timeoutMs: 1 },
    )
    const result = await new Flow(handler).start(
      {},
      {
        cancelGraceMs: 100,
        observer(event): undefined {
          if (event.kind === 'report') {
            const until = performance.now() + 20
            while (performance.now() < until) {
              // Deliberately block the synchronous observer.
            }
          }
          return undefined
        },
      },
    ).result

    assert.equal(result.status, 'failed')
    if (result.status !== 'failed') throw new Error('observer time must count against the attempt timeout')
    assert.equal(result.failure.kind, 'handler_timeout')
    assert.equal(result.stats.reports, 1)
    assert.equal(resumed, false)
  })

  it('publishes a run deadline crossed inside a report observer', async () => {
    const events: RunEvent[] = []
    let resumed = false
    const handler = node<State>((context) => {
      context.report('slow')
      resumed = true
    })
    const result = await new Flow(handler).start(
      {},
      {
        deadlineMs: 30,
        cancelGraceMs: 100,
        observer(event): undefined {
          events.push(event)
          if (event.kind === 'report') {
            const until = performance.now() + 100
            while (performance.now() < until) {
              // Deliberately block the synchronous observer.
            }
          }
          return undefined
        },
      },
    ).result

    assert.equal(result.status, 'cancelled')
    assert.equal(resumed, false)
    const reportIndex = events.findIndex((event) => event.kind === 'report')
    const fence = events[reportIndex + 1]!
    assert.equal(fence.kind, 'cancellation_fenced')
    if (fence.kind === 'cancellation_fenced') assert.equal(fence.payload.deadline, true)
  })

  it('is available in recovery and combine callbacks', async () => {
    const names: string[] = []
    const observer = (event: RunEvent): undefined => {
      if (event.kind === 'report') names.push(event.payload.name)
      return undefined
    }
    const fail = (): never => {
      throw new Error('failed')
    }

    const nodeResult = await new Flow(
      node<State>(fail, {
        recover(context) {
          context.report('node_recover')
          context.end('node')
        },
      }),
    ).start({}, { observer }).result

    const flowResult = await new Flow(node<State>(fail), {
      recover(context: Context<State>, _failure: ScopeFailure) {
        context.report('flow_recover')
        context.end('flow')
      },
    }).start({}, { observer }).result

    const combineResult = await new Flow(
      node<State>((context) => context.end()),
      {
        combine(context: Context<State>, _result: ScopeResult) {
          context.report('flow_combine')
        },
      },
    ).start({}, { observer }).result

    assert.equal(nodeResult.status, 'completed')
    assert.equal(flowResult.status, 'completed')
    assert.equal(combineResult.status, 'completed')
    assert.deepEqual(names, ['node_recover', 'flow_recover', 'flow_combine'])
  })

  it('closes the report capability with its context', async () => {
    let retained!: Context<State>
    const result = await new Flow(
      node<State>((context) => {
        retained = context
      }),
    ).start({}).result

    assert.equal(result.status, 'completed')
    assert.throws(() => retained.report('late'))
  })
})
