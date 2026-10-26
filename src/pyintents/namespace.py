"""Policy engine for PyIntents."""

from __future__ import annotations

import builtins
import inspect
import types
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeAlias, cast

from pyintents.exceptions import (
    IntentConfigurationError,
    IntentViolationError,
)
from pyintents.introspect import (
    CallNode,
    CallTree,
    get_function_identity,
)

__all__ = [
    "IntentNamespace",
]


Rule: TypeAlias = Callable[..., Any] | str


DEFAULT_DENIED_DYNAMIC_PRIMITIVES: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "breakpoint",
    }
)


@dataclass(frozen=True)
class RuleSet:
    """Normalized permission or denial rules."""

    objects: frozenset[Callable[..., Any]] = frozenset()
    identities: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    short_names: frozenset[str] = frozenset()

    def union(self, other: RuleSet) -> RuleSet:
        return RuleSet(
            objects=self.objects | other.objects,
            identities=self.identities | other.identities,
            names=self.names | other.names,
            short_names=self.short_names | other.short_names,
        )

    def matches(self, node: CallNode, *, unresolved: bool = False) -> bool:
        if node.resolved_func is not None:
            if any(node.resolved_func is obj for obj in self.objects):
                return True

            if get_function_identity(node.resolved_func) in self.identities:
                return True

        if (node.is_unresolved or node.is_dynamic) and not unresolved:
            return False

        if node.identity in self.identities:
            return True

        if node.call_name in self.names:
            return True

        short_name = node.call_name.rsplit(".", maxsplit=1)[-1]
        return short_name in self.short_names


def _normalize_rules(
    rules: Iterable[Rule],
    *,
    include_short_names: bool,
) -> RuleSet:
    objects: set[Callable[..., Any]] = set()
    identities: set[str] = set()
    names: set[str] = set()
    short_names: set[str] = set()

    for rule in rules:
        if type(rule) is str:
            rule_text = rule.strip()

            if not rule_text:
                raise IntentConfigurationError("String rule cannot be empty")

            if ":" in rule_text:
                # Identity-like rule:
                #
                #     module:qualname
                identities.add(rule_text)
                qualname = rule_text.rsplit(":", maxsplit=1)[-1]

                if include_short_names:
                    names.add(qualname)
                    short_names.add(qualname.rsplit(".", maxsplit=1)[-1])
            else:
                # Dotted or bare name rule:
                #
                #     os.system
                #     print
                names.add(rule_text)

                if "." in rule_text:
                    module, _, qualname = rule_text.rpartition(".")
                    identities.add(f"{module}:{qualname}")

                if include_short_names or "." not in rule_text:
                    short_names.add(rule_text.rsplit(".", maxsplit=1)[-1])

            continue

        if type(rule) not in (
            types.FunctionType,
            types.BuiltinFunctionType,
            types.MethodType,
        ):
            raise IntentConfigurationError(
                "Rule must be a callable or a string; callable instances are unsupported"
            )

        objects.add(cast(Callable[..., Any], rule))

        # An object rule means precisely this object, never a metadata fallback.

    return RuleSet(
        objects=frozenset(objects),
        identities=frozenset(identities),
        names=frozenset(names),
        short_names=frozenset(short_names),
    )


def _validate_settings(
    *,
    recursive: bool,
    usemodule: bool,
) -> None:
    if usemodule and not recursive:
        raise IntentConfigurationError("usemodule requires recursive=True")


@dataclass(frozen=True)
class _EffectivePolicy:
    uses: RuleSet
    deny: RuleSet
    without: RuleSet
    recursive: bool
    uselocals: bool
    usemodule: bool
    allow_unknown: bool


