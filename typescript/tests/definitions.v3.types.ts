import { CompiledFlow, Flow, Node, node } from '../caskada'

import type { Context } from '../caskada'

interface StateA {
  value?: string
}

interface StateB {
  count?: number
}

interface JobInput {
  job: string
}

const source = node<StateA>((context) => {
  context.state.value = 'ready'
})

const target = node<StateA, JobInput>((context) => {
  context.state.value = context.input.job
})

source.link(target)
source.link(target, 'job')
const compiled: CompiledFlow<StateA> = new Flow<StateA>(source).compile()
compiled.describe()

const wrongState = node<StateB>(() => {})
// @ts-expect-error Graph topology is invariant in State.
source.link(wrongState)
// @ts-expect-error A Flow entry must use the same State.
new Flow<StateA>(wrongState)
// @ts-expect-error Links are target-first.
source.link('job', target)
// @ts-expect-error Explicit undefined is not an unlabelled action.
source.link(target, undefined)
// @ts-expect-error Node construction is factory-only.
new Node()
