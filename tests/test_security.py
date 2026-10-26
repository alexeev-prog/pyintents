"""Regression tests use markers, never privileged or destructive operations."""

import asyncio
import builtins
import functools
import inspect
import linecache
import types

import pytest

from pyintents import (
    CallTree,
    IntentConfigurationError,
    IntentError,
    IntentNamespace,
    IntentParseError,
    IntentViolationError,
)


@pytest.fixture
def subjects():
    source = """
events = []
def forbidden(*args):
    events.append("FORBIDDEN")
    return 7
def safe():
    return 1
def parameter(safe):
    return safe()
def loop():
    for safe in [forbidden]:
        return safe()
def walrus():
    (safe := forbidden)
    return safe()
def unpack():
    [[safe]] = [[forbidden]]
    return safe()
def replacement():
    def inner():
        return 1
    inner = forbidden
    return inner()
def exception_binding():
    try:
        pass
    except Exception as safe:
        return safe()
def matching(value):
    match value:
        case {"callback": safe}:
            return safe()
class Evil:
    @property
    def value(self):
        return forbidden()
    def __len__(self):
        return forbidden()
    def __enter__(self):
        return forbidden()
    def __exit__(self, *args):
        pass
obj = Evil()
def property_read():
    return obj.value
def context():
    with obj:
        pass
def import_only():
    import audit_never_import_this
def decorator():
    @forbidden
    def inner():
        pass
def mutation():
    box.safe = forbidden
    return box.safe()
def alias_call():
    return alias("events.append('FORBIDDEN')")
def actual_wrapper(*args, **kwargs):
    return forbidden()
def local_recursion():
    def inner(n):
        if n:
            return inner(n - 1)
        return 1
    return inner(1)
async def async_entry():
    return safe()
def generator():
    yield safe()
def uses_len():
    return len([])
def uses_object_len():
    return len(obj)
def uses_sorted_callback():
    return sorted([1, 2], key=forbidden)
def closure_factory(callback):
    def entry():
        return callback()
    return entry
def nested_parameter(safe):
    def inner():
        return safe()
    return inner()
def calls_target():
    return target()
"""
    filename = "<pyintents-security-tests>"
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
    module = types.ModuleType("security_subjects")
    exec(compile(source, filename, "exec"), module.__dict__)
    module.box = types.ModuleType("box")
    module.box.safe = module.safe
    module.alias = exec
    yield module
    linecache.cache.pop(filename, None)


@pytest.mark.parametrize(
    "name,args",
    [
        ("parameter", ("callback",)),
        ("loop", ()),
        ("walrus", ()),
        ("unpack", ()),
        ("replacement", ()),
        ("property_read", ()),
        ("context", ()),
        ("import_only", ()),
        ("decorator", ()),
        ("mutation", ()),
        ("matching", ({"callback": "callback"},)),
    ],
)
def test_strict_rejects_bypasses_before_effects(subjects, name, args):
    args = tuple(subjects.forbidden if arg == "callback" else arg for arg in args)
    namespace = IntentNamespace(uses=[subjects.safe], uselocals=True)
    with pytest.raises(IntentError):
        namespace.intent()(getattr(subjects, name))(*args)
    assert subjects.events == []


@pytest.mark.parametrize(
    "name", ["parameter", "loop", "walrus", "unpack", "replacement"]
)
def test_scope_resolution_also_hardened_in_audit_mode(subjects, name):
    namespace = IntentNamespace(uses=[subjects.safe], uselocals=True, strict=False)
    args = (subjects.forbidden,) if name == "parameter" else ()
    with pytest.raises(IntentViolationError):
        namespace.intent()(getattr(subjects, name))(*args)
    assert subjects.events == []


def test_exception_and_pattern_bindings_are_not_globals(subjects):
    for name in ("exception_binding", "matching"):
        tree = CallTree(getattr(subjects, name), max_depth=2)
        assert tree.find_calls("safe")[0].is_unresolved


@pytest.mark.parametrize("allow_unknown", [False, True])
def test_exec_alias_deny_has_priority(subjects, allow_unknown):
    ns = IntentNamespace(uses=[exec], allow_unknown=allow_unknown)
    with pytest.raises(IntentViolationError):
        ns.intent()(subjects.alias_call)()
    assert subjects.events == []


def test_source_does_not_follow_wrapped(subjects):
    wrapped = functools.wraps(subjects.safe)(subjects.actual_wrapper)
    with pytest.raises(IntentViolationError):
        IntentNamespace().intent()(wrapped)()
    assert subjects.events == []


