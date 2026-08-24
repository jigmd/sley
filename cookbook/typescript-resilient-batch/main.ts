import { Flow, node } from '@jigging/sley'

import type { Context, ScopeFailure } from '@jigging/sley'
import type { BatchState, ImportedRecord, SourceRecord } from './types'

const dispatch = node<BatchState>((context) => {
  for (const record of context.state.records) {
    context.emit('record', record)
  }
})

const importRecord = node<BatchState, SourceRecord>((context) => {
  const amount = Number(context.input.amount)
  if (!Number.isFinite(amount)) {
    throw new Error(`record ${context.input.id} has an invalid amount`)
  }

  console.log(`Imported record ${context.input.id}`)
  context.end({ id: context.input.id, amount })
})

function keepCompleted(context: Context<BatchState>, failure: ScopeFailure) {
  const imported = failure.terminals.filter((terminal) => terminal.hasOutput).map((terminal) => terminal.output as ImportedRecord)

  context.state.imported = imported
  context.state.error = failure.primary.message

  console.log(`Recovery kept ${imported.length} completed record`)
  console.log(`Failure: ${failure.primary.message}`)

  // Recovery replaces the partial terminals with one completed batch result.
  context.end({ imported: imported.length, error: failure.primary.message })
}

dispatch.link(importRecord, 'record')
const batch = new Flow(dispatch, {
  concurrency: 1,
  recover: keepCompleted,
})

const result = await batch
  .start({
    records: [
      { id: 1, amount: '12.50' },
      { id: 2, amount: 'invalid' },
      { id: 3, amount: '9.75' },
    ],
  })
  .result()

console.log(`Run status: ${result.status}`)
console.log(`Final terminals: ${result.terminals.length}`)
