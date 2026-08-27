import { Flow, node } from '@jigging/sley'

interface SummaryState {
  text: string
  summary?: string
}

type Summarizer = (text: string) => string

function createFlow(summarize: Summarizer) {
  const summarizeText = node<SummaryState>(
    (context) => {
      context.state.summary = summarize(context.state.text)
    },
    {
      retry: {
        maxAttempts: 3,
        shouldRetry: (failure) => failure.kind === 'handler',
      },
      recover: (context, failure) => {
        context.state.summary = `Fallback after ${failure.attempt} attempts`
        context.emit()
      },
    },
  )

  return new Flow(summarizeText)
}

let transientAttempts = 0
const transient = await createFlow((text) => {
  transientAttempts += 1
  console.log(`Transient attempt ${transientAttempts}`)
  if (transientAttempts < 3) throw new Error('service is temporarily unavailable')
  return text.split(/\s+/).slice(0, 4).join(' ')
}).run({ text: 'Retries repeat the complete node handler safely' })

console.log(`Summary: ${transient.summary}`)

let permanentAttempts = 0
const recovered = await createFlow(() => {
  permanentAttempts += 1
  console.log(`Permanent attempt ${permanentAttempts}`)
  throw new Error('service remains unavailable')
}).run({ text: 'This request will use recovery' })

console.log(`Recovered summary: ${recovered.summary}`)
