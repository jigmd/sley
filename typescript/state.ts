// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2026, Victor Duarte

export function captureInitialState<State extends object>(initialState: Readonly<State>): State {
  if (typeof initialState !== 'object' || initialState === null || Array.isArray(initialState)) {
    throw new TypeError('initialState must be an object')
  }
  const prototype = Object.getPrototypeOf(initialState)
  if (prototype !== Object.prototype && prototype !== null) {
    throw new TypeError('initialState must be a plain object')
  }
  if (Reflect.ownKeys(initialState).some((key) => typeof key !== 'string')) {
    throw new TypeError('initialState keys must be strings')
  }
  return { ...initialState }
}

export function resolveState<State extends object>(resolve: (state: State) => void, state: State): void {
  if (typeof Reflect.get(state, 'then') !== 'function') {
    resolve(state)
    return
  }
  const previous = Object.getOwnPropertyDescriptor(state, 'then')
  try {
    Object.defineProperty(
      state,
      'then',
      previous !== undefined && 'value' in previous ? { ...previous, value: undefined } : { value: undefined, configurable: true },
    )
  } catch {
    throw new TypeError('final state with a callable then property must remain mutable')
  }
  try {
    resolve(state)
  } finally {
    if (previous === undefined) Reflect.deleteProperty(state, 'then')
    else Object.defineProperty(state, 'then', previous)
  }
}
