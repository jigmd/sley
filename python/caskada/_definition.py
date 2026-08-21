# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Graph definitions, validation, compilation, and topology inspection.
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import (
    Any,
    Generic,
    Literal,
    TypeAlias,
    TypedDict,
    final,
    overload,
)

from ._contracts import (
    MAX_PORTABLE_COLLECTION_LENGTH,
    MAX_SAFE_INTEGER,
    Action,
    DuplicateLinkError,
    FlowCombineHandler,
    FlowRecoveryHandler,
    GraphDefinitionError,
    InputT,
    NodeHandler,
    NodeRecoveryHandler,
    RetryPolicy,
    StateT,
    _definition_error,
    _require_control_string,
    _require_positive_integer,
)

_UNLABELLED = object()


class GraphElement(ABC, Generic[StateT]):
    __slots__ = ("_links_by_action", "_links_in_order", "_name")

    def __init__(self, name: str) -> None:
        self._name = _require_control_string(name, "element name")
        self._links_in_order: list[Link[StateT]] = []
        self._links_by_action: dict[object, Link[StateT]] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    @abstractmethod
    def _caskada_kind(self) -> Literal["node", "flow"]: ...

    @overload
    def link(self, target: GraphElement[StateT], /) -> None: ...

    @overload
    def link(
        self,
        target: GraphElement[StateT],
        /,
        action: Action,
    ) -> None: ...

    def link(
        self,
        target: GraphElement[StateT],
        /,
        action: Action | object = _UNLABELLED,
    ) -> None:
        if not isinstance(target, GraphElement):
            raise GraphDefinitionError("link target must be a GraphElement")

        if action is _UNLABELLED:
            key = _UNLABELLED
            public_action = None
        else:
            public_action = _require_control_string(action, "link action")
            key = public_action

        if key in self._links_by_action:
            description = "unlabelled" if key is _UNLABELLED else repr(public_action)
            raise DuplicateLinkError(f"duplicate link action: {description}")
        if len(self._links_in_order) >= MAX_PORTABLE_COLLECTION_LENGTH:
            raise GraphDefinitionError("link collection exceeds the portable limit")

        record = Link(action=public_action, target=target)
        self._links_by_action[key] = record
        self._links_in_order.append(record)

    def links(self) -> tuple[Link[StateT], ...]:
        return tuple(self._links_in_order)


@dataclass(frozen=True, slots=True)
class Link(Generic[StateT]):
    action: Action | None
    target: GraphElement[StateT]


class _NodeConstructionToken:
    pass


_NODE_CONSTRUCTION_TOKEN = _NodeConstructionToken()


@final
class Node(GraphElement[StateT], Generic[StateT]):
    __slots__ = ("_handler", "_recover", "_retry", "_timeout_ms")

    def __new__(cls, token: _NodeConstructionToken, /) -> Node[StateT]:
        if cls is not Node or token is not _NODE_CONSTRUCTION_TOKEN:
            raise TypeError("Use node(handler) to create a Node")
        return super().__new__(cls)

    def __init__(self, token: _NodeConstructionToken, /) -> None:
        if token is not _NODE_CONSTRUCTION_TOKEN:
            raise TypeError("Use node(handler) to create a Node")
        super().__init__("anonymous")
        self._handler: Callable[..., Any] | None = None
        self._recover: Callable[..., Any] | None = None
        self._retry = RetryPolicy()
        self._timeout_ms: int | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("Node is final; wrap a handler with node(...)")

    @property
    def _caskada_kind(self) -> Literal["node"]:
        return "node"

    @property
    def retry(self) -> RetryPolicy:
        return self._retry

    @property
    def timeout_ms(self) -> int | None:
        return self._timeout_ms


class _FlowConstructionToken:
    pass


_FLOW_CONSTRUCTION_TOKEN = _FlowConstructionToken()


