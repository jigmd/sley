export interface SourceRecord {
  id: number
  amount: string
}

export interface ImportedRecord {
  id: number
  amount: number
}

export interface BatchState {
  records: readonly SourceRecord[]
  imported?: readonly ImportedRecord[]
  error?: string
}
