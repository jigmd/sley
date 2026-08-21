// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

export { CaskadaError, DuplicateLinkError, GraphDefinitionError, RunError } from './internal/contracts.js'
export { Flow, GraphElement, Node, node } from './internal/definition.js'

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
} from './internal/contracts.js'

export type { CompiledDescription, CompiledFlow, FlowOptions, Link, NodeOptions } from './internal/definition.js'