class _FlowDefinition(GraphElement[StateT], Generic[StateT]):
    __slots__ = (
        "_combine",
        "_concurrency",
        "_entry",
        "_exits",
        "_max_activations",
        "_recover",
    )

    def __init__(
        self,
        token: _FlowConstructionToken,
        entry: GraphElement[StateT],
        *,
        name: str | None = None,
        exits: Sequence[Action] = (),
        concurrency: int = 1,
        max_activations: int | None = None,
        combine: FlowCombineHandler[StateT] | None = None,
        recover: FlowRecoveryHandler[StateT] | None = None,
    ) -> None:
        if token is not _FLOW_CONSTRUCTION_TOKEN:
            raise TypeError("Use Flow(entry) to create a Flow")
        if not isinstance(entry, GraphElement):
            raise GraphDefinitionError("Flow.entry must be a GraphElement")
        if name is not None:
            resolved_name = _require_control_string(name, "Flow.name")
        else:
            resolved_name = "Flow"
        resolved_exits = _capture_exits(exits)
        resolved_concurrency = _require_positive_integer(
            concurrency, "Flow.concurrency"
        )
        resolved_max_activations = (
            None
            if max_activations is None
            else _require_positive_integer(max_activations, "Flow.max_activations")
        )
        if combine is not None and not callable(combine):
            raise GraphDefinitionError("Flow.combine must be callable")
        if recover is not None and not callable(recover):
            raise GraphDefinitionError("Flow.recover must be callable")

        super().__init__(resolved_name)
        self._entry = entry
        self._exits = resolved_exits
        self._concurrency = resolved_concurrency
        self._max_activations = resolved_max_activations
        self._combine = combine
        self._recover = recover

    @property
    def _caskada_kind(self) -> Literal["flow"]:
        return "flow"

    @property
    def entry(self) -> GraphElement[StateT]:
        return self._entry

    @property
    def exits(self) -> tuple[Action, ...]:
        return self._exits

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @property
    def max_activations(self) -> int | None:
        return self._max_activations

def _capture_exits(exits: Sequence[Action]) -> tuple[Action, ...]:
    if isinstance(exits, (str, bytes)) or not isinstance(exits, Sequence):
        raise GraphDefinitionError("Flow.exits must be a sequence of actions")
    try:
        gross_length = len(exits)
    except BaseException as error:
        raise _definition_error("Flow.exits could not be captured", error)
    if gross_length > MAX_PORTABLE_COLLECTION_LENGTH:
        raise GraphDefinitionError("Flow.exits exceeds the portable limit")

    try:
        iterator = iter(exits)
    except BaseException as error:
        raise _definition_error("Flow.exits could not be captured", error)

    captured: list[str] = []
    seen: set[str] = set()
    while True:
        try:
            raw_action = next(iterator)
        except StopIteration:
            break
        except BaseException as error:
            raise _definition_error("Flow.exits could not be captured", error)
        if len(captured) >= MAX_PORTABLE_COLLECTION_LENGTH:
            raise GraphDefinitionError("Flow.exits exceeds the portable limit")
        action = _require_control_string(raw_action, "Flow exit")
        if action in seen:
            raise GraphDefinitionError(f"duplicate Flow exit: {action!r}")
        captured.append(action)
        seen.add(action)
    return tuple(captured)


class CompiledLinkDescription(TypedDict):
    action: Action | None
    target_element_id: int


class CompiledRetryDescription(TypedDict):
    max_attempts: int


class CompiledNodeDescription(TypedDict):
    element_id: int
    kind: Literal["node"]
    name: str
    parent_scope_definition_id: int
    links: list[CompiledLinkDescription]
    retry: CompiledRetryDescription
    timeout_ms: int | None


class CompiledFlowElementDescription(TypedDict):
    element_id: int
    kind: Literal["flow"]
    name: str
    parent_scope_definition_id: int | None
    owned_scope_definition_id: int
    links: list[CompiledLinkDescription]


CompiledElementDescription: TypeAlias = (
    CompiledNodeDescription | CompiledFlowElementDescription
)


class CompiledScopeDescription(TypedDict):
    scope_definition_id: int
    owner_element_id: int
    parent_scope_definition_id: int | None
    entry_element_id: int
    exits: list[Action]
    concurrency: int
    max_activations: int | None


class CompiledRootDescription(TypedDict):
    element_id: int
    scope_definition_id: int


class CompiledDescription(TypedDict):
    schema_version: Literal[1]
    auto_max_concurrency: int
    root: CompiledRootDescription
    scope_definitions: list[CompiledScopeDescription]
    elements: list[CompiledElementDescription]


