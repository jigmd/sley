import readline from 'node:readline'
import { Flow, node } from '@jigging/sley'
import { callLLM } from './utils'

import type { ChatState } from './types'

function promptUser(): Promise<string> {
  const terminal = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  })
  return new Promise((resolve) => {
    terminal.question('You: ', (input) => {
      terminal.close()
      resolve(input)
    })
  })
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
await new Flow(chat).run({})
