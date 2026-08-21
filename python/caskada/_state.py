# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar, cast

StateT = TypeVar("StateT")


def _capture_initial_state(initial_state: StateT) -> StateT:
    if not isinstance(initial_state, Mapping):
        raise TypeError("initial_state must be a mapping")
    state = dict(initial_state)
    if any(not isinstance(key, str) for key in state):
        raise TypeError("initial_state keys must be strings")
    return cast(StateT, state)
