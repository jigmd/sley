// This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
// Copyright (c) 2025, Victor Duarte

export {
  MAX_SAFE_INTEGER,
  MAX_PORTABLE_COLLECTION_LENGTH,
  RUN_EVENT_SCHEMA_VERSION,
  CaskadaError,
  GraphDefinitionError,
  DuplicateLinkError,
  OptionValidationError,
  RunError,
} from './internal/contracts.js'

export type {
  Action,
  Phase,
  Context,
  Cancellation,
  EndTerminal,
  ExitTerminal,
  Terminal,
  NonEmptyTerminals,
  ScopeResult,
  ScopeFailure,
  FailureKind,
  InvalidOutcomeReason,
  InvalidCombinationReason,
  LimitName,
  InternalReason,
  FailureDetail,
  Failure,
  EventBase,
  ReportPayload,
  RunEvent,
  Observer,
  RunStats,
  ObserverDiagnostic,
  CancellationInfo,
  RunOptions,
  CompletedResult,
  FailedResult,
  CancelledResult,
  AbandonedResult,
  RunResult,
  RunHandle,
  NodeHandler,
  NodeRecoveryHandler,
  FlowCombineHandler,
  FlowRecoveryHandler,
  RetryOptions,
  RetryPolicy,
} from './internal/contracts.js'

export { GraphElement, Node, node } from './internal/definition.js'
export { CompiledFlow, Flow } from './internal/execution.js'

export type {
  Link,
  NodeOptions,
  FlowOptions,
  CompiledLinkDescription,
  CompiledNodeDescription,
  CompiledFlowElementDescription,
  CompiledElementDescription,
  CompiledScopeDescription,
  CompiledDescription,
} from './internal/definition.js'
