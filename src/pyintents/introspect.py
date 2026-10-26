"""AST introspection and call graph construction for PyIntents."""

from __future__ import annotations

import ast
import inspect
import textwrap
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from pyintents.exceptions import IntentParseError, IntentShadowingError

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
    """Return a diagnostic name, never a security identity.

    Do not inspect arbitrary callable instances: even repr/getattr can execute
    application code. Callable objects are deliberately opaque to the analyzer.
    """
    if type(func) not in (
        types.FunctionType,
        types.BuiltinFunctionType,
        types.MethodType,
    ):
        return "<unknown>:<callable>"
    module = func.__module__ or "<unknown>"
    qualname = func.__qualname__ or func.__name__ or "<callable>"
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
    func_name = get_function_identity(func)
    if type(func) is types.MethodType:
        func = func.__func__
    if type(func) is not types.FunctionType:
        raise IntentParseError(
            func_name, "source code is not available for this callable"
        )

    try:
        # inspect.getsource(func) follows __wrapped__, potentially inspecting an
        # entirely different function. A code object has no such indirection.
        source = inspect.getsource(func.__code__)
    except (OSError, TypeError) as exc:
        raise IntentParseError(
            func_name,
            "source code is not available",
        ) from exc

    if len(source) > 1_000_000:
        raise IntentParseError(func_name, "source exceeds analysis budget")

    try:
        module = ast.parse(textwrap.dedent(source))
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise IntentParseError(
            func_name,
            f"invalid source: {exc}",
        ) from exc

    target_name = func.__code__.co_name

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_name is None or node.name == target_name:
                return node

    for node in ast.walk(module):  # type: ignore
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_name is None or node.name == target_name:
                return node

    raise IntentParseError(
        func_name,
        "function definition was not found in source",
    )


