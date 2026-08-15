"""PyIntents exceptions."""

from __future__ import annotations

__all__ = [
    "IntentError",
    "IntentViolationError",
    "IntentParseError",
    "IntentConfigurationError",
]


class IntentError(Exception):
    """Base class for all PyIntents errors."""


class IntentShadowingError(IntentError):
    """Raised when a protected name is shadowed in the local scope."""

    def __init__(self, desc: str) -> None:
        super().__init__(f"Protected name shadowing error: {desc}")


class IntentViolationError(IntentError):
    """Raised when a function violates declared capabilities."""

    def __init__(
        self,
        func_name: str,
        violation: str,
        *,
        path: tuple[str, ...] = (),
    ) -> None:
        self.func_name = func_name
        self.violation = violation
        self.path = tuple(path)

        if self.path:
            where = " -> ".join((*self.path, func_name))
        else:
            where = func_name

        super().__init__(f"Function '{where}' calls forbidden '{violation}'")


class IntentParseError(IntentError):
    """Raised when function source cannot be parsed or is unavailable."""

    def __init__(self, func_name: str, message: str) -> None:
        self.func_name = func_name
        self.message = message
        super().__init__(f"Function '{func_name}' cannot be parsed: {message}")


class IntentConfigurationError(IntentError):
    """Raised when namespace or decorator configuration is invalid."""
