import { agentFlow } from './flow'

async function main() {
  const question = process.argv[2] ?? 'What is the latest Deepseek LLM model?'
  const state = await agentFlow.run({ question })

  if (state.answer === undefined) throw new Error('The agent finished without an answer')
}

main().catch(console.error)
