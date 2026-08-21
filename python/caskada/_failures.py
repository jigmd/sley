# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Failure construction, packets, and retry-policy evaluation.
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import overload

from ._contracts import (
    _FAILURE_MESSAGES,
    Failure,
    FailureDetail,
    FailureKind,
    InvalidOutcomeReason,
)


class _SemanticMisuse(TypeError):
    def __init__(self, reason: InvalidOutcomeReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class _FailureLeaf:
    failures: tuple[Failure, ...]


@dataclass(frozen=True, slots=True)
class _FailureConcat:
    left: _FailureTree
    right: _FailureTree
    size: int


_FailureTree = _FailureLeaf | _FailureConcat


class _FailureSequence(Sequence[Failure]):
    """Immutable failure rope; concatenation never copies Failure references."""

    __slots__ = ("_root", "_size")

    def __init__(self, root: _FailureTree | None = None, size: int = 0) -> None:
        self._root = root
        self._size = size

    @classmethod
    def one(cls, failure: Failure) -> _FailureSequence:
        return cls(_FailureLeaf((failure,)), 1)

    @classmethod
    def from_sequence(cls, failures: Sequence[Failure]) -> _FailureSequence:
        if isinstance(failures, cls):
            return failures
        items = tuple(failures)
        return cls() if not items else cls(_FailureLeaf(items), len(items))

    def append(self, failure: Failure) -> _FailureSequence:
        return self.concat(self.one(failure))

    def concat(self, other: _FailureSequence) -> _FailureSequence:
        if not self:
            return other
        if not other:
            return self
        return _FailureSequence(
            _FailureConcat(
                self._require_root(), other._require_root(), len(self) + len(other)
            ),
            len(self) + len(other),
        )

    def materialize(self) -> tuple[Failure, ...]:
        return tuple(self)

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[Failure]:
        if self._root is None:
            return
        stack = [self._root]
        while stack:
            node = stack.pop()
            if isinstance(node, _FailureLeaf):
                yield from node.failures
            else:
                stack.append(node.right)
                stack.append(node.left)

    @overload
    def __getitem__(self, index: int) -> Failure: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Failure, ...]: ...

    def __getitem__(self, index: int | slice) -> Failure | tuple[Failure, ...]:
        if isinstance(index, slice):
            return self.materialize()[index]
        normalized = index + self._size if index < 0 else index
        if normalized < 0 or normalized >= self._size:
            raise IndexError("failure sequence index out of range")
        for position, failure in enumerate(self):
            if position == normalized:
                return failure
        raise RuntimeError("failure sequence size invariant violated")

    def _require_root(self) -> _FailureTree:
        if self._root is None:
            raise RuntimeError("empty failure sequence has no root")
        return self._root


class _ScopeEpoch:
    __slots__ = ("_live",)

    def __init__(self) -> None:
        self._live = True

    def close(self) -> None:
        self._live = False

    def require_live(self) -> None:
        if not self._live:
            raise RuntimeError("ScopeFailure suppression view is closed")


class _ScopedFailureIterator(Iterator[Failure]):
    __slots__ = ("_epoch", "_iterator")

    def __init__(self, epoch: _ScopeEpoch, failures: _FailureSequence) -> None:
        self._epoch = epoch
        self._iterator = iter(failures)

    def __next__(self) -> Failure:
        self._epoch.require_live()
        return next(self._iterator)


class _ScopedFailureView(Sequence[Failure]):
    __slots__ = ("_epoch", "_failures")

    def __init__(self, epoch: _ScopeEpoch, failures: _FailureSequence) -> None:
        self._epoch = epoch
        self._failures = failures

    def __len__(self) -> int:
        self._epoch.require_live()
        return len(self._failures)

    def __iter__(self) -> Iterator[Failure]:
        self._epoch.require_live()
        return _ScopedFailureIterator(self._epoch, self._failures)

    @overload
    def __getitem__(self, index: int) -> Failure: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Failure, ...]: ...

    def __getitem__(self, index: int | slice) -> Failure | tuple[Failure, ...]:
        self._epoch.require_live()
        return self._failures[index]


