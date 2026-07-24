"""AST introspection and call graph construction for PyIntents."""

from __future__ import annotations

import ast
import builtins
import inspect
import textwrap
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from pyintents.exceptions import IntentParseError

__all__ = [
    "CallLocation",
    "CallNode",
    "CallTree",
    "SafeResolver",
    "get_calls",
    "get_function_identity",
]


FunctionDefLike = ast.FunctionDef | ast.AsyncFunctionDef


def get_function_identity(func: Callable[..., Any]) -> str:
    """Return a stable textual identity for a callable."""
    module = getattr(func, "__module__", None) or "<unknown>"
    qualname = getattr(func, "__qualname__", None)

    if not qualname:
        qualname = getattr(func, "__name__", repr(func))

    return f"{module}:{qualname}"


@dataclass(frozen=True)
class CallLocation:
    """A single call site discovered in AST."""

    target: str
    short_name: str
    lineno: int
    col_offset: int
    is_dynamic: bool = False


@dataclass
class CallNode:
    """Node in a call graph."""

    identity: str
    call_name: str
    lineno: int | None = None
    col_offset: int | None = None
    resolved_func: Callable[..., Any] | None = None
    is_local_definition: bool = False
    is_dynamic: bool = False
    is_unresolved: bool = False
    is_source_available: bool = True
    is_cycle: bool = False
    children: list[CallNode] = field(default_factory=list)

    def walk(self) -> Iterator[CallNode]:
        """Yield this node and all descendants."""
        yield self

        for child in self.children:
            yield from child.walk()


def _get_function_ast(func: Callable[..., Any]) -> FunctionDefLike:
    """Parse source code of a callable and return its AST definition."""
    func_name = getattr(
        func,
        "__qualname__",
        getattr(func, "__name__", repr(func)),
    )

    try:
        source = inspect.getsource(func)
    except (OSError, TypeError) as exc:
        raise IntentParseError(
            func_name,
            "source code is not available",
        ) from exc

    try:
        module = ast.parse(textwrap.dedent(source))
    except (SyntaxError, IndentationError) as exc:
        raise IntentParseError(
            func_name,
            f"invalid source: {exc}",
        ) from exc

    target_name = getattr(func, "__name__", None)

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_name is None or node.name == target_name:
                return node

    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_name is None or node.name == target_name:
                return node

    raise IntentParseError(
        func_name,
        "function definition was not found in source",
    )


def _format_target(node: ast.expr) -> tuple[str, bool]:
    """
    Convert AST call target to a textual representation.

    Returns:
        (target_name, is_dynamic)
    """
    if isinstance(node, ast.Name):
        return node.id, False

    if isinstance(node, ast.Attribute):
        base, dynamic = _format_target(node.value)

        if dynamic:
            return f"<dynamic>.{node.attr}", True

        return f"{base}.{node.attr}", False

    if isinstance(node, ast.Call):
        return "<call-result>", True

    if isinstance(node, ast.Subscript):
        return "<subscript>", True

    return "<dynamic>", True