class IntentNamespace:
    """
    Declarative capability policy for Python functions.

    Security defaults:
    - recursive=True
    - allow_unknown=False
    - deny_dynamic_primitives=True

    usemodule:
        Allows functions defined in the same module as the decorated
        function. Works only with recursive=True.
    """

    def __init__(
        self,
        uses: Iterable[Rule] | None = None,
        *,
        recursive: bool = True,
        without: Iterable[Rule] | None = None,
        uselocals: bool = False,
        usemodule: bool = False,
        deny: Iterable[Rule] | None = None,
        allow_unknown: bool = False,
        deny_dynamic_primitives: bool = True,
        only_warnings: bool = False,
        strict: bool = True,
        max_nodes: int = 10_000,
        analysis_depth: int = 100,
    ) -> None:
        for name, value in (
            ("max_nodes", max_nodes),
            ("analysis_depth", analysis_depth),
        ):
            if type(value) is not int or value < 1:
                raise IntentConfigurationError(f"{name} must be a positive integer")
        _validate_settings(
            recursive=recursive,
            usemodule=usemodule,
        )

        self._uses = _normalize_rules(
            uses or [],
            include_short_names=False,
        )
        self._without = _normalize_rules(
            without or [],
            include_short_names=False,
        )
        self._deny = _normalize_rules(
            deny or [],
            include_short_names=True,
        )

        if deny_dynamic_primitives:
            self._deny = self._deny.union(
                _normalize_rules(
                    [
                        *DEFAULT_DENIED_DYNAMIC_PRIMITIVES,
                        *(
                            getattr(builtins, name)
                            for name in DEFAULT_DENIED_DYNAMIC_PRIMITIVES
                        ),
                    ],
                    include_short_names=True,
                )
            )

        self._recursive = recursive
        self._uselocals = uselocals
        self._usemodule = usemodule
        self._allow_unknown = allow_unknown
        self._only_warnings = only_warnings
        self._strict = strict
        self._max_nodes = max_nodes
        self._analysis_depth = analysis_depth

    def intent(
        self,
        uses: Iterable[Rule] | None = None,
        *,
        recursive: bool | None = None,
        without: Iterable[Rule] | None = None,
        uselocals: bool | None = None,
        usemodule: bool | None = None,
        deny: Iterable[Rule] | None = None,
        allow_unknown: bool | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        effective_recursive = self._recursive if recursive is None else recursive
        effective_uselocals = self._uselocals if uselocals is None else uselocals
        effective_usemodule = self._usemodule if usemodule is None else usemodule
        effective_allow_unknown = (
            self._allow_unknown if allow_unknown is None else allow_unknown
        )

        _validate_settings(
            recursive=effective_recursive,
            usemodule=effective_usemodule,
        )

        merged_uses = self._uses.union(
            _normalize_rules(
                uses or [],
                include_short_names=False,
            )
        )
        merged_without = self._without.union(
            _normalize_rules(
                without or [],
                include_short_names=False,
            )
        )
        merged_deny = self._deny.union(
            _normalize_rules(
                deny or [],
                include_short_names=True,
            )
        )

        max_depth: int | float = float("inf") if effective_recursive else 1

        policy = _EffectivePolicy(
            uses=merged_uses,
            deny=merged_deny,
            without=merged_without,
            recursive=effective_recursive,
            uselocals=effective_uselocals,
            usemodule=effective_usemodule,
            allow_unknown=effective_allow_unknown,
        )

        def decorator(
            func: Callable[..., Any],
        ) -> Callable[..., Any]:
            if type(func) is not types.FunctionType:
                raise IntentConfigurationError("intent requires a Python function")
            if inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func):
                raise IntentConfigurationError("generator functions are not supported")

            def validate() -> None:
                protected_names: set[str] = set(
                    merged_uses.names | merged_uses.short_names
                )

                tree = CallTree(
                    func,
                    max_depth=max_depth,
                    protected_names=protected_names,
                    strict=self._strict,
                    max_nodes=self._max_nodes,
                    analysis_depth=self._analysis_depth,
                )
                root_module = getattr(func, "__module__", None)

                self._validate_tree(
                    tree.root,
                    policy,
                    root_module=root_module,
                )

            if inspect.iscoroutinefunction(func):

                @wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    validate()
                    return await func(*args, **kwargs)

                return async_wrapper

            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                validate()
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def _violation(self, node: CallNode, path: tuple[str, ...]) -> None:
        error = IntentViolationError(
            func_name=path[-1],
            violation=f"{node.call_name} (identity: {node.identity})",
            path=path[:-1],
        )
        if self._only_warnings:
            warnings.warn(f"Intent violation: {error}", stacklevel=3)
        else:
            raise error

    def _validate_tree(
        self,
        root: CallNode,
        policy: _EffectivePolicy,
        *,
        root_module: str | None = None,
    ) -> None:
        stack: list[tuple[CallNode, tuple[str, ...]]] = [(root, ())]

        while stack:
            node, path = stack.pop()

            if path:
                if policy.deny.matches(node, unresolved=True):
                    self._violation(node, path)

                elif not policy.without.matches(node):
                    if not self._is_allowed(
                        node,
                        policy,
                        root_module=root_module,
                    ):
                        self._violation(node, path)

            for child in reversed(node.children):
                stack.append((child, (*path, node.call_name)))

    @staticmethod
    def _is_allowed(
        node: CallNode,
        policy: _EffectivePolicy,
        *,
        root_module: str | None = None,
    ) -> bool:
        if policy.uses.matches(node):
            return True

        if node.is_local_definition and policy.uselocals:
            return True

        if (
            policy.usemodule
            and root_module
            and root_module != "builtins"
            and node.resolved_func is not None
            and node.is_source_available
        ):
            child_module = getattr(
                node.resolved_func,
                "__module__",
                None,
            )

            if child_module == root_module:
                return True

        if node.is_unresolved or node.is_dynamic or not node.is_source_available:
            return policy.allow_unknown

        return False