@dataclass(frozen=True, slots=True)
class _CompiledLink:
    action: Action | None
    target_element_id: int


@dataclass(frozen=True, slots=True)
class _CompiledPlacement:
    element_id: int
    kind: Literal["node", "flow"]
    name: str
    parent_scope_definition_id: int | None
    definition: GraphElement[Any]
    links: tuple[_CompiledLink, ...]
    owned_scope_definition_id: int | None = None
    retry: RetryPolicy | None = None
    timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class _CompiledScope:
    scope_definition_id: int
    owner_element_id: int
    parent_scope_definition_id: int | None
    entry_element_id: int
    exits: tuple[Action, ...]
    concurrency: int
    max_activations: int | None
    flow: _FlowDefinition[Any]
    combine: Callable[..., Any] | None
    recover: Callable[..., Any] | None


@dataclass(frozen=True, slots=True)
class _CompiledSnapshot:
    root: _FlowDefinition[Any]
    auto_max_concurrency: int
    scopes: tuple[_CompiledScope, ...]
    placements: tuple[_CompiledPlacement, ...]


@dataclass(slots=True)
class _ScopeWork:
    scope_definition_id: int
    owner_element_id: int
    parent_scope_definition_id: int | None
    flow: _FlowDefinition[Any]


class _DefinitionCompiler:
    def __init__(self, root: _FlowDefinition[Any]) -> None:
        self.root = root
        self.next_element_id = 2
        self.next_scope_definition_id = 2
        self.compiled_connection_count = 0
        self.compiled_exit_count = 0
        self.placements_by_id: dict[int, _CompiledPlacement] = {
            1: _CompiledPlacement(
                element_id=1,
                kind="flow",
                name=root.name,
                parent_scope_definition_id=None,
                definition=root,
                links=(),
                owned_scope_definition_id=1,
            )
        }
        self.owned_scope_by_element: dict[int, int] = {1: 1}
        self.scope_queue = [
            _ScopeWork(
                scope_definition_id=1,
                owner_element_id=1,
                parent_scope_definition_id=None,
                flow=root,
            )
        ]
        self.compiled_scopes: list[_CompiledScope] = []

    def compile(self) -> _CompiledSnapshot:
        scope_index = 0
        while scope_index < len(self.scope_queue):
            scope = self.scope_queue[scope_index]
            scope_index += 1
            self._compile_scope(scope)

        ordered_placements = tuple(
            self.placements_by_id[element_id]
            for element_id in range(1, self.next_element_id)
        )
        return _CompiledSnapshot(
            root=self.root,
            auto_max_concurrency=max(
                scope.concurrency for scope in self.compiled_scopes
            ),
            scopes=tuple(self.compiled_scopes),
            placements=ordered_placements,
        )

    def _compile_scope(self, scope: _ScopeWork) -> None:
        self.compiled_exit_count = _reserve_portable_total(
            self.compiled_exit_count,
            len(scope.flow.exits),
            "exit",
        )
        placements: dict[GraphElement[Any], int] = {}
        placement_queue: list[GraphElement[Any]] = []
        entry_element_id = self._enqueue(
            scope,
            scope.flow.entry,
            placements,
            placement_queue,
        )

        placement_index = 0
        while placement_index < len(placement_queue):
            element = placement_queue[placement_index]
            placement_index += 1
            element_id = placements[element]
            definition_links = element.links()
            self.compiled_connection_count = _reserve_portable_total(
                self.compiled_connection_count,
                len(definition_links),
                "connection",
            )
            compiled_links = tuple(
                _CompiledLink(
                    link.action,
                    self._enqueue(
                        scope,
                        link.target,
                        placements,
                        placement_queue,
                    ),
                )
                for link in definition_links
            )
            self._capture_placement(scope, element, element_id, compiled_links)

        self.compiled_scopes.append(
            _CompiledScope(
                scope_definition_id=scope.scope_definition_id,
                owner_element_id=scope.owner_element_id,
                parent_scope_definition_id=scope.parent_scope_definition_id,
                entry_element_id=entry_element_id,
                exits=scope.flow.exits,
                concurrency=scope.flow.concurrency,
                max_activations=scope.flow.max_activations,
                flow=scope.flow,
                combine=scope.flow._combine,
                recover=scope.flow._recover,
            )
        )

    def _enqueue(
        self,
        scope: _ScopeWork,
        element: GraphElement[Any],
        placements: dict[GraphElement[Any], int],
        placement_queue: list[GraphElement[Any]],
    ) -> int:
        if type(element) is not Node and not isinstance(element, _FlowDefinition):
            raise GraphDefinitionError("unsupported GraphElement definition")
        existing = placements.get(element)
        if existing is not None:
            return existing
        _require_compiled_capacity(self.next_element_id, "element")
        element_id = self.next_element_id
        self.next_element_id += 1
        placements[element] = element_id
        placement_queue.append(element)

        if isinstance(element, _FlowDefinition):
            _require_compiled_capacity(self.next_scope_definition_id, "scope")
            owned_scope_id = self.next_scope_definition_id
            self.next_scope_definition_id += 1
            self.owned_scope_by_element[element_id] = owned_scope_id
            self.scope_queue.append(
                _ScopeWork(
                    scope_definition_id=owned_scope_id,
                    owner_element_id=element_id,
                    parent_scope_definition_id=scope.scope_definition_id,
                    flow=element,
                )
            )
        return element_id

    def _capture_placement(
        self,
        scope: _ScopeWork,
        element: GraphElement[Any],
        element_id: int,
        compiled_links: tuple[_CompiledLink, ...],
    ) -> None:
        if type(element) is Node:
            self.placements_by_id[element_id] = _CompiledPlacement(
                element_id=element_id,
                kind="node",
                name=element.name,
                parent_scope_definition_id=scope.scope_definition_id,
                definition=element,
                links=compiled_links,
                retry=element.retry,
                timeout_ms=element.timeout_ms,
            )
            return
        self.placements_by_id[element_id] = _CompiledPlacement(
            element_id=element_id,
            kind="flow",
            name=element.name,
            parent_scope_definition_id=scope.scope_definition_id,
            definition=element,
            links=compiled_links,
            owned_scope_definition_id=self.owned_scope_by_element[element_id],
        )


