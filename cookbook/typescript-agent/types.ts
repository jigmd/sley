export interface AgentState {
  question: string
  research?: string
  searchQuery?: string
  answer?: string
}

export type Decision = { action: 'search'; reason: string; searchQuery: string } | { action: 'answer'; reason: string }