class _OuterCallCollector(ast.NodeVisitor):
    """
    Collect calls from the executable body of one function.

    This collector intentionally does not descend into nested function
    bodies, lambda bodies, or method bodies. Nested function definitions
    are recorded separately so they can be analyzed only when called.
    """

    def __init__(self) -> None:
        self.calls: list[CallLocation] = []
        self.local_functions: dict[str, FunctionDefLike] = {}

    def visit_Call(self, node: ast.Call) -> None:
        target, is_dynamic = _format_target(node.func)
        short_name = target.rsplit(".", maxsplit=1)[-1]

        self.calls.append(
            CallLocation(
                target=target,
                short_name=short_name,
                lineno=node.lineno,
                col_offset=node.col_offset,
                is_dynamic=is_dynamic,
            )
        )

        # Immediately invoked lambda:
        #
        #     (lambda: foo())()
        #
        # Its body executes in the current scope, so analyze it.
        if isinstance(node.func, ast.Lambda):
            self.visit(node.func.body)

        self.generic_visit(node)

    def visit_FunctionDef(self, node: FunctionDefLike) -> None:
        # Directly nested function definition.
        # Record it, but do not analyze its body as part of outer function.
        self.local_functions[node.name] = node
        self._visit_function_definition_creation(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Lambda body is executed when called, not when defined.
        # Immediate lambda calls are handled in visit_Call.
        self._visit_arguments(node.args)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Class body executes at definition time.
        # We visit class-level expressions, but skip method bodies.
        for decorator in node.decorator_list:
            self.visit(decorator)

        for base in node.bases:
            self.visit(base)

        for keyword in node.keywords:
            self.visit(keyword.value)

        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function_definition_creation(statement)
            elif isinstance(statement, ast.ClassDef):
                self.visit(statement)
            else:
                self.visit(statement)

    def _visit_function_definition_creation(
        self,
        node: FunctionDefLike,
    ) -> None:
        # Decorators and default arguments are evaluated when the function
        # object is created, so they belong to the enclosing execution scope.
        for decorator in node.decorator_list:
            self.visit(decorator)

        self._visit_arguments(node.args)

    def _visit_arguments(self, args: ast.arguments) -> None:
        all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]

        for arg in all_args:
            if arg.annotation is not None:
                self.visit(arg.annotation)

        if args.vararg is not None and args.vararg.annotation is not None:
            self.visit(args.vararg.annotation)

        if args.kwarg is not None and args.kwarg.annotation is not None:
            self.visit(args.kwarg.annotation)

        for default in args.defaults:
            self.visit(default)

        for default in args.kw_defaults:
            if default is not None:
                self.visit(default)


def extract_calls_from_function_def(
    func_def: FunctionDefLike,
) -> tuple[list[CallLocation], dict[str, FunctionDefLike]]:
    """Extract call sites and local function definitions from AST."""
    collector = _OuterCallCollector()

    for statement in func_def.body:
        collector.visit(statement)

    return collector.calls, collector.local_functions


def get_calls(func: Callable[..., Any]) -> list[str]:
    """
    Compatibility helper.

    Returns call target names from the outer function body.
    Raises IntentParseError when source is unavailable or invalid.
    """
    func_def = _get_function_ast(func)
    calls, _ = extract_calls_from_function_def(func_def)
    return [call.target for call in calls]


class SafeResolver:
    """
    Resolve dotted names without executing arbitrary descriptors.

    This resolver intentionally avoids:
    - inspect.stack()
    - getattr() on arbitrary instances
    - resolution through mutable local variables
    """

    def resolve(
        self,
        name: str,
        parent_func: Callable[..., Any] | None,
    ) -> Callable[..., Any] | None:
        if parent_func is None:
            return None

        if not name or name.startswith("<"):
            return None

        parts = name.split(".")

        try:
            parent_globals = parent_func.__globals__
        except AttributeError:
            return None

        obj = parent_globals.get(parts[0])

        if obj is None:
            obj = getattr(builtins, parts[0], None)

        if obj is None:
            return None

        for part in parts[1:]:
            # Follow only modules and classes.
            # This avoids triggering instance properties/descriptors.
            if not isinstance(obj, (types.ModuleType, type)):
                return None

            obj = inspect.getattr_static(obj, part, None)

            if obj is None:
                return None

        return obj if callable(obj) else None


