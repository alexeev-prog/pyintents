# namespace.py
from functools import wraps
from typing import Callable, Optional

from pyintents.exceptions import IntentParseError, IntentViolationError
from pyintents.introspect import CallNode, CallTree


class IntentNamespace:
    def __init__(
        self,
        uses: Optional[list[Callable]] = None,
        recursive: bool = False,
        without: Optional[list[Callable]] = None,
        uselocals: bool = False,
        deny: Optional[list[Callable]] = None,
    ) -> None:
        self._uses = self._map_functions(uses or [])
        self._recursive = recursive
        self._without = self._map_functions(without or [])
        self._uselocals = uselocals
        self._deny = self._map_functions(deny or [])
        self._ignored_names: set[str] = {
            name
            for name in dir(IntentNamespace)
            if callable(getattr(IntentNamespace, name)) and not name.startswith("_")
        }

    @staticmethod
    def _map_functions(functions: list[Callable]) -> dict[str, Callable]:
        return {func.__name__: func for func in functions}

    def intent(
        self,
        uses: Optional[list[Callable]] = None,
        recursive: Optional[bool] = None,
        without: Optional[list[Callable]] = None,
        uselocals: Optional[bool] = None,
        deny: Optional[list[Callable]] = None,
    ) -> Callable:
        merged_uses = self._uses | self._map_functions(uses or [])
        merged_without = self._without | self._map_functions(without or [])
        merged_deny = self._deny | self._map_functions(deny or [])
        use_locals = uselocals if uselocals is not None else self._uselocals
        max_depth = (
            float("inf")
            if (recursive if recursive is not None else self._recursive)
            else 1
        )

        allowed_names = self._build_allowed_names(merged_uses, merged_deny)
        denied_names = set(merged_deny.keys())
        without_names = set(merged_without.keys())

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    tree = CallTree(func, max_depth=max_depth)
                    self._validate_tree(
                        tree.root,
                        allowed_names,
                        denied_names,
                        without_names,
                        use_locals,
                        func,
                    )
                except (SyntaxError, IndentationError) as e:
                    raise IntentParseError(func.__name__, f"cannot parse: {e}")
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def _build_allowed_names(
        self, uses: dict[str, Callable], deny: dict[str, Callable]
    ) -> set[str]:
        allowed = set(uses.keys())
        denied_names = set(deny.keys())
        return allowed - denied_names

    def _is_ignored_method(self, name: str) -> bool:
        short_name = name.split(".")[-1]
        return short_name in self._ignored_names

    def _validate_tree(
        self,
        node: CallNode,
        allowed_names: set[str],
        denied_names: set[str],
        without_names: set[str],
        use_locals: bool,
        root_func: Callable,
        depth: int = 0,
    ) -> None:
        if depth > 0:
            if self._is_ignored_method(node.name):
                return

            short_name = node.name.split(".")[-1]

            if self._is_denied(node, denied_names):
                parent_name = node.parent.name if node.parent else "unknown"
                raise IntentViolationError(
                    func_name=parent_name,
                    violation=node.name,
                )

            if short_name in without_names or node.name in without_names:
                return

            if not self._is_call_allowed(node, allowed_names, use_locals):
                parent_name = node.parent.name if node.parent else "unknown"
                raise IntentViolationError(
                    func_name=parent_name,
                    violation=node.name,
                )

        for child in node.calls:
            self._validate_tree(
                child,
                allowed_names,
                denied_names,
                without_names,
                use_locals,
                root_func,
                depth + 1,
            )

    def _is_denied(self, node: CallNode, denied_names: set[str]) -> bool:
        short_name = node.name.split(".")[-1]
        if short_name in denied_names:
            return True
        if node.name in denied_names:
            return True
        if node.resolved_func is not None:
            func_name = getattr(node.resolved_func, "__name__", "")
            if func_name in denied_names:
                return True
        return False

    def _is_call_allowed(
        self, node: CallNode, allowed_names: set[str], use_locals: bool
    ) -> bool:
        if use_locals and node.is_local:
            return True

        short_name = node.name.split(".")[-1]
        if short_name in allowed_names:
            return True
        if node.name in allowed_names:
            return True
        if node.resolved_func is not None:
            func_name = getattr(node.resolved_func, "__name__", "")
            if func_name in allowed_names:
                return True
        return False

    def _is_local_to_root(self, name: str, root_func: Callable) -> bool:
        short_name = name.split(".")[-1]
        try:
            root_globals = root_func.__globals__
            return short_name in root_globals
        except AttributeError:
            return False
