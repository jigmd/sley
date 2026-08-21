// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// Persistent run-state validation and carrier behavior.

import { MAX_PORTABLE_COLLECTION_LENGTH, OptionValidationError } from './contracts.js'
import { SemanticMisuse } from './failures.js'

const stateTargets = new WeakMap<object, Record<string, unknown>>()

function captureOptionValue<Value>(operation: () => Value, message: string): Value {
  try {
    return operation()
  } catch (error) {
    throw new OptionValidationError(message, { cause: error })
  }
}

export function captureInitialState<State extends object>(initialState: Readonly<State>): State {
  if (typeof initialState !== 'object' || initialState === null || Array.isArray(initialState)) {
    throw new OptionValidationError('initialState must be a plain data record')
  }
  const prototype = captureOptionValue(() => Object.getPrototypeOf(initialState), 'initialState prototype could not be read')
  if (prototype !== Object.prototype && prototype !== null) {
    throw new OptionValidationError('initialState must be a plain data record')
  }
  const keys = captureOptionValue(() => Reflect.ownKeys(initialState), 'initialState keys could not be read')
  if (keys.length > MAX_PORTABLE_COLLECTION_LENGTH) {
    throw new OptionValidationError('initialState exceeds the portable limit')
  }
  const target: Record<string, unknown> = {}
  for (const key of keys) {
    if (typeof key !== 'string') throw new OptionValidationError('initialState keys must be strings')
    const descriptor = captureOptionValue(
      () => Reflect.getOwnPropertyDescriptor(initialState, key),
      'initialState property could not be captured',
    )
    if (descriptor === undefined || !descriptor.enumerable || !('value' in descriptor)) {
      throw new OptionValidationError('initialState properties must be enumerable data properties')
    }
    Object.defineProperty(target, key, {
      value: descriptor.value,
      writable: true,
      enumerable: true,
      configurable: true,
    })
  }
  const carrier = new Proxy(target, stateProxyHandler) as State
  stateTargets.set(carrier, target)
  return carrier
}

const stateProxyHandler: ProxyHandler<Record<string, unknown>> = {
  get(target, property, receiver) {
    if (typeof property === 'symbol') return undefined
    return Reflect.get(target, property, receiver)
  },
  set(target, property, value) {
    if (typeof property !== 'string') {
      throw new SemanticMisuse('state_record_misuse', 'state keys must be strings')
    }
    Object.defineProperty(target, property, stateDataDescriptor(value))
    return true
  },
  deleteProperty(target, property) {
    if (typeof property !== 'string') {
      throw new SemanticMisuse('state_record_misuse', 'state keys must be strings')
    }
    return Reflect.deleteProperty(target, property)
  },
  defineProperty(target, property, descriptor) {
    if (
      typeof property !== 'string' ||
      'get' in descriptor ||
      'set' in descriptor ||
      descriptor.configurable === false ||
      descriptor.enumerable === false ||
      descriptor.writable === false
    ) {
      throw new SemanticMisuse('state_record_misuse', 'invalid state property descriptor')
    }
    const previous = Reflect.getOwnPropertyDescriptor(target, property)
    Object.defineProperty(target, property, stateDataDescriptor('value' in descriptor ? descriptor.value : previous?.value))
    return true
  },
  getOwnPropertyDescriptor(target, property) {
    if (typeof property !== 'string') return undefined
    return Reflect.getOwnPropertyDescriptor(target, property)
  },
  ownKeys(target) {
    return Reflect.ownKeys(target)
  },
  has(target, property) {
    if (typeof property === 'symbol') return false
    return Reflect.has(target, property)
  },
  getPrototypeOf() {
    return Object.prototype
  },
  setPrototypeOf() {
    throw new SemanticMisuse('state_record_misuse', 'state prototype is fixed')
  },
  isExtensible() {
    return true
  },
  preventExtensions() {
    throw new SemanticMisuse('state_record_misuse', 'state must remain extensible')
  },
}

function stateDataDescriptor(value: unknown): PropertyDescriptor {
  return {
    value,
    writable: true,
    enumerable: true,
    configurable: true,
  }
}

export function resolveStateCarrier<State extends object>(resolve: (value: State | PromiseLike<State>) => void, state: State): void {
  const target = stateTargets.get(state)
  if (target === undefined) throw new Error('state carrier target is missing')
  const previous = Reflect.getOwnPropertyDescriptor(target, 'then')
  Object.defineProperty(target, 'then', stateDataDescriptor(undefined))
  try {
    resolve(state)
  } finally {
    if (previous === undefined) Reflect.deleteProperty(target, 'then')
    else Object.defineProperty(target, 'then', previous)
  }
}