class CallTree:
    """
    Build a call graph for a function.

    Root function must have source code available.
    Child functions without source are represented as opaque nodes.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        max_depth: int | float = 1,
        resolver: SafeResolver | None = None,
    ) -> None:
        self.max_depth: int | float = max(0, max_depth)
        self.resolver = resolver or SafeResolver()
        self.root = self._build_from_callable(
            func=func,
            depth=0,
            stack=frozenset(),
            require_source=True,
        )

    def has_call(self, name: str) -> bool:
        """Check whether call graph contains exact call name or identity."""
        return any(
            name == node.call_name or name == node.identity for node in self.root.walk()
        )

    def find_calls(self, name: str) -> list[CallNode]:
        """Find nodes by exact call name or identity."""
        return [
            node
            for node in self.root.walk()
            if name == node.call_name or name == node.identity
        ]

    def _build_from_callable(
        self,
        func: Callable[..., Any],
        depth: int,
        stack: frozenset[str],
        require_source: bool,
    ) -> CallNode:
        identity = get_function_identity(func)
        call_name = getattr(
            func,
            "__qualname__",
            getattr(func, "__name__", identity),
        )

        node = CallNode(
            identity=identity,
            call_name=call_name,
            resolved_func=func,
        )

        if identity in stack:
            node.is_cycle = True
            return node

        if depth >= self.max_depth:
            return node

        try:
            func_def = _get_function_ast(func)
        except IntentParseError:
            if require_source:
                raise

            node.is_source_available = False
            return node

        node.is_source_available = True

        return self._expand_node(
            node=node,
            func_def=func_def,
            depth=depth,
            stack=stack,
            parent_func=func,
            local_defs={},
        )

    def _build_from_ast(
        self,
        func_def: FunctionDefLike,
        name: str,
        depth: int,
        stack: frozenset[str],
        parent_func: Callable[..., Any] | None,
        local_defs: dict[str, FunctionDefLike],
        owner_identity: str,
    ) -> CallNode:
        identity = f"local:{owner_identity}:{name}"

        node = CallNode(
            identity=identity,
            call_name=name,
            lineno=func_def.lineno,
            col_offset=func_def.col_offset,
            is_local_definition=True,
            is_source_available=True,
        )

        if identity in stack:
            node.is_cycle = True
            return node

        if depth >= self.max_depth:
            return node

        return self._expand_node(
            node=node,
            func_def=func_def,
            depth=depth,
            stack=stack,
            parent_func=parent_func,
            local_defs=local_defs,
        )

    def _expand_node(
        self,
        node: CallNode,
        func_def: FunctionDefLike,
        depth: int,
        stack: frozenset[str],
        parent_func: Callable[..., Any] | None,
        local_defs: dict[str, FunctionDefLike],
    ) -> CallNode:
        calls, own_locals = extract_calls_from_function_def(func_def)
        merged_locals = {**local_defs, **own_locals}
        child_stack = stack | {node.identity}

        for call in calls:
            child = self._build_child(
                call=call,
                parent_func=parent_func,
                local_defs=merged_locals,
                depth=depth + 1,
                stack=child_stack,
                owner_identity=node.identity,
            )
            node.children.append(child)

        return node

    def _build_child(
        self,
        call: CallLocation,
        parent_func: Callable[..., Any] | None,
        local_defs: dict[str, FunctionDefLike],
        depth: int,
        stack: frozenset[str],
        owner_identity: str,
    ) -> CallNode:
        local_def: FunctionDefLike | None = None

        if not call.is_dynamic and "." not in call.target:
            local_def = local_defs.get(call.target)

        if local_def is not None:
            child = self._build_from_ast(
                func_def=local_def,
                name=call.target,
                depth=depth,
                stack=stack,
                parent_func=parent_func,
                local_defs=local_defs,
                owner_identity=owner_identity,
            )
        else:
            resolved = (
                None
                if call.is_dynamic
                else self.resolver.resolve(call.target, parent_func)
            )

            if resolved is not None:
                child = self._build_from_callable(
                    func=resolved,
                    depth=depth,
                    stack=stack,
                    require_source=False,
                )
            else:
                child = CallNode(
                    identity=f"unresolved:{call.target}",
                    call_name=call.target,
                    is_unresolved=True,
                    is_dynamic=call.is_dynamic,
                    is_source_available=False,
                )

        child.call_name = call.target
        child.lineno = call.lineno
        child.col_offset = call.col_offset

        if call.is_dynamic:
            child.is_dynamic = True

        return child
