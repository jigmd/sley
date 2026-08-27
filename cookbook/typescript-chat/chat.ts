import readline from 'node:readline'
import { Flow, node } from '@jigging/sley'
import { callLLM } from './utils'

import type { ChatState } from './types'

const terminal = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
})
const inputLines = terminal[Symbol.asyncIterator]()

async function promptUser(): Promise<string> {
  process.stdout.write('You: ')
  const next = await inputLines.next()
  return next.done ? 'exit' : next.value
}

const chat = node<ChatState>(async (context) => {
  const messages = context.state.messages ?? []
  if (context.state.messages === undefined) {
    context.state.messages = messages
    console.log("Welcome to the chat! Type 'exit' to end the conversation.")
  }

  const input = await promptUser()
  if (input === 'exit') {
    console.log('Goodbye!')
    // end() finishes this branch instead of following the self-link below.
    context.end()
    return
  }

  messages.push({ role: 'user', content: input })
  const response = await callLLM(messages)
  messages.push({ role: 'assistant', content: response })
  console.log(`Assistant: ${response}`)
  // No control call: successful completion follows the unlabelled self-link.
})

chat.link(chat)
try {
  await new Flow(chat, { maxActivations: 100 }).run({})
} finally {
  terminal.close()
}