def test_actual_function_builtins_are_used(subjects):
    namespace = dict(subjects.__dict__)
    namespace["__builtins__"] = dict(vars(builtins), len=subjects.forbidden)
    func = types.FunctionType(subjects.uses_len.__code__, namespace)
    with pytest.raises(IntentViolationError):
        IntentNamespace(uses=[len]).intent()(func)()
    assert subjects.events == []


def test_callable_metadata_never_executed(subjects):
    class Hostile:
        def __getattribute__(self, name):
            raise AssertionError("metadata access")

        def __repr__(self):
            raise AssertionError("repr")

        def __hash__(self):
            raise AssertionError("hash")

        def __call__(self):
            raise AssertionError("call")

    subjects.target = Hostile()
    with pytest.raises(IntentViolationError):
        IntentNamespace().intent()(subjects.calls_target)()
    with pytest.raises(IntentConfigurationError):
        IntentNamespace(uses=[subjects.target])


def test_object_rule_cannot_be_spoofed_by_metadata(subjects):
    subjects.forbidden.__module__ = subjects.safe.__module__
    subjects.forbidden.__qualname__ = subjects.safe.__qualname__
    original = subjects.safe
    subjects.safe = subjects.forbidden
    with pytest.raises(IntentViolationError):
        asyncio.run(IntentNamespace(uses=[original]).intent()(subjects.async_entry)())
    assert subjects.events == []


def test_async_checks_at_execution_and_preserves_kind(subjects):
    wrapped = IntentNamespace(uses=[subjects.safe]).intent()(subjects.async_entry)
    assert inspect.iscoroutinefunction(wrapped)
    pending = wrapped()
    subjects.safe = subjects.forbidden
    with pytest.raises(IntentViolationError):
        asyncio.run(pending)
    assert subjects.events == []


def test_generators_are_explicitly_unsupported(subjects):
    with pytest.raises(IntentConfigurationError, match="generator"):
        IntentNamespace().intent()(subjects.generator)


def test_closure_is_not_resolved_as_global(subjects):
    entry = subjects.closure_factory(subjects.forbidden)
    subjects.callback = subjects.safe
    with pytest.raises(IntentViolationError):
        IntentNamespace(uses=[subjects.safe]).intent()(entry)()


def test_nested_scope_cannot_resolve_outer_parameter_as_global(subjects):
    namespace = IntentNamespace(uses=[subjects.safe], uselocals=True)
    with pytest.raises(IntentViolationError):
        namespace.intent()(subjects.nested_parameter)(subjects.forbidden)
    assert subjects.events == []


def test_local_recursion_is_finite_in_analysis(subjects):
    tree = CallTree(subjects.local_recursion, max_depth=float("inf"))
    assert any(node.is_cycle for node in tree.root.walk())
    assert (
        IntentNamespace(uselocals=True, strict=False).intent()(
            subjects.local_recursion
        )()
        == 1
    )


def test_analysis_budget_fails_closed(subjects):
    with pytest.raises(IntentParseError, match="budget"):
        asyncio.run(
            IntentNamespace(uses=[subjects.safe], max_nodes=1).intent()(
                subjects.async_entry
            )()
        )


def test_strict_limitations_are_not_hidden(subjects):
    # Trusted opaque builtins may call arbitrary protocols. This is deliberately
    # documented: static validation is NOT an untrusted-code boundary.
    assert IntentNamespace(uses=[len]).intent()(subjects.uses_object_len)() == 7
    assert subjects.events == ["FORBIDDEN"]
    subjects.events.clear()
    assert IntentNamespace(uses=[sorted]).intent()(subjects.uses_sorted_callback)() == [
        1,
        2,
    ]
    assert subjects.events == ["FORBIDDEN", "FORBIDDEN"]


@pytest.mark.parametrize("option", ["max_nodes", "analysis_depth"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_analysis_limits(option, value):
    with pytest.raises(IntentConfigurationError):
        IntentNamespace(**{option: value})


def test_string_deny_still_blocks_unresolved_with_allow_unknown(subjects):
    namespace = IntentNamespace(deny=["safe"], allow_unknown=True)
    with pytest.raises(IntentViolationError):
        namespace.intent()(subjects.parameter)(subjects.forbidden)
    assert subjects.events == []


def test_async_success(subjects):
    wrapped = IntentNamespace(uses=[subjects.safe]).intent()(subjects.async_entry)
    assert asyncio.run(wrapped()) == 1
