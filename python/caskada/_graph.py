# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2026, Victor Duarte
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeAlias, cast, overload

from ._contracts import (
    Action,
    DuplicateLinkError,
    FlowCombineHandler,
    FlowRecoveryHandler,
    GraphDefinitionError,
    InputT,
    NodeHandler,
    NodeRecoveryHandler,
    RetryPolicy,
    RunError,
    RunHandle,
    StateT,
    _nonempty_string,
    _positive_integer,
)
from ._state import _capture_initial_state

_UNLABELLED = object()
_MISSING = object()
CompiledDescription: TypeAlias = dict[str, object]


@dataclass(frozen=True, slots=True)
class Link(Generic[StateT]):
    action: Action | None
    target: GraphElement[StateT]


class GraphElement(Generic[StateT]):
    def __init__(self, name: str) -> None:
        self._name = _nonempty_string(name, "element name")
        self._links: dict[object, Link[StateT]] = {}

    @property
    def name(self) -> str:
        return self._name

    @overload
    def link(self, target: GraphElement[StateT], /) -> None: ...

    @overload
    def link(self, target: GraphElement[StateT], action: Action, /) -> None: ...

    def link(
        self,
        target: GraphElement[StateT],
        action: Action | object = _UNLABELLED,
        /,
    ) -> None:
        if not isinstance(target, GraphElement):
            raise GraphDefinitionError("link target must be a Node or Flow")
        key: object = _UNLABELLED
        public_action: str | None = None
        if action is not _UNLABELLED:
            public_action = _nonempty_string(action, "link action")
            key = public_action
        if key in self._links:
            label = "unlabelled" if key is _UNLABELLED else repr(public_action)
            raise DuplicateLinkError(f"duplicate link action: {label}")
        self._links[key] = Link(public_action, target)

    def links(self) -> tuple[Link[StateT], ...]:
        return tuple(self._links.values())


class Node(GraphElement[StateT], Generic[StateT, InputT]):
    def __init__(
        self,
        handler: NodeHandler[StateT, InputT],
        *,
        name: str,
        retry: RetryPolicy,
        recover: NodeRecoveryHandler[StateT, InputT] | None,
    ) -> None:
        super().__init__(name)
        self.handler = handler
        self.retry = retry
        self.recover = recover