class _ScopeBindings(ast.NodeVisitor):
    """Collect bindings in one lexical scope, including all Store contexts."""

    def __init__(self, func_def: FunctionDefLike) -> None:
        self.counts: dict[str, int] = {}
        self.globals: set[str] = set()
        args = func_def.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            self.bind(arg.arg)
        for optional_arg in (args.vararg, args.kwarg):
            if optional_arg is not None:
                self.bind(optional_arg.arg)
        for statement in func_def.body:
            self.visit(statement)

    def bind(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bind(node.id)

    def visit_FunctionDef(self, node: FunctionDefLike) -> None:
        self.bind(node.name)
        # Defaults and decorators execute in the enclosing scope.
        for expr in [*node.decorator_list, *node.args.defaults]:
            self.visit(expr)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bind(node.name)
        for expr in [*node.decorator_list, *node.bases]:
            self.visit(expr)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for expr in node.args.defaults:
            self.visit(expr)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bind(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bind(alias.asname or alias.name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.bind(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.bind(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.bind(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.bind(node.rest)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        # Never resolve a nonlocal binding as a global.
        for name in node.names:
            self.bind(name)


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
    def __init__(self, protected_names: set[str] | None = None) -> None:
        self.calls: list[CallLocation] = []
        self.local_functions: dict[str, FunctionDefLike] = {}
        self.protected_names: set[str] = protected_names or set()

    def _check_shadowing(self, node: ast.AST) -> None:
        protected_short_names = {p.rsplit(".", 1)[-1] for p in self.protected_names}

        if isinstance(node, ast.Name):
            if node.id in protected_short_names:
                conflicts = [
                    p for p in self.protected_names if p.rsplit(".", 1)[-1] == node.id
                ]
                raise IntentShadowingError(
                    f"Assignment to '{node.id}' is forbidden. It shadows: {', '.join(conflicts)}"
                )

    def visit_Import(self, node: ast.Import):
        protected_short_names = {p.rsplit(".", 1)[-1] for p in self.protected_names}
        for alias in node.names:
            name = alias.asname or alias.name
            if name in protected_short_names:
                conflicts = [
                    p for p in self.protected_names if p.rsplit(".", 1)[-1] == name
                ]
                raise IntentShadowingError(
                    f"Forbidden import: '{alias.name}' imported as '{name}' "
                    f"shadows protected name(s): {', '.join(conflicts)}"
                )

    def visit_ImportFrom(self, node: ast.ImportFrom):
        protected_short_names = {p.rsplit(".", 1)[-1] for p in self.protected_names}
        for alias in node.names:
            name = alias.asname or alias.name
            if name in protected_short_names:
                conflicts = [
                    p for p in self.protected_names if p.rsplit(".", 1)[-1] == name
                ]
                source = f"{node.module}." if node.module else ""
                raise IntentShadowingError(
                    f"Forbidden import: '{source}{alias.name}' imported as '{name}' "
                    f"shadows protected name(s): {', '.join(conflicts)}"
                )

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._check_shadowing(target)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    self._check_shadowing(elt)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_shadowing(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_shadowing(node.target)
        self.generic_visit(node)

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

        if isinstance(node.func, ast.Lambda):
            self.visit(node.func.body)

        self.generic_visit(node)

    def _visit_decorators(self, decorators: list[ast.expr]) -> None:
        for decorator in decorators:
            # @decorator is a call too; @factory() additionally calls its result.
            target, dynamic = _format_target(decorator)
            self.calls.append(
                CallLocation(
                    target,
                    target.rsplit(".", 1)[-1],
                    decorator.lineno,
                    decorator.col_offset,
                    dynamic,
                )
            )
            self.visit(decorator)

    def visit_FunctionDef(self, node: FunctionDefLike) -> None:
        self.local_functions[node.name] = node
        self._visit_function_definition_creation(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_arguments(node.args)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_decorators(node.decorator_list)

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
        self._visit_decorators(node.decorator_list)

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

        for default in args.kw_defaults:  # type: ignore
            if default is not None:
                self.visit(default)


def extract_calls_from_function_def(
    func_def: FunctionDefLike,
    protected_names: set[str] | None = None,
) -> tuple[list[CallLocation], dict[str, FunctionDefLike]]:
    collector = _OuterCallCollector(protected_names=protected_names or set())

    for statement in func_def.body:
        collector.visit(statement)

    return collector.calls, collector.local_functions


def get_calls(
    func: Callable[..., Any], protected_names: set[str] | None = None
) -> list[str]:
    """
    Compatibility helper.

    Returns call target names from the outer function body.
    Raises IntentParseError when source is unavailable or invalid.
    """
    func_def = _get_function_ast(func)
    calls, _ = extract_calls_from_function_def(
        func_def, protected_names=protected_names
    )
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

        if type(parent_func) is not types.FunctionType:
            return None
        parent_globals = parent_func.__globals__

        sentinel = object()
        obj = parent_globals.get(parts[0], sentinel)
        if obj is sentinel:
            obj = parent_func.__builtins__.get(parts[0])

        if obj is None:
            return None

        for part in parts[1:]:
            if type(obj) not in (types.ModuleType, type):
                return None

            obj = inspect.getattr_static(obj, part, None)

            if obj is None:
                return None

        return (
            obj
            if type(obj)
            in (types.FunctionType, types.BuiltinFunctionType, types.MethodType)
            else None
        )


class _StrictSyntax(ast.NodeVisitor):
    """Reject operations with implicit dispatch rather than claiming to analyze it.

    This is a conservative lint profile, not an interpreter or a sandbox.
    Explicit trusted calls remain responsible for their arguments/callbacks.
    """

    def __init__(self, func_name: str) -> None:
        self.func_name = func_name

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
                ast.With,
                ast.AsyncWith,
                ast.ClassDef,
                ast.Subscript,
                ast.BinOp,
                ast.UnaryOp,
                ast.Compare,
                ast.BoolOp,
                ast.For,
                ast.AsyncFor,
                ast.comprehension,
                ast.JoinedStr,
                ast.Await,
                ast.Yield,
                ast.YieldFrom,
                ast.Match,
                ast.Starred,
                ast.If,
                ast.While,
                ast.IfExp,
                ast.Assert,
                ast.Delete,
            ),
        ):
            raise IntentParseError(
                self.func_name,
                f"{type(node).__name__} requires implicit execution; "
                "unsupported in strict mode",
            )
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        raise IntentParseError(
            self.func_name,
            "attribute access outside a call is unsupported in strict mode",
        )

    def visit_Call(self, node: ast.Call) -> None:
        target, dynamic = _format_target(node.func)
        if dynamic:
            raise IntentParseError(
                self.func_name, f"dynamic call {target} is unsupported in strict mode"
            )
        # The resolver checks dotted call targets without invoking descriptors.
        for arg in node.args:
            self.visit(arg)
        for keyword in node.keywords:
            if keyword.arg is None:
                raise IntentParseError(
                    self.func_name, "keyword unpacking is unsupported in strict mode"
                )
            self.visit(keyword.value)

    def visit_FunctionDef(self, node: FunctionDefLike) -> None:
        if (
            node.decorator_list
            or node.returns is not None
            or any(
                arg.annotation is not None
                for arg in [
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                ]
            )
        ):
            raise IntentParseError(
                self.func_name,
                "nested decorators and annotations are unsupported in strict mode",
            )
        for statement in node.body:
            self.visit(statement)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)

    visit_AsyncFunctionDef = visit_FunctionDef


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
        protected_names: set[str] | None = None,
        *,
        strict: bool = False,
        max_nodes: int = 10_000,
        analysis_depth: int = 100,
    ) -> None:
        self.strict = strict
        self.max_nodes = max_nodes
        self.analysis_depth = analysis_depth
        self._nodes = 0
        self._local_ids: dict[int, str] = {}
        self._local_blocked: dict[int, set[str]] = {}
        self.max_depth: int | float = max(0, max_depth)
        self.resolver = resolver or SafeResolver()
        self.protected_names = protected_names or set()
        try:
            self.root = self._build_from_callable(
                func=func,
                depth=0,
                stack=frozenset(),
                require_source=True,
            )
        except RecursionError as exc:
            raise IntentParseError(
                "<graph>", "analysis recursion budget exceeded"
            ) from exc

    def _check_budget(self, depth: int) -> None:
        self._nodes += 1
        if self._nodes > self.max_nodes or depth > self.analysis_depth:
            raise IntentParseError("<graph>", "call graph exceeds analysis budget")

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
        self._check_budget(depth)
        identity = get_function_identity(func)
        call_name = identity.split(":", 1)[-1]

        node = CallNode(
            identity=identity,
            call_name=call_name,
            resolved_func=func,
        )

        cycle_key = f"object:{id(func)}"
        if cycle_key in stack:
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
            stack=stack | {cycle_key},
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
        self._check_budget(depth)
        identity = self._local_ids.setdefault(
            id(func_def), f"local:{owner_identity}:{name}"
        )

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
        if self.strict:
            validator = _StrictSyntax(node.identity)
            for statement in func_def.body:
                validator.visit(statement)
        calls, own_locals = extract_calls_from_function_def(
            func_def, protected_names=self.protected_names
        )
        bindings = _ScopeBindings(func_def)
        blocked = set(bindings.counts)
        inherited_blocked = self._local_blocked.get(id(func_def), set())
        blocked.update(inherited_blocked)
        if parent_func is not None and type(parent_func) is types.FunctionType:
            blocked.update(parent_func.__code__.co_freevars)
        # Only a single, undecorated definition has a stable local target.
        stable_locals = {
            name: definition
            for name, definition in own_locals.items()
            if bindings.counts.get(name) == 1 and not definition.decorator_list
        }
        for definition in own_locals.values():
            self._local_blocked[id(definition)] = blocked - stable_locals.keys()
        merged_locals = {
            name: definition
            for name, definition in local_defs.items()
            if name not in bindings.counts and name not in inherited_blocked
        } | stable_locals
        child_stack = stack | {node.identity}

        for call in calls:
            if (
                call.target.split(".")[0] in blocked
                and call.target not in merged_locals
            ):
                call = CallLocation(
                    call.target, call.short_name, call.lineno, call.col_offset, True
                )
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
                self._check_budget(depth)
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
