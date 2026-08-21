# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Failure construction, packets, and retry-policy evaluation.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
    suppressed: tuple[Failure, ...]
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
    suppressed: tuple[Failure, ...]


class _PacketRegistry:
    """Insertion-ordered failure packets with one explicit runtime owner."""

    __slots__ = ("_active", "_next_id", "_next_sequence")

    def __init__(self) -> None:
        self._active: dict[int, _FailurePacket] = {}
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
            tuple(suppressed),
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
        # ponytail: copy short suppression tuples; revisit only with measured depth.
        packet.suppressed += (failure,)

    def transfer(self, packet_id: int, owner: _PacketOwner) -> None:
        self.get(packet_id).owner = owner

    def merge(self, target_id: int, source_id: int) -> None:
        if target_id == source_id:
            raise RuntimeError("failure packet cannot merge into itself")
        target = self.get(target_id)
        source = self.get(source_id)
        target.suppressed += (source.primary, *source.suppressed)
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
        suppressed: tuple[Failure, ...] = ()
        for packet in ordered:
            if packet is controlling:
                suppressed += packet.suppressed
            else:
                suppressed += (packet.primary, *packet.suppressed)
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
