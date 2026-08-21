// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

import { OptionValidationError } from './contracts.js'

export function captureInitialState<State extends object>(initialState: Readonly<State>): State {
  if (typeof initialState !== 'object' || initialState === null || Array.isArray(initialState)) {
    throw new OptionValidationError('initialState must be a data record')
  }
  try {
    const state = { ...initialState } as State
    if (Reflect.ownKeys(state).some((key) => typeof key !== 'string')) {
      throw new OptionValidationError('initialState keys must be strings')
    }
    return state
  } catch (cause) {
    if (cause instanceof OptionValidationError) throw cause
    throw new OptionValidationError('initialState could not be shallow-copied', { cause })
  }
}

export function resolveStateCarrier<State extends object>(resolve: (value: State | PromiseLike<State>) => void, state: State): void {
  const previous = Object.getOwnPropertyDescriptor(state, 'then')
  Object.defineProperty(state, 'then', { value: undefined, configurable: true })
  try {
    resolve(state)
  } finally {
    if (previous === undefined) Reflect.deleteProperty(state, 'then')
    else Object.defineProperty(state, 'then', previous)
  }
}
