import { Flow, node } from '@jigging/sley'

interface SectionTask {
  id: string
  goal: string
}

interface Section {
  id: string
  text: string
}

interface BriefState {
  topic: string
  foundation?: string
  plan?: readonly SectionTask[]
  sections?: readonly Section[]
  brief?: string
}

const plan = node<BriefState>((context) => {
  context.state.foundation = `Every section must help a reader apply ${context.state.topic}.`
  context.state.plan = [
    { id: 'problem', goal: 'Name the practical problem.' },
    { id: 'method', goal: 'Explain the smallest useful method.' },
    { id: 'check', goal: 'Give one observable success check.' },
  ]
  console.log('Planner froze the foundation')
})

const dispatch = node<BriefState>((context) => {
  const tasks = context.state.plan
  if (tasks === undefined) throw new Error('plan is missing')
  for (const task of tasks) context.emit('write', task)
})

const write = node<BriefState, SectionTask>((context) => {
  const foundation = context.state.foundation
  if (foundation === undefined) throw new Error('foundation is missing')
  context.end({
    id: context.input.id,
    text: `${context.input.goal} ${foundation}`,
  } satisfies Section)
})

dispatch.link(write, 'write')
const workers = new Flow(dispatch, {
  name: 'section workers',
  concurrency: 3,
  combine(context, result) {
    context.state.sections = [...(result.outputs as Section[])].sort((left, right) => left.id.localeCompare(right.id))
    context.emit()
  },
})

const edit = node<BriefState>((context) => {
  const sections = context.state.sections
  if (sections === undefined) throw new Error('sections are missing')
  context.state.brief = sections.map((section) => section.text).join('\n')
  console.log(`Integrated brief:\n${context.state.brief}`)
})

plan.link(workers)
workers.link(edit)

await new Flow(plan).run({ topic: 'orchestrator-worker graphs' })
