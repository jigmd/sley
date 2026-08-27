import * as z from 'zod/v4'
import { McpServer } from '@modelcontextprotocol/server'
import { serveStdio } from '@modelcontextprotocol/server/stdio'

function createServer() {
  const server = new McpServer({ name: 'cookbook-math', version: '1.0.0' })

  server.registerTool(
    'add',
    {
      description: 'Add two numbers',
      inputSchema: z.object({
        left: z.number(),
        right: z.number(),
      }),
    },
    ({ left, right }) => ({
      content: [{ type: 'text', text: String(left + right) }],
    }),
  )

  server.registerTool(
    'multiply',
    {
      description: 'Multiply two numbers',
      inputSchema: z.object({
        left: z.number(),
        right: z.number(),
      }),
    },
    ({ left, right }) => ({
      content: [{ type: 'text', text: String(left * right) }],
    }),
  )

  return server
}

void serveStdio(createServer)
console.error('Math MCP server ready')
