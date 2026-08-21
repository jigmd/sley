# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ._contracts import OptionValidationError

type _StateCarrier = dict[str, Any]


def _capture_initial_state(initial_state: object) -> _StateCarrier:
    if not isinstance(initial_state, Mapping):
        raise OptionValidationError("initial_state must be a Mapping")
    try:
        state = dict(initial_state)
    except BaseException as cause:
        raise OptionValidationError(
            "initial_state could not be shallow-copied"
        ) from cause
    if any(type(key) is not str for key in state):
        raise OptionValidationError("initial_state keys must be exact strings")
    return cast(_StateCarrier, state)
