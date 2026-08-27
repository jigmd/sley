import { Flow, node } from '@jigging/sley'

interface ComponentTask {
  id: string
  requiredPhrase: string
}

interface ComponentJob {
  task: ComponentTask
  attempt: number
  draft?: string
  feedback?: string
}

interface ComponentResult extends ComponentJob {
  draft: string
  status: 'passed' | 'capped'
}

interface QualityState {
  tasks?: readonly ComponentTask[]
  componentResults?: readonly ComponentResult[]
  integrationAttempt: number
  artifact?: string
  outcome?: 'parity' | 'stopped'
  stopReason?: string
}

const build = node<QualityState, ComponentJob>((context) => {
  const attempt = context.input.attempt + 1
  const phrase = context.input.feedback ?? 'a concrete result'
  const next: ComponentJob = {
    ...context.input,
    attempt,
    draft: `${context.input.task.id}: ${phrase}.`,
  }
  console.log(`Built ${context.input.task.id} attempt ${attempt}`)
  context.emit('evaluate', next)
})

const evaluate = node<QualityState, ComponentJob>((context) => {
  const draft = context.input.draft
  if (draft === undefined) throw new Error('component draft is missing')

  if (draft.includes(context.input.task.requiredPhrase)) {
    console.log(`Component reached parity: ${context.input.task.id}`)
    context.emit('passed', { ...context.input, draft, status: 'passed' } satisfies ComponentResult)
    return
  }

  if (context.input.attempt >= 2) {
    context.emit('capped', { ...context.input, draft, status: 'capped' } satisfies ComponentResult)
    return
  }

  console.log(`Evaluator requested a revision: ${context.input.task.id}`)
  context.emit('revise', {
    ...context.input,
    feedback: context.input.task.requiredPhrase,
  })
})

build.link(evaluate, 'evaluate')
evaluate.link(build, 'revise')
const component = new Flow(build, {
  name: 'component quality loop',
  exits: ['passed', 'capped'],
  maxActivations: 5,
})

const settle = node<QualityState, ComponentResult>((context) => context.end(context.input))
component.link(settle, 'passed')
component.link(settle, 'capped')

const dispatch = node<QualityState>((context) => {
  const tasks = context.state.tasks
  if (tasks === undefined) throw new Error('quality tasks are missing')
  for (const task of tasks) context.emit('improve', { task, attempt: 0 } satisfies ComponentJob)
})

dispatch.link(component, 'improve')
const components = new Flow(dispatch, {
  name: 'component workers',
  concurrency: 2,
  combine(context, result) {
    const completed = [...(result.outputs as ComponentResult[])].sort((left, right) => left.task.id.localeCompare(right.task.id))
    context.state.componentResults = completed

    if (completed.some((item) => item.status === 'capped')) {
      context.state.outcome = 'stopped'
      context.state.stopReason = 'A component exhausted its iteration cap.'
      context.emit('stopped')
      return
    }

    console.log('Every component reached its local quality bar')
    context.emit('ready', completed)
  },
})

const integrate = node<QualityState, readonly ComponentResult[]>((context) => {
  context.state.integrationAttempt += 1
  const drafts = context.input.map((item) => item.draft)
  context.state.artifact = context.state.integrationAttempt === 1 ? drafts[0] : `Cookbook benchmark candidate. ${drafts.join(' ')}`
  console.log(`Integrated artifact attempt ${context.state.integrationAttempt}`)
})

const judge = node<QualityState, readonly ComponentResult[]>((context) => {
  const artifact = context.state.artifact
  if (artifact === undefined) throw new Error('integrated artifact is missing')

  const missing = context.input.filter((item) => !artifact.includes(item.task.requiredPhrase))
  if (missing.length === 0) {
    context.state.outcome = 'parity'
    context.emit('approved')
    return
  }

  if (context.state.integrationAttempt >= 2) {
    context.state.outcome = 'stopped'
    context.state.stopReason = `Still missing ${missing.map((item) => item.task.requiredPhrase).join(', ')}`
    context.emit('stopped')
    return
  }

  console.log('Whole-artifact judge requested a revision')
  context.emit('revise', context.input)
})

integrate.link(judge)
judge.link(integrate, 'revise')

const setBar = node<QualityState>((context) => {
  context.state.tasks = [
    { id: 'contract', requiredPhrase: 'explicit acceptance criteria' },
    { id: 'evidence', requiredPhrase: 'observable evidence' },
  ]
  console.log('Quality bar: cookbook benchmark')
})

setBar.link(components)
components.link(integrate, 'ready')

const qualityFlow = new Flow(setBar, {
  exits: ['approved', 'stopped'],
  maxActivations: 10,
})

const state = await qualityFlow.run({ integrationAttempt: 0 })
console.log(`Outcome: ${state.outcome}`)
console.log(state.artifact)
if (state.stopReason !== undefined) console.log(`Residual gap: ${state.stopReason}`)
