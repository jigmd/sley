import OpenAI from 'openai'
import { DDGS } from '@phukon/duckduckgo-search'

export async function callLLM(prompt: string): Promise<string> {
  const client = new OpenAI(
    process.env.OPENROUTER_API_KEY
      ? {
          apiKey: process.env.OPENROUTER_API_KEY,
          baseURL: 'https://openrouter.ai/api/v1',
        }
      : { apiKey: process.env.OPENAI_API_KEY },
  )
  const response = await client.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [{ role: 'user', content: prompt }],
  })
  return response.choices[0]?.message.content ?? ''
}

export async function webSearch(query: string) {
  return new DDGS().text({ keywords: query, maxResults: 5 })
}
