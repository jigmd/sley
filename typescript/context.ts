// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2026, Victor Duarte

import type { Action, Context } from './contracts.js'

export class InvalidOutcome extends Error {}

export interface Intent {
  readonly kind: 'emit' | 'end'
  readonly action: Action | null
  readonly value: unknown
  readonly hasValue: boolean
}

export class CallbackContext<State extends object> implements Context<State> {
  readonly #state: State
  readonly #input: unknown
  readonly #intents: Intent[] = []
  #open = true

  constructor(state: State, input: unknown) {
    this.#state = state
    this.#input = input
  }

  get state(): State {
    this.checkOpen()
    return this.#state
  }

  get input(): unknown {
    this.checkOpen()
    return this.#input
  }

  emit(): void
  emit(action: undefined, input: unknown): void
  emit(action: Action): void
  emit(action: Action, input: unknown): void
  emit(action?: Action, input?: unknown): void {
    this.checkOpen()
    if (arguments.length > 2) throw new InvalidOutcome('emit accepts at most two arguments')
    if (arguments.length === 1 && (typeof action !== 'string' || !action)) {
      throw new InvalidOutcome('emit action must be a nonempty string')
    }
    if (arguments.length === 2 && action !== undefined && (typeof action !== 'string' || !action)) {
      throw new InvalidOutcome('emit action must be undefined or a nonempty string')
    }
    this.#intents.push({
      kind: 'emit',
      action: action ?? null,
      value: arguments.length === 2 ? input : this.#input,
      hasValue: true,
    })
  }

  end(): void
  end(output: unknown): void
  end(output?: unknown): void {
    this.checkOpen()
    if (arguments.length > 1) throw new InvalidOutcome('end accepts at most one argument')
    this.#intents.push({ kind: 'end', action: null, value: output, hasValue: arguments.length === 1 })
  }

  close(): readonly Intent[] {
    this.#open = false
    return this.#intents
  }

  private checkOpen(): void {
    if (!this.#open) throw new Error('Context is closed')
  }
}
