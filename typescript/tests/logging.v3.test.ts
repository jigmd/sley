import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Flow, node } from '../caskada'
import { createLoggingObserver } from '../caskada-logging'

import type { Context } from '../caskada'
import type { CaskadaLogFields, CaskadaLogger, CaskadaLogLevel } from '../caskada-logging'

type State = { [key: string]: unknown }

class CaptureLogger implements CaskadaLogger {
  readonly records: Array<{ readonly level: CaskadaLogLevel; readonly message: string; readonly fields: CaskadaLogFields }> = []

  debug(message: string, fields: CaskadaLogFields): void {
    this.records.push({ level: 'debug', message, fields })
  }

  info(message: string, fields: CaskadaLogFields): void {
    this.records.push({ level: 'info', message, fields })
  }

  warn(message: string, fields: CaskadaLogFields): void {
    this.records.push({ level: 'warn', message, fields })
  }

  error(message: string, fields: CaskadaLogFields): void {
    this.records.push({ level: 'error', message, fields })
  }
}

describe('v3 logging adapter', () => {
  it('forwards exact events without buffering or formatting application data', async () => {
    const logger = new CaptureLogger()
    let attempts = 0
    const unformattable = {
      toString(): never {
        throw new Error('application data must not be formatted')
      },
    }
    const handler = node<State>(
      (context: Context<State>) => {
        attempts += 1
        context.report('payload', unformattable)
        if (attempts === 1) throw new Error('retry')
      },
      { retry: { maxAttempts: 2 } },
    )
    const result = await new Flow(handler).start({}, { observer: createLoggingObserver(logger) }).result

    assert.equal(result.status, 'completed')
    assert.deepEqual(
      logger.records.map((record) => record.fields.caskadaSequence),
      Array.from({ length: logger.records.length }, (_unused, index) => index + 1),
    )
    assert.equal(logger.records.find((record) => record.fields.caskadaEventKind === 'failure_recorded')!.level, 'error')
    assert.equal(logger.records.find((record) => record.fields.caskadaEventKind === 'retry_scheduled')!.level, 'info')
    assert.equal(logger.records.find((record) => record.fields.caskadaEventKind === 'report')!.level, 'info')
    assert.equal(logger.records.find((record) => record.fields.caskadaEventKind === 'callback_started')!.level, 'debug')
    for (const record of logger.records) {
      assert.equal(record.fields.caskadaEvent.sequence, record.fields.caskadaSequence)
      assert.equal(record.message, `Caskada event: ${record.fields.caskadaEventKind}`)
    }
  })

  it('turns logger failure into one observer diagnostic', async () => {
    const cause = new Error('sink failed')
    const logger: CaskadaLogger = {
      debug(): never {
        throw cause
      },
      info(): never {
        throw cause
      },
      warn(): never {
        throw cause
      },
      error(): never {
        throw cause
      },
    }
    const result = await new Flow(node<State>(() => {})).start({}, { observer: createLoggingObserver(logger) }).result

    assert.equal(result.status, 'completed')
    assert.equal(result.diagnostics.length, 1)
    assert.equal(result.diagnostics[0]!.message, 'Observer raised')
    assert.equal(result.diagnostics[0]!.eventSequence, 1)
    assert.equal(result.diagnostics[0]!.cause, cause)
  })

  it('logs a cancellation fence as a warning', async () => {
    const logger = new CaptureLogger()
    let entered!: () => void
    const enteredPromise = new Promise<void>((resolve) => {
      entered = resolve
    })
    const handler = node<State>(async (context) => {
      entered()
      await new Promise<void>((resolve) => context.cancellation.signal.addEventListener('abort', () => resolve(), { once: true }))
    })
    const handle = new Flow(handler).start({}, { observer: createLoggingObserver(logger) })
    await enteredPromise
    handle.cancel('test')
    await handle.result

    assert.equal(logger.records.find((record) => record.fields.caskadaEventKind === 'cancellation_fenced')!.level, 'warn')
  })
})
