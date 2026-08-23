# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2026, Victor Duarte
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ._contracts import Action

_MISSING = object()


class _InvalidOutcome(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _Intent:
    kind: Literal["emit", "end"]
    action: Action | None
    value: object
    has_value: bool


class _Context:
    def __init__(self, state: object, input: object) -> None:
        self._state = state
        self._input = input
        self._intents: list[_Intent] = []
        self._open = True

    @property
    def state(self) -> object:
        self._check_open()
        return self._state

    @property
    def input(self) -> object:
        self._check_open()
        return self._input

    def emit(
        self,
        action: object = _MISSING,
        input: object = _MISSING,
    ) -> None:
        self._check_open()
        public_action: str | None = None
        if action is not _MISSING:
            if not isinstance(action, str) or not action:
                raise _InvalidOutcome("emit action must be a nonempty string")
            public_action = action
        value = self._input if input is _MISSING else input
        self._intents.append(_Intent("emit", public_action, value, True))

    def end(self, output: object = _MISSING) -> None:
        self._check_open()
        self._intents.append(
            _Intent(
                "end",
                None,
                None if output is _MISSING else output,
                output is not _MISSING,
            )
        )

    def close(self) -> tuple[_Intent, ...]:
        self._open = False
        return tuple(self._intents)

    def _check_open(self) -> None:
        if not self._open:
            raise RuntimeError("Context is closed")
