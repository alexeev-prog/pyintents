"""Explicit capability dispatch for a trusted application or IPC broker.

This module does not execute, load, or sandbox untrusted Python. Keep the
dispatcher and its grants on the trusted side of the process boundary.
"""

from __future__ import annotations

import inspect
import math
import re
import types
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pyintents.exceptions import IntentConfigurationError, IntentViolationError

__all__ = ["Capability", "IntentDispatcher"]


def _capability_name(name: str) -> str:
    if (
        type(name) is not str
        or re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,127}", name) is None
    ):
        raise IntentConfigurationError(
            "Capability ID must be an ASCII identifier of 1–128 characters"
        )
    return name


def _trusted_function(func: Any) -> bool:
    return type(func) in (types.FunctionType, types.BuiltinFunctionType)


@dataclass(frozen=True)
class Capability:
    """Trusted synchronous handler and a mandatory resource/argument validator.

    The validator must return exactly True to authorize a payload. Validators
    must be pure: authorization is completed before the handler is invoked.
    """

    handler: Callable[[dict[str, Any]], Any]
    validate: Callable[[dict[str, Any]], bool]

    def __post_init__(self) -> None:
        for func in (self.handler, self.validate):
            if not _trusted_function(func):
                raise IntentConfigurationError(
                    "Capability handlers and validators must be functions"
                )
            if (
                inspect.iscoroutinefunction(func)
                or inspect.isgeneratorfunction(func)
                or inspect.isasyncgenfunction(func)
            ):
                raise IntentConfigurationError(
                    "Capabilities require synchronous, non-generator functions"
                )


class IntentDispatcher:
    """A fixed registry with fixed, trusted grants and bounded JSON-like data.

    Construct one dispatcher per trusted authorization context. Never derive
    grants from an unauthenticated request. Registry entries and grants cannot
    be extended through dispatch(). Resource limits cover data traversal, not
    handler runtime, memory allocation by the transport, or external effects.
    """

    def __init__(
        self,
        capabilities: Mapping[str, Capability],
        *,
        grants: Iterable[str],
        deny: Iterable[str] = (),
        max_nodes: int = 10_000,
        max_depth: int = 32,
        max_bytes: int = 1_000_000,
    ) -> None:
        for name, value in (
            ("max_nodes", max_nodes),
            ("max_depth", max_depth),
            ("max_bytes", max_bytes),
        ):
            if type(value) is not int or value < 1:
                raise IntentConfigurationError(f"{name} must be a positive integer")
        if max_depth > 128:
            raise IntentConfigurationError("max_depth cannot exceed 128")
        registry = {}
        for name, capability in capabilities.items():
            _capability_name(name)
            if type(capability) is not Capability:
                raise IntentConfigurationError(
                    "Registry values must be Capability instances"
                )
            registry[name] = capability
        if isinstance(grants, str) or isinstance(deny, str):
            raise IntentConfigurationError(
                "grants and deny must be collections of IDs, not strings"
            )
        allowed = frozenset(_capability_name(name) for name in grants)
        denied = frozenset(_capability_name(name) for name in deny)
        if not (allowed | denied) <= registry.keys():
            raise IntentConfigurationError(
                "All grants and deny entries must be registered"
            )
        self._registry = MappingProxyType(registry)
        self._grants = allowed - denied
        self._max_nodes = max_nodes
        self._max_depth = max_depth
        self._max_bytes = max_bytes

    def _reject(self, name: str, reason: str) -> None:
        raise IntentViolationError("dispatch", f"{name}: {reason}")

    def _copy_data(self, value: Any, name: str) -> Any:
        nodes = 0
        size = 0

        def copy(item: Any, depth: int) -> Any:
            nonlocal nodes, size
            nodes += 1
            if nodes > self._max_nodes or depth > self._max_depth:
                self._reject(name, "data exceeds traversal budget")
            kind = type(item)
            if item is None or kind is bool:
                return item
            if kind is int:
                if item.bit_length() > 4096:
                    self._reject(name, "integer exceeds 4096 bits")
                return item
            if kind is float:
                if not math.isfinite(item):
                    self._reject(name, "non-finite numbers are not supported")
                return item
            if kind is str:
                # Conservative UTF-8 upper bound, including unpaired surrogates.
                size += len(item) * 4
                if size > self._max_bytes:
                    self._reject(name, "strings exceed byte budget")
                return item
            if kind is list:
                if len(item) > self._max_nodes - nodes:
                    self._reject(name, "list exceeds node budget")
                return [copy(child, depth + 1) for child in item]
            if kind is dict:
                if len(item) * 2 > self._max_nodes - nodes:
                    self._reject(name, "object exceeds node budget")
                result = {}
                for key, child in item.items():
                    if type(key) is not str:
                        self._reject(name, "object keys must be strings")
                    result[copy(key, depth + 1)] = copy(child, depth + 1)
                return result
            self._reject(name, "only plain JSON-like data is supported")

        return copy(value, 0)

    def dispatch(self, name: str, payload: dict[str, Any]) -> Any:
        """Authorize, copy, validate, invoke once, and copy the result.

        Handler exceptions propagate. There is no retry, rollback, or ACID
        guarantee; a rejected result does not undo a completed handler effect.
        """
        if type(name) is not str:
            self._reject("<invalid>", "capability ID must be a string")
        if not 1 <= len(name) <= 128:
            self._reject("<invalid>", "capability ID exceeds length limit")
        if name not in self._grants:
            self._reject("<capability>", "capability is not granted")
        if type(payload) is not dict:
            self._reject(name, "payload must be a plain object")
        capability = self._registry[name]
        arguments = self._copy_data(payload, name)
        # The validator receives its own copy, so mutation cannot rewrite the
        # authorized handler payload. Both functions are trusted application code.
        if capability.validate(self._copy_data(arguments, name)) is not True:
            self._reject(name, "argument validation failed")
        result = capability.handler(arguments)
        return self._copy_data(result, name)
