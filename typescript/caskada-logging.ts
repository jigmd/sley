import type { Observer, RunEvent } from './caskada'

export type CaskadaLogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface CaskadaLogFields {
  readonly caskadaEvent: RunEvent
  readonly caskadaEventKind: RunEvent['kind']
  readonly caskadaRunId: string
  readonly caskadaSequence: number
}

export interface CaskadaLogger {
  debug(message: string, fields: CaskadaLogFields): unknown
  info(message: string, fields: CaskadaLogFields): unknown
  warn(message: string, fields: CaskadaLogFields): unknown
  error(message: string, fields: CaskadaLogFields): unknown
}

const EVENT_LEVELS: Readonly<Partial<Record<RunEvent['kind'], CaskadaLogLevel>>> = Object.freeze({
  failure_recorded: 'error',
  failure_fenced: 'error',
  cancellation_fenced: 'warn',
  run_started: 'info',
  run_finished: 'info',
  retry_scheduled: 'info',
  report: 'info',
})

export function createLoggingObserver(logger: CaskadaLogger): Observer {
  return (event): undefined => {
    const level = EVENT_LEVELS[event.kind] ?? 'debug'
    const fields: CaskadaLogFields = Object.freeze({
      caskadaEvent: event,
      caskadaEventKind: event.kind,
      caskadaRunId: event.runId,
      caskadaSequence: event.sequence,
    })
    logger[level](`Caskada event: ${event.kind}`, fields)
    return undefined
  }
}
