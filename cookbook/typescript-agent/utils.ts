import OpenAI from 'openai'

export async function callLLM(prompt: string): Promise<string> {
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
    messages: [{ role: 'user', content: prompt }],
  })
  const content = response.choices[0]?.message.content
  if (!content) throw new Error('Model returned no agent decision')
  return content
}

export async function webSearch(query: string) {
  const url = new URL('https://api.duckduckgo.com/')
  url.search = new URLSearchParams({ q: query, format: 'json', no_html: '1', no_redirect: '1' }).toString()
  const response = await fetch(url, { signal: AbortSignal.timeout(10_000) })
  if (!response.ok) throw new Error(`Search failed with HTTP ${response.status}`)
  return response.json()
}