@overload
def node(
    handler: NodeHandler[StateT, InputT],
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Node[StateT, InputT]: ...


@overload
def node(
    *,
    name: str | None = None,
    retry: RetryPolicy | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Callable[[NodeHandler[StateT, InputT]], Node[StateT, InputT]]: ...


def node(
    handler: NodeHandler[StateT, InputT] | object = _MISSING,
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> (
    Node[StateT, InputT] | Callable[[NodeHandler[StateT, InputT]], Node[StateT, InputT]]
):
    policy = RetryPolicy() if retry is None else retry
    if not isinstance(policy, RetryPolicy):
        raise GraphDefinitionError("node retry must be a RetryPolicy")
    if recover is not None and not callable(recover):
        raise GraphDefinitionError("Node.recover must be callable")
    if name is not None:
        _nonempty_string(name, "Node.name")

    def create(callback: NodeHandler[StateT, InputT]) -> Node[StateT, InputT]:
        if not callable(callback):
            raise GraphDefinitionError("node handler must be callable")
        inferred = getattr(callback, "__name__", "anonymous")
        resolved_name = name or (inferred if isinstance(inferred, str) else "anonymous")
        return Node(callback, name=resolved_name, retry=policy, recover=recover)

    if handler is _MISSING:
        return create
    return create(cast(NodeHandler[StateT, InputT], handler))


class Flow(GraphElement[StateT], Generic[StateT]):
    def __init__(
        self,
        entry: GraphElement[StateT],
        *,
        name: str = "Flow",
        exits: Iterable[Action] = (),
        concurrency: int = 1,
        max_activations: int | None = None,
        combine: FlowCombineHandler[StateT] | None = None,
        recover: FlowRecoveryHandler[StateT] | None = None,
    ) -> None:
        if not isinstance(entry, GraphElement):
            raise GraphDefinitionError("Flow.entry must be a Node or Flow")
        if isinstance(exits, (str, bytes)):
            raise GraphDefinitionError("Flow.exits must be an iterable of actions")
        captured_exits = tuple(
            _nonempty_string(action, "Flow exit") for action in exits
        )
        if len(set(captured_exits)) != len(captured_exits):
            raise GraphDefinitionError("Flow.exits contains a duplicate action")
        _positive_integer(concurrency, "Flow.concurrency")
        if max_activations is not None:
            _positive_integer(max_activations, "Flow.max_activations")
        if combine is not None and not callable(combine):
            raise GraphDefinitionError("Flow.combine must be callable")
        if recover is not None and not callable(recover):
            raise GraphDefinitionError("Flow.recover must be callable")

        super().__init__(name)
        self.entry = entry
        self.exits = captured_exits
        self.concurrency = concurrency
        self.max_activations = max_activations
        self.combine = combine
        self.recover = recover

    def compile(self) -> CompiledFlow[StateT]:
        return CompiledFlow(_compile(self))

    def start(self, initial_state: StateT) -> RunHandle[StateT]:
        return self.compile().start(initial_state)

    async def run(self, initial_state: StateT) -> StateT:
        return await self.compile().run(initial_state)


class CompiledFlow(Generic[StateT]):
    def __init__(self, snapshot: _CompiledSnapshot) -> None:
        self._snapshot = snapshot

    def start(self, initial_state: StateT) -> RunHandle[StateT]:
        from ._runner import _start

        return _start(self._snapshot, _capture_initial_state(initial_state))

    async def run(self, initial_state: StateT) -> StateT:
        result = await self.start(initial_state).result()
        if result.status == "failed":
            raise RunError(result)
        return result.state

    def describe(self) -> CompiledDescription:
        return _describe(self._snapshot)


@dataclass(frozen=True, slots=True)
class _CompiledLink:
    action: Action | None
    target_element_id: int


@dataclass(frozen=True, slots=True)
class _CompiledPlacement:
    element_id: int
    kind: Literal["node", "flow"]
    name: str
    links: tuple[_CompiledLink, ...]
    handler: Callable[..., Any] | None = None
    retry: RetryPolicy | None = None
    recover: Callable[..., Any] | None = None
    owned_scope_id: int | None = None


@dataclass(frozen=True, slots=True)
class _CompiledScope:
    scope_id: int
    owner_element_id: int
    parent_scope_id: int | None
    entry_element_id: int
    name: str
    exits: tuple[Action, ...]
    concurrency: int
    max_activations: int | None
    combine: Callable[..., Any] | None
    recover: Callable[..., Any] | None


@dataclass(frozen=True, slots=True)
class _CompiledSnapshot:
    scopes: tuple[_CompiledScope, ...]
    placements: tuple[_CompiledPlacement, ...]

    def scope(self, scope_id: int) -> _CompiledScope:
        return self.scopes[scope_id - 1]

    def placement(self, element_id: int) -> _CompiledPlacement:
        return self.placements[element_id - 1]


@dataclass(slots=True)
class _ScopeWork:
    scope_id: int
    owner_element_id: int
    parent_scope_id: int | None
    flow: Flow[Any]
    ancestors: tuple[Flow[Any], ...]


class _Compiler:
    def __init__(self, root: Flow[Any]) -> None:
        self.next_element_id = 2
        self.next_scope_id = 2
        self.placements: dict[int, _CompiledPlacement] = {
            1: _CompiledPlacement(1, "flow", root.name, (), owned_scope_id=1)
        }
        self.scopes: dict[int, _CompiledScope] = {}
        self.work = [_ScopeWork(1, 1, None, root, (root,))]

    def compile(self) -> _CompiledSnapshot:
        for scope in self.work:
            self._compile_scope(scope)
        return _CompiledSnapshot(
            tuple(self.scopes[index] for index in range(1, self.next_scope_id)),
            tuple(self.placements[index] for index in range(1, self.next_element_id)),
        )

    def _compile_scope(self, scope: _ScopeWork) -> None:
        element_ids: dict[GraphElement[Any], int] = {}
        elements: list[GraphElement[Any]] = []

        def add(element: GraphElement[Any]) -> int:
            existing = element_ids.get(element)
            if existing is not None:
                return existing
            if not isinstance(element, (Node, Flow)):
                raise GraphDefinitionError("unsupported graph element")
            element_id = self.next_element_id
            self.next_element_id += 1
            element_ids[element] = element_id
            elements.append(element)
            if isinstance(element, Flow):
                if element in scope.ancestors:
                    raise GraphDefinitionError(
                        "recursive Flow containment is not allowed"
                    )
                owned_scope_id = self.next_scope_id
                self.next_scope_id += 1
                self.work.append(
                    _ScopeWork(
                        owned_scope_id,
                        element_id,
                        scope.scope_id,
                        element,
                        (*scope.ancestors, element),
                    )
                )
            return element_id

        entry_id = add(scope.flow.entry)
        for element in elements:
            links = tuple(
                _CompiledLink(link.action, add(link.target)) for link in element.links()
            )
            element_id = element_ids[element]
            if isinstance(element, Node):
                self.placements[element_id] = _CompiledPlacement(
                    element_id,
                    "node",
                    element.name,
                    links,
                    element.handler,
                    element.retry,
                    element.recover,
                )
            else:
                owned_scope_id = next(
                    item.scope_id
                    for item in self.work
                    if item.owner_element_id == element_id
                )
                self.placements[element_id] = _CompiledPlacement(
                    element_id,
                    "flow",
                    element.name,
                    links,
                    owned_scope_id=owned_scope_id,
                )

        self.scopes[scope.scope_id] = _CompiledScope(
            scope.scope_id,
            scope.owner_element_id,
            scope.parent_scope_id,
            entry_id,
            scope.flow.name,
            scope.flow.exits,
            scope.flow.concurrency,
            scope.flow.max_activations,
            scope.flow.combine,
            scope.flow.recover,
        )


def _compile(root: Flow[StateT]) -> _CompiledSnapshot:
    if not isinstance(root, Flow):
        raise GraphDefinitionError("compile requires a Flow")
    return _Compiler(root).compile()


def _describe(snapshot: _CompiledSnapshot) -> CompiledDescription:
    return {
        "schema_version": 1,
        "root": {"element_id": 1, "scope_id": 1},
        "scopes": [
            {
                "scope_id": scope.scope_id,
                "owner_element_id": scope.owner_element_id,
                "parent_scope_id": scope.parent_scope_id,
                "entry_element_id": scope.entry_element_id,
                "name": scope.name,
                "exits": list(scope.exits),
                "concurrency": scope.concurrency,
                "max_activations": scope.max_activations,
            }
            for scope in snapshot.scopes
        ],
        "elements": [
            {
                "element_id": element.element_id,
                "kind": element.kind,
                "name": element.name,
                "links": [
                    {
                        "action": link.action,
                        "target_element_id": link.target_element_id,
                    }
                    for link in element.links
                ],
                **(
                    {"max_attempts": element.retry.max_attempts}
                    if element.retry is not None
                    else {"owned_scope_id": element.owned_scope_id}
                ),
            }
            for element in snapshot.placements
        ],
    }