def _compile_flow(root: _FlowDefinition[StateT]) -> _CompiledSnapshot:
    if not isinstance(root, _FlowDefinition):
        raise GraphDefinitionError("only runtime-created Flow definitions can compile")

    _validate_containment(root)
    return _DefinitionCompiler(root).compile()


def _validate_containment(root: _FlowDefinition[Any]) -> None:
    adjacency: dict[
        _FlowDefinition[Any], tuple[_FlowDefinition[Any], ...]
    ] = {}
    colors: dict[_FlowDefinition[Any], Literal["active", "complete"]] = {
        root: "active"
    }
    stack: list[tuple[_FlowDefinition[Any], int]] = [(root, 0)]

    while stack:
        flow, child_index = stack[-1]
        children = adjacency.get(flow)
        if children is None:
            children = _nested_flow_definitions(flow)
            adjacency[flow] = children
        if child_index >= len(children):
            colors[flow] = "complete"
            stack.pop()
            continue

        child = children[child_index]
        stack[-1] = (flow, child_index + 1)
        color = colors.get(child)
        if color == "active":
            raise GraphDefinitionError("recursive Flow containment is not allowed")
        if color == "complete":
            continue
        colors[child] = "active"
        stack.append((child, 0))


def _nested_flow_definitions(
    flow: _FlowDefinition[Any],
) -> tuple[_FlowDefinition[Any], ...]:
    seen: set[GraphElement[Any]] = set()
    worklist: list[GraphElement[Any]] = [flow.entry]
    nested: list[_FlowDefinition[Any]] = []
    work_index = 0
    while work_index < len(worklist):
        element = worklist[work_index]
        work_index += 1
        if element in seen:
            continue
        seen.add(element)
        if type(element) is not Node and not isinstance(element, _FlowDefinition):
            raise GraphDefinitionError("unsupported GraphElement definition")
        if isinstance(element, _FlowDefinition):
            nested.append(element)
        for link in element.links():
            worklist.append(link.target)
    return tuple(nested)


