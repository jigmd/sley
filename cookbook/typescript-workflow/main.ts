import { Flow, node } from '@jigging/sley'

interface ArticleState {
  topic: string
  outline?: readonly string[]
  draft?: string
  article?: string
}

const outline = node<ArticleState>((context) => {
  context.state.outline = [`Why ${context.state.topic} matters`, 'A small example', 'What to try next']
  console.log('Outline ready')
})

const draft = node<ArticleState>((context) => {
  const sections = context.state.outline
  if (sections === undefined) throw new Error('outline is missing')
  context.state.draft = sections.map((section) => `${section}.`).join(' ')
  console.log('Draft ready')
})

const polish = node<ArticleState>((context) => {
  const draftText = context.state.draft
  if (draftText === undefined) throw new Error('draft is missing')
  context.state.article = `${draftText} Start with one visible workflow.`
  console.log('Article polished')
})

outline.link(draft)
draft.link(polish)

const state = await new Flow(outline).run({ topic: 'workflow graphs' })
console.log(`Final article: ${state.article}`)
