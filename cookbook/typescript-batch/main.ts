import { setTimeout as delay } from 'node:timers/promises'
import { Flow, node } from 'caskada'

import type { BatchState, CheckResult, Service } from './types'

const dispatch = node<BatchState>((context) => {
  for (const service of context.state.services) {
    // Each emission starts one check with its own branch input.
    context.emit('check', service)
  }
})

const check = node<BatchState, Service>(async (context) => {
  await delay(context.input.delayMs)
  console.log(`Checked ${context.input.name}`)

  // end(value) publishes this branch's result to the Flow combiner.
  context.end({ name: context.input.name, healthy: context.input.healthy })
})

dispatch.link(check, 'check')

const checks = new Flow(dispatch, {
  concurrency: 3,
  combine(context, result) {
    const results = result.outputs as readonly CheckResult[]
    context.state.summary = {
      healthy: results.filter((item) => item.healthy).map((item) => item.name),
      unhealthy: results.filter((item) => !item.healthy).map((item) => item.name),
    }

    // Replace the worker terminals with one continuation to report.
    context.emit()
  },
})

const report = node<BatchState>((context) => {
  const summary = context.state.summary
  if (summary === undefined) throw new Error('summary is missing')

  console.log(`Healthy: ${summary.healthy.join(', ')}`)
  console.log(`Unhealthy: ${summary.unhealthy.join(', ')}`)
})

checks.link(report)

await new Flow(checks).run({
  services: [
    { name: 'Search', healthy: true, delayMs: 30 },
    { name: 'Database', healthy: true, delayMs: 10 },
    { name: 'Queue', healthy: false, delayMs: 20 },
  ],
})
