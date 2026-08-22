// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2026, Victor Duarte

export function captureInitialState<State extends object>(initialState: Readonly<State>): State {
  if (typeof initialState !== 'object' || initialState === null || Array.isArray(initialState)) {
    throw new TypeError('initialState must be an object')
  }
  if (Reflect.ownKeys(initialState).some((key) => typeof key !== 'string')) {
    throw new TypeError('initialState keys must be strings')
  }
  return { ...initialState }
}

export function resolveState<State extends object>(resolve: (state: State) => void, state: State): void {
  const previous = Object.getOwnPropertyDescriptor(state, 'then')
  Object.defineProperty(state, 'then', { value: undefined, configurable: true })
  try {
    resolve(state)
  } finally {
    if (previous === undefined) Reflect.deleteProperty(state, 'then')
    else Object.defineProperty(state, 'then', previous)
  }
}
