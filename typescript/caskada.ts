// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2026, Victor Duarte

export { CaskadaError, DuplicateLinkError, GraphDefinitionError, RunError } from './contracts.js'
export { Flow, GraphElement, Node, node } from './graph.js'

export type {
  Action,
  Completed,
  Context,
  EndTerminal,
  ExitTerminal,
  Failed,
  Failure,
  FailureKind,
  FlowCombineHandler,
  FlowRecoveryHandler,
  NodeHandler,
  NodeRecoveryHandler,
  RetryPolicy,
  RunHandle,
  RunResult,
  ScopeFailure,
  ScopeResult,
  Terminal,
} from './contracts.js'

export type { CompiledDescription, CompiledFlow, FlowOptions, Link, NodeOptions } from './graph.js'
