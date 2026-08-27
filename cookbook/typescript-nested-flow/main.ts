import { setTimeout as delay } from 'node:timers/promises'
import { Flow, node } from '@jigging/sley'

interface Job {
  name: string
  delayMs: number
}

interface PipelineState {
  jobs: readonly Job[]
  results?: readonly string[]
}

const load = node<PipelineState, Job>(async (context) => {
  await delay(context.input.delayMs)
  console.log(`Loaded ${context.input.name}`)
})

const transform = node<PipelineState, Job>((context) => {
  console.log(`Transformed ${context.input.name}`)
})

const save = node<PipelineState, Job>((context) => {
  context.end(`${context.input.name}.ready`)
})

load.link(transform)
transform.link(save)
const worker = new Flow(load, { name: 'job worker' })

const dispatch = node<PipelineState>((context) => {
  for (const job of context.state.jobs) context.emit('job', job)
})

dispatch.link(worker, 'job')
const pipeline = new Flow(dispatch, {
  concurrency: 2,
  combine(context, result) {
    context.state.results = [...(result.outputs as string[])].sort()
    context.emit()
  },
})

const report = node<PipelineState>((context) => {
  console.log(`Results: ${context.state.results?.join(', ')}`)
})

pipeline.link(report)

await new Flow(pipeline).run({
  jobs: [
    { name: 'alpha', delayMs: 30 },
    { name: 'beta', delayMs: 10 },
    { name: 'gamma', delayMs: 20 },
  ],
})