class _FailureFactory:
    """Allocates portable failure identities and immutable failure records."""

    __slots__ = ("_next_id",)

    def __init__(self) -> None:
        self._next_id = 1

    def new(
        self,
        kind: FailureKind,
        *,
        scope_id: int,
        activation_id: int | None,
        element_id: int | None,
        attempt: int | None,
        cause: BaseException | None = None,
        detail: FailureDetail | None = None,
        previous: Failure | None = None,
    ) -> Failure:
        failure = Failure(
            failure_id=self._next_id,
            kind=kind,
            message=_FAILURE_MESSAGES[kind],
            cause=cause,
            scope_id=scope_id,
            activation_id=activation_id,
            element_id=element_id,
            attempt=attempt,
            detail=detail,
            previous=previous,
        )
        self._next_id += 1
        return failure


@dataclass(slots=True)
class _FailurePacket:
    packet_id: int
    sequence: int
    primary: Failure
    suppressed: _FailureSequence
    input: object
    owner: _PacketOwner
    state: str = "active"


@dataclass(frozen=True, slots=True)
class _PacketOwner:
    kind: str
    owner_id: int | None


@dataclass(frozen=True, slots=True)
class _PacketDrain:
    primary: Failure | None
    suppressed: _FailureSequence


class _PacketRegistry:
    """Insertion-ordered failure packets with one explicit runtime owner."""

    __slots__ = ("_active", "_next_id", "_next_sequence")

    def __init__(self) -> None:
        self._active: OrderedDict[int, _FailurePacket] = OrderedDict()
        self._next_id = 1
        self._next_sequence = 1

    def create(
        self,
        primary: Failure,
        input: object,
        owner: _PacketOwner,
        *,
        suppressed: Sequence[Failure] = (),
    ) -> int:
        packet_id = self._next_id
        self._next_id += 1
        packet = _FailurePacket(
            packet_id,
            self._next_sequence,
            primary,
            _FailureSequence.from_sequence(suppressed),
            input,
            owner,
        )
        self._next_sequence += 1
        self._active[packet_id] = packet
        return packet_id

    def get(self, packet_id: int) -> _FailurePacket:
        packet = self._active.get(packet_id)
        if packet is None or packet.state != "active":
            raise RuntimeError("failure packet is not active")
        return packet

    def replace(
        self,
        packet_id: int,
        failure: Failure,
        *,
        input: object = None,
        replace_input: bool = False,
    ) -> None:
        packet = self.get(packet_id)
        packet.primary = failure
        if replace_input:
            packet.input = input

    def append(self, packet_id: int, failure: Failure) -> None:
        packet = self.get(packet_id)
        packet.suppressed = packet.suppressed.append(failure)

    def transfer(self, packet_id: int, owner: _PacketOwner) -> None:
        self.get(packet_id).owner = owner

    def merge(self, target_id: int, source_id: int) -> None:
        if target_id == source_id:
            raise RuntimeError("failure packet cannot merge into itself")
        target = self.get(target_id)
        source = self.get(source_id)
        target.suppressed = target.suppressed.append(source.primary).concat(
            source.suppressed
        )
        source.state = "merged"
        del self._active[source_id]

    def consume(self, packet_id: int) -> None:
        packet = self.get(packet_id)
        packet.state = "consumed"
        del self._active[packet_id]

    def drain(self, controlling_id: int | None) -> _PacketDrain:
        controlling = None if controlling_id is None else self.get(controlling_id)
        ordered = list(self._active.values())
        if controlling is not None:
            ordered.remove(controlling)
            ordered.insert(0, controlling)

        primary = None if controlling is None else controlling.primary
        suppressed = _FailureSequence()
        for packet in ordered:
            if packet is controlling:
                suppressed = suppressed.concat(packet.suppressed)
            else:
                suppressed = suppressed.append(packet.primary).concat(packet.suppressed)
            packet.state = "drained"
        self._active.clear()
        return _PacketDrain(primary, suppressed)

    def active_packets(self) -> tuple[_FailurePacket, ...]:
        return tuple(self._active.values())

    def require_empty(self) -> None:
        if self._active:
            raise RuntimeError("run settled with active failure packets")


def _is_recoverable_failure(failure: Failure) -> bool:
    return failure.kind in {
        "handler",
        "handler_timeout",
        "node_recovery",
        "flow_combine",
        "flow_recovery",
    }
