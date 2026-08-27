import { fileURLToPath } from 'node:url'
import { Flow, node } from '@jigging/sley'
import { Client } from '@modelcontextprotocol/client'
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio'

interface ToolCall {
  name: string
  arguments: Record<string, unknown>
}

interface McpState {
  client: Client
  toolNames?: readonly string[]
  answer?: string
}

const discover = node<McpState>(async (context) => {
  const { tools } = await context.state.client.listTools()
  context.state.toolNames = tools.map((tool) => tool.name)
  console.log(`Discovered tools: ${context.state.toolNames.join(', ')}`)
})

const choose = node<McpState>((context) => {
  if (!context.state.toolNames?.includes('add')) {
    throw new Error('required add tool was not discovered')
  }

  const call: ToolCall = {
    name: 'add',
    arguments: { left: 2, right: 5 },
  }
  console.log(`Selected tool: ${call.name}`)
  context.emit('call', call)
})

const invoke = node<McpState, ToolCall>(async (context) => {
  const result = await context.state.client.callTool({
    name: context.input.name,
    arguments: context.input.arguments,
  })
  if (result.isError === true) throw new Error('MCP tool reported an error')

  const text = result.content.find((block) => block.type === 'text')
  if (text?.type !== 'text') throw new Error('MCP tool did not return text')

  context.state.answer = text.text
  console.log(`Tool result: ${text.text}`)
})

discover.link(choose)
choose.link(invoke, 'call')
const toolFlow = new Flow(discover)

const client = new Client({ name: 'sley-cookbook', version: '1.0.0' })
const serverCommand = fileURLToPath(new URL('./node_modules/.bin/tsx', import.meta.url))

await client.connect(
  new StdioClientTransport({
    command: serverCommand,
    args: [fileURLToPath(new URL('./server.ts', import.meta.url))],
  }),
)

try {
  await toolFlow.run({ client })
} finally {
  await client.close()
}
