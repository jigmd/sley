import { Flow, node } from '@jigging/sley'

interface GreetingState {
  name: string
  greeting?: string
}

const greet = node<GreetingState>((context) => {
  context.state.greeting = `Hello, ${context.state.name}!`
})

const state = await new Flow(greet).run({ name: 'Sley' })
console.log(state.greeting)
