# introspect.py
import ast
import builtins
import inspect
from dataclasses import dataclass, field
from typing import Callable, Optional


def get_calls(func: Callable) -> list[str]:
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return []

    try:
        tree = ast.parse(source)
    except (SyntaxError, IndentationError):
        return []

    calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func_node = node.func
        while isinstance(func_node, ast.Call):
            func_node = func_node.func

        if isinstance(func_node, ast.Name):
            calls.append(func_node.id)
        elif isinstance(func_node, ast.Attribute):
            parts = []
            current = func_node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value  # type: ignore
            if isinstance(current, ast.Name):
                parts.append(current.id)
            calls.append(".".join(reversed(parts)))

    return calls


@dataclass
class CallNode:
    name: str
    calls: list["CallNode"] = field(default_factory=list)
    parent: Optional["CallNode"] = None
    source: Optional[str] = None
    resolved_func: Optional[Callable] = None
    is_local: bool = False

    def __repr__(self, level: int = 0) -> str:
        indent = "  " * level
        result = f"{indent}└─ {self.name}\n"
        for child in self.calls:
            result += child.__repr__(level + 1)
        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CallNode):
            return False
        return self.name == other.name and self.parent == other.parent


class CallTree:
    def __init__(self, func: Callable, max_depth: int = 1):
        self.max_depth: int = max(0, max_depth)
        self._visited: dict[str, CallNode] = {}
        self._call_stack: set[str] = set()
        self.root = self._build_node(func, current_depth=0, parent=None)

    def _build_node(
        self, func: Callable, current_depth: int, parent: Optional[CallNode]
    ) -> CallNode:
        name = getattr(func, "__qualname__", getattr(func, "__name__", str(func)))

        if name in self._call_stack:
            return CallNode(name=name, parent=parent, resolved_func=func)

        if name in self._visited:
            return self._visited[name]

        node = CallNode(name=name, parent=parent, resolved_func=func)

        try:
            node.source = inspect.getsource(func)
        except (OSError, TypeError):
            pass

        self._visited[name] = node
        self._call_stack.add(name)

        if current_depth >= self.max_depth:
            self._call_stack.remove(name)
            return node

        called_names = get_calls(func)

        for called_name in called_names:
            child_func = self._resolve_function(called_name, func)
            if child_func:
                child_node = self._build_node(child_func, current_depth + 1, node)
                if "." in called_name:
                    child_node.name = called_name
                child_node.is_local = self._is_local_function(called_name, func)
                node.calls.append(child_node)
            else:
                child_node = CallNode(name=called_name, parent=node)
                child_node.is_local = self._is_local_function(called_name, func)
                node.calls.append(child_node)

        self._call_stack.remove(name)
        return node

    def _resolve_function(self, name: str, parent_func: Callable) -> Optional[Callable]:
        try:
            parent_globals = parent_func.__globals__
        except AttributeError:
            return None

        parts = name.split(".")
        obj = parent_globals.get(parts[0])

        if obj is None:
            obj = getattr(builtins, parts[0], None)

        if obj is None:
            for frame in inspect.stack():
                if frame.function == "<module>":
                    obj = frame.frame.f_globals.get(parts[0])
                    if obj is not None:
                        break

        if obj is None:
            return None

        for part in parts[1:]:
            if obj is None:
                return None
            obj = getattr(obj, part, None)

        return obj if callable(obj) else None

    def _is_local_function(self, name: str, parent_func: Callable) -> bool:
        try:
            parent_globals = parent_func.__globals__
            return name in parent_globals and callable(parent_globals.get(name))
        except AttributeError:
            return False

    def has_call(self, func_name: str) -> bool:
        return self._search_call(self.root, func_name)

    def _search_call(self, node: CallNode, func_name: str) -> bool:
        if node.name == func_name or func_name in node.name:
            return True
        return any(self._search_call(child, func_name) for child in node.calls)

    def find_calls(self, func_name: str) -> list[CallNode]:
        result: list[CallNode] = []
        self._find_calls_recursive(self.root, func_name, result)
        return result

    def _find_calls_recursive(
        self, node: CallNode, func_name: str, result: list[CallNode]
    ) -> None:
        if func_name in node.name:
            result.append(node)
        for child in node.calls:
            self._find_calls_recursive(child, func_name, result)
