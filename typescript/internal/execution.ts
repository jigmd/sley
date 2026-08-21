// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

// Public Flow lifecycle composed from inert definitions and runtime scheduling.

import { compiledFlowConstructionToken } from './contracts.js'
import { compileFlow, describeCompiled, flowConstructionToken, FlowDefinition, GraphElement } from './definition.js'
import { captureRunOptions, projectState, startRuntime } from './scheduling.js'
import { captureInitialState } from './state.js'

import type { RunHandle, RunOptions } from './contracts.js'
import type { CompiledDescription, CompiledSnapshot, FlowOptions } from './definition.js'

export class Flow<State extends object = Record<string, unknown>> extends FlowDefinition<State> {
  constructor(entry: GraphElement<State>, options?: FlowOptions<State>) {
    if (new.target !== Flow) throw new TypeError('Flow subclasses are not supported')
    super(flowConstructionToken, entry, options)
  }

  compile(): CompiledFlow<State> {
    return new CompiledFlow<State>(compiledFlowConstructionToken, compileFlow(this))
  }

  start(initialState: Readonly<State>, options?: RunOptions): RunHandle<State> {
    const capturedOptions = captureRunOptions(options)
    const snapshot = compileFlow(this)
    const state = captureInitialState(initialState)
    return startRuntime(snapshot, state, capturedOptions)
  }

  run(initialState: Readonly<State>, options?: RunOptions): Promise<State> {
    return projectState(this.start(initialState, options))
  }
}

const compiledSnapshots = new WeakMap<object, CompiledSnapshot>()

export class CompiledFlow<State extends object = Record<string, unknown>> {
  constructor(token: typeof compiledFlowConstructionToken, snapshot?: CompiledSnapshot) {
    if (new.target !== CompiledFlow || token !== compiledFlowConstructionToken || snapshot === undefined) {
      throw new TypeError('Use Flow.compile() to create a CompiledFlow')
    }
    compiledSnapshots.set(this, snapshot)
  }

  start(initialState: Readonly<State>, options?: RunOptions): RunHandle<State> {
    const capturedOptions = captureRunOptions(options)
    const state = captureInitialState(initialState)
    return startRuntime(this.snapshot(), state, capturedOptions)
  }

  run(initialState: Readonly<State>, options?: RunOptions): Promise<State> {
    return projectState(this.start(initialState, options))
  }

  describe(): CompiledDescription {
    return describeCompiled(this.snapshot())
  }

  private snapshot(): CompiledSnapshot {
    const snapshot = compiledSnapshots.get(this)
    if (snapshot === undefined) throw new Error('CompiledFlow snapshot is missing')
    return snapshot
  }
}