def _require_compiled_capacity(next_id: int, kind: str) -> None:
    if next_id > MAX_SAFE_INTEGER or next_id > MAX_PORTABLE_COLLECTION_LENGTH:
        raise GraphDefinitionError(
            f"compiled {kind} collection exceeds the portable limit"
        )


def _reserve_portable_total(current: int, addition: int, kind: str) -> int:
    if addition > MAX_PORTABLE_COLLECTION_LENGTH - current:
        raise GraphDefinitionError(
            f"compiled {kind} collection exceeds the portable limit"
        )
    return current + addition


def _describe_compiled(snapshot: _CompiledSnapshot) -> CompiledDescription:
    elements: list[CompiledElementDescription] = []
    for placement in snapshot.placements:
        links: list[CompiledLinkDescription] = [
            {
                "action": link.action,
                "target_element_id": link.target_element_id,
            }
            for link in placement.links
        ]
        if placement.kind == "node":
            if placement.retry is None or placement.parent_scope_definition_id is None:
                raise RuntimeError("invalid compiled Node placement")
            elements.append(
                {
                    "element_id": placement.element_id,
                    "kind": "node",
                    "name": placement.name,
                    "parent_scope_definition_id": placement.parent_scope_definition_id,
                    "links": links,
                    "retry": {"max_attempts": placement.retry.max_attempts},
                    "timeout_ms": placement.timeout_ms,
                }
            )
        else:
            if placement.owned_scope_definition_id is None:
                raise RuntimeError("invalid compiled Flow placement")
            elements.append(
                {
                    "element_id": placement.element_id,
                    "kind": "flow",
                    "name": placement.name,
                    "parent_scope_definition_id": placement.parent_scope_definition_id,
                    "owned_scope_definition_id": placement.owned_scope_definition_id,
                    "links": links,
                }
            )

    return {
        "schema_version": 1,
        "auto_max_concurrency": snapshot.auto_max_concurrency,
        "root": {"element_id": 1, "scope_definition_id": 1},
        "scope_definitions": [
            {
                "scope_definition_id": scope.scope_definition_id,
                "owner_element_id": scope.owner_element_id,
                "parent_scope_definition_id": scope.parent_scope_definition_id,
                "entry_element_id": scope.entry_element_id,
                "exits": list(scope.exits),
                "concurrency": scope.concurrency,
                "max_activations": scope.max_activations,
            }
            for scope in snapshot.scopes
        ],
        "elements": elements,
    }


_MISSING = object()


@overload
def node(
    handler: NodeHandler[StateT, InputT],
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Node[StateT]: ...


@overload
def node(
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Callable[[NodeHandler[StateT, InputT]], Node[StateT]]: ...


def node(
    handler: NodeHandler[StateT, InputT] | object = _MISSING,
    /,
    *,
    name: str | None = None,
    retry: RetryPolicy = RetryPolicy(),
    timeout_ms: int | None = None,
    recover: NodeRecoveryHandler[StateT, InputT] | None = None,
) -> Node[StateT] | Callable[[NodeHandler[StateT, InputT]], Node[StateT]]:
    if type(retry) is not RetryPolicy:
        raise GraphDefinitionError("node retry must be an exact RetryPolicy")
    if timeout_ms is not None:
        _require_positive_integer(timeout_ms, "Node.timeout_ms")
    if recover is not None and not callable(recover):
        raise GraphDefinitionError("Node.recover must be callable")
    if name is not None:
        _require_control_string(name, "Node.name")

    def create(callback: NodeHandler[StateT, InputT]) -> Node[StateT]:
        if not callable(callback):
            raise GraphDefinitionError("node handler must be callable")
        if name is None:
            try:
                inferred_name = getattr(callback, "__name__", None)
            except BaseException as error:
                raise _definition_error("node handler name could not be read", error)
            resolved_name = (
                inferred_name
                if type(inferred_name) is str and bool(inferred_name)
                else "anonymous"
            )
        else:
            resolved_name = name

        occurrence: Node[StateT] = Node(_NODE_CONSTRUCTION_TOKEN)
        occurrence._name = resolved_name
        occurrence._handler = callback
        occurrence._recover = recover
        occurrence._retry = retry
        occurrence._timeout_ms = timeout_ms
        return occurrence

    if handler is _MISSING:
        return create
    return create(handler)  # type: ignore[arg-type]
