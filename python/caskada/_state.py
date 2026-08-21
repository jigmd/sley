# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# Copyright (c) 2025, Victor Duarte
# Persistent run-state validation and carrier behavior.
from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Self,
    cast,
    overload,
)

from ._contracts import (
    MAX_PORTABLE_COLLECTION_LENGTH,
    OptionValidationError,
)
from ._failures import _SemanticMisuse

_MISSING = object()


class _StateCarrier(dict[str, Any]):
    """Invocation-owned native dictionary storage with portable string keys."""

    def __getitem__(self, key: object) -> Any:
        return super().__getitem__(_require_state_key(key))

    def __setitem__(self, key: object, value: Any) -> None:
        super().__setitem__(_require_state_key(key), value)

    def __delitem__(self, key: object) -> None:
        super().__delitem__(_require_state_key(key))

    def __contains__(self, key: object) -> bool:
        return super().__contains__(_require_state_key(key))

    def get(self, key: object, default: Any = None) -> Any:
        return super().get(_require_state_key(key), default)

    def setdefault(self, key: object, default: Any = None) -> Any:
        return super().setdefault(_require_state_key(key), default)

    @overload
    def pop(self, key: object) -> Any: ...

    @overload
    def pop(self, key: object, default: Any) -> Any: ...

    def pop(self, key: object, default: object = _MISSING) -> Any:
        checked = _require_state_key(key)
        if default is _MISSING:
            return super().pop(checked)
        return super().pop(checked, default)

    def update(self, *args: object, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 argument, got {len(args)}")
        if args:
            self._update_from(args[0])
        for key, value in kwargs.items():
            self[key] = value

    def copy(self) -> dict[str, Any]:
        return dict(self)

    def __or__(self, other: object) -> dict[str, Any]:  # type: ignore[override]
        if not isinstance(other, dict):
            return NotImplemented
        result = dict(self)
        _update_plain_dict(result, other)
        return result

    def __ror__(self, other: object) -> dict[str, Any]:  # type: ignore[override]
        if not isinstance(other, dict):
            return NotImplemented
        result: dict[str, Any] = {}
        _update_plain_dict(result, other)
        result.update(dict(self))
        return result

    def __ior__(self, other: object) -> Self:  # type: ignore[override]
        if not isinstance(other, Mapping):
            return NotImplemented
        self._update_from(other)
        return self

    @classmethod
    def fromkeys(  # type: ignore[override]
        cls, iterable: object, value: Any = None
    ) -> _StateCarrier:
        result = cls()
        for key in cast(Any, iterable):
            result[key] = value
        return result

    def _update_from(self, source: object) -> None:
        dynamic_source = cast(Any, source)
        try:
            keys_method = dynamic_source.keys
        except AttributeError:
            keys_method = None
        if keys_method is not None:
            keys = keys_method()
            for key in keys:
                checked = _require_state_key(key)
                value = dynamic_source[checked]
                super().__setitem__(checked, value)
            return

        for index, item in enumerate(cast(Any, source)):
            try:
                key, value = item
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"dictionary update sequence element #{index} has invalid length"
                ) from error
            self[key] = value


def _require_state_key(key: object) -> str:
    if type(key) is not str:
        raise _SemanticMisuse("state_record_misuse", "state keys must be exact strings")
    return key


def _update_plain_dict(target: dict[str, Any], source: Mapping[object, Any]) -> None:
    for key in source:
        checked = _require_state_key(key)
        target[checked] = source[checked]


def _capture_initial_state(initial_state: object) -> _StateCarrier:
    if not isinstance(initial_state, Mapping):
        raise OptionValidationError("initial_state must be a Mapping")
    try:
        gross_length = len(initial_state)
    except BaseException as error:
        raise _option_error("initial_state length could not be read", error)
    if gross_length > MAX_PORTABLE_COLLECTION_LENGTH:
        raise OptionValidationError("initial_state exceeds the portable limit")
    try:
        iterator = iter(initial_state)
    except BaseException as error:
        raise _option_error("initial_state keys could not be read", error)

    state = _StateCarrier()
    seen: set[str] = set()
    while True:
        try:
            key = next(iterator)
        except StopIteration:
            break
        except BaseException as error:
            raise _option_error("initial_state keys could not be read", error)
        if len(seen) >= MAX_PORTABLE_COLLECTION_LENGTH:
            raise OptionValidationError("initial_state exceeds the portable limit")
        if type(key) is not str:
            raise OptionValidationError("initial_state keys must be exact strings")
        if key in seen:
            raise OptionValidationError("initial_state contains a duplicate key")
        seen.add(key)
        try:
            value = initial_state[key]
        except BaseException as error:
            raise _option_error("initial_state value could not be read", error)
        state[key] = value
    return state


def _option_error(message: str, cause: BaseException) -> OptionValidationError:
    error = OptionValidationError(message)
    error.__cause__ = cause
    return error
