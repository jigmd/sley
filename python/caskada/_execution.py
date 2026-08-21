# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Public Flow lifecycle composed from inert definitions and runtime scheduling.
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Generic, final

from ._contracts import (
    Action,
    FlowCombineHandler,
    FlowRecoveryHandler,
    GraphDefinitionError,
    RunError,
    RunHandle,
    RunOptions,
    StateT,
)
from ._definition import (
    _FLOW_CONSTRUCTION_TOKEN,
    CompiledDescription,
    GraphElement,
    _compile_flow,
    _CompiledSnapshot,
    _describe_compiled,
    _FlowDefinition,
)
from ._scheduling import (
    _capture_run_options,
    _require_running_loop,
    _start_runtime,
)
from ._state import _capture_initial_state


class Flow(_FlowDefinition[StateT], Generic[StateT]):
    __slots__ = ()

    def __init__(
        self,
        entry: GraphElement[StateT],
        *,
        name: str | None = None,
        exits: Sequence[Action] = (),
        concurrency: int = 1,
        max_activations: int | None = None,
        combine: FlowCombineHandler[StateT] | None = None,
        recover: FlowRecoveryHandler[StateT] | None = None,
    ) -> None:
        if type(self) is not Flow:
            raise GraphDefinitionError("Flow subclasses are not supported")
        super().__init__(
            _FLOW_CONSTRUCTION_TOKEN,
            entry,
            name=name,
            exits=exits,
            concurrency=concurrency,
            max_activations=max_activations,
            combine=combine,
            recover=recover,
        )

    def compile(self) -> CompiledFlow[StateT]:
        if type(self) is not Flow:
            raise GraphDefinitionError(
                "only runtime-created Flow definitions can compile"
            )
        return CompiledFlow(_COMPILED_FLOW_CONSTRUCTION_TOKEN, _compile_flow(self))

    def start(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> RunHandle[StateT]:
        loop = _require_running_loop()
        captured_options = _capture_run_options(options)
        compiled = self.compile()
        state = _capture_initial_state(initial_state)
        return _start_runtime(compiled._snapshot, state, loop, captured_options)

    async def run(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> StateT:
        handle = self.start(initial_state, options=options)
        try:
            result = await handle.result()
        except asyncio.CancelledError:
            handle.cancel("caller_cancelled")
            raise
        if result.status == "completed":
            return result.state
        raise RunError(result)


class _CompiledFlowConstructionToken:
    pass


_COMPILED_FLOW_CONSTRUCTION_TOKEN = _CompiledFlowConstructionToken()


@final
class CompiledFlow(Generic[StateT]):
    __slots__ = ("_snapshot",)

    def __new__(
        cls,
        token: _CompiledFlowConstructionToken,
        snapshot: _CompiledSnapshot | None = None,
        /,
    ) -> CompiledFlow[StateT]:
        if cls is not CompiledFlow or token is not _COMPILED_FLOW_CONSTRUCTION_TOKEN:
            raise TypeError("Use Flow.compile() to create a CompiledFlow")
        return super().__new__(cls)

    def __init__(
        self,
        token: _CompiledFlowConstructionToken,
        snapshot: _CompiledSnapshot | None = None,
        /,
    ) -> None:
        if token is not _COMPILED_FLOW_CONSTRUCTION_TOKEN or snapshot is None:
            raise TypeError("Use Flow.compile() to create a CompiledFlow")
        self._snapshot = snapshot

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("CompiledFlow is final; use Flow.compile()")

    def start(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> RunHandle[StateT]:
        loop = _require_running_loop()
        captured_options = _capture_run_options(options)
        state = _capture_initial_state(initial_state)
        return _start_runtime(self._snapshot, state, loop, captured_options)

    async def run(
        self,
        initial_state: StateT,
        *,
        options: RunOptions | None = None,
    ) -> StateT:
        result = await self.start(initial_state, options=options).result()
        if result.status == "completed":
            return result.state
        raise RunError(result)

    def describe(self) -> CompiledDescription:
        return _describe_compiled(self._snapshot)
