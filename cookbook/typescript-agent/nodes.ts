import { node } from 'sley'
import { parse } from 'yaml'
import { callLLM, webSearch } from './utils'

import type { AgentState, Decision } from './types'

function parseDecision(response: string): Decision {
  const yaml = response.split('```yaml', 2)[1]?.split('```', 1)[0]
  if (yaml === undefined) throw new Error('LLM response must contain a YAML block')

  const value: unknown = parse(yaml)
  if (typeof value !== 'object' || value === null) {
    throw new Error('LLM decision must be a YAML object')
  }

  const decision = value as Record<string, unknown>
  if ((decision.action !== 'search' && decision.action !== 'answer') || typeof decision.reason !== 'string') {
    throw new Error('LLM decision needs a valid action and reason')
  }

  if (decision.action === 'search') {
    if (typeof decision.searchQuery !== 'string' || decision.searchQuery.trim() === '') {
      throw new Error('A search decision needs a non-empty searchQuery')
    }
    return {
      action: 'search',
      reason: decision.reason,
      searchQuery: decision.searchQuery,
    }
  }

  return { action: 'answer', reason: decision.reason }
}

export const decide = node<AgentState>(async (context) => {
  console.log('Deciding whether to search or answer the question...')
  const response = await callLLM(`
### Context
Current date: ${new Date().toISOString()}
Question: ${context.state.question}
Research: ${context.state.research ?? 'No previous search.'}

### Next Action
Choose whether to search for more information or answer now.

Return exactly one YAML code block in one of these forms:

\`\`\`yaml
action: search
reason: Why another search is needed
searchQuery: A concise query written for a search engine
\`\`\`

\`\`\`yaml
action: answer
reason: Why the available research is sufficient
\`\`\`

Use only the keys shown for the selected action. Do not write text outside the block.
`)
  const decision = parseDecision(response)
  console.log(`Reason: ${decision.reason}`)

  if (decision.action === 'search') {
    context.state.searchQuery = decision.searchQuery
    console.log(`Searching for: ${decision.searchQuery}`)
  } else {
    console.log('Research is sufficient; preparing the final answer.')
  }

  context.emit(decision.action)
})

export const search = node<AgentState>(async (context) => {
  const query = context.state.searchQuery
  if (query === undefined) throw new Error('searchQuery is missing')

  console.log('Calling web search tool.')
  const results = await webSearch(query)
  context.state.research = `${context.state.research ?? ''}\n\nSearch: ${query}\nResults: ${JSON.stringify(results)}`
  context.emit('decide')
})

export const answer = node<AgentState>(async (context) => {
  const response = await callLLM(`
Answer this question using the research below.

Question: ${context.state.question}
Research: ${context.state.research ?? 'No previous search.'}
`)
  context.state.answer = response
  console.log(`Final Answer: ${response}`)
})
