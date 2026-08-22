export interface Service {
  name: string
  healthy: boolean
  delayMs: number
}

export interface CheckResult {
  name: string
  healthy: boolean
}

export interface BatchState {
  services: readonly Service[]
  summary?: {
    healthy: string[]
    unhealthy: string[]
  }
}
