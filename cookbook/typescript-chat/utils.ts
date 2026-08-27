import OpenAI from 'openai'

import type { Message } from './types'

export async function callLLM(messages: Message[]): Promise<string> {
  const apiKey = process.env.OPENROUTER_API_KEY ?? process.env.OPENAI_API_KEY
  if (!apiKey) throw new Error('Set OPENAI_API_KEY or OPENROUTER_API_KEY')
  const client = new OpenAI(
    process.env.OPENROUTER_API_KEY
      ? {
          apiKey,
          baseURL: 'https://openrouter.ai/api/v1',
        }
      : { apiKey, baseURL: process.env.OPENAI_BASE_URL },
  )
  const response = await client.chat.completions.create({
    model: process.env.OPENAI_MODEL ?? 'gpt-4o-mini',
    messages,
  })
  const content = response.choices[0]?.message.content
  if (!content) throw new Error('Model returned no answer')
  return content
}
