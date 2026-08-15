from __future__ import annotations

import ast
import builtins
import os
import textwrap

import pytest

import pyintents
from pyintents import (
    CallNode,
    CallTree,
    IntentConfigurationError,
    IntentError,
    IntentNamespace,
    IntentParseError,
    IntentViolationError,
    introspect,
)
from pyintents.introspect import (
    CallLocation,
    SafeResolver,
    _format_target,
    _get_function_ast,
    _OuterCallCollector,
    extract_calls_from_function_def,
    get_calls,
    get_function_identity,
)
from pyintents.namespace import (
    DEFAULT_DENIED_DYNAMIC_PRIMITIVES,
    RuleSet,
    _EffectivePolicy,
    _normalize_rules,
    _validate_settings,
)

# ---------------------------------------------------------------------------
# Module-level subject functions.
#
# They are intentionally module-level so that SafeResolver can resolve them
# through function.__globals__.
# ---------------------------------------------------------------------------


def calls_os_getcwd():
    return os.getcwd()


def helper_allowed():
    return 1


def no_calls():
    return 1


def calls_helper():
    return helper_allowed()


def calls_eval():
    return eval("1")


def calls_calls_eval():
    return calls_eval()


def calls_len():
    return len([1, 2])


def calls_getattr():
    return getattr(helper_allowed, "__name__")


def calls_local_variable_callback():
    cb = helper_allowed
    return cb()


def calls_dynamic_expression():
    cb = helper_allowed
    return (cb if True else cb)()


def calls_local_function():
    def local_helper():
        return 1

    return local_helper()


def calls_local_function_with_eval():
    def inner():
        return eval("1")

    return inner()


def calls_len_and_helper():
    len([])
    return helper_allowed()


def recursive_subject():
    return recursive_subject()


def usemodule_subject():
    return helper_allowed()


class ResolverClass:
    def method(self):
        return 1


RESOLVER_INSTANCE = object()


def resolver_parent():
    return None


def _raise_oserror(_func):
    raise OSError("no source")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


def test_intent_violation_error_without_path():
    err = IntentViolationError("f", "os.system")
    assert err.func_name == "f"
    assert err.violation == "os.system"
    assert err.path == ()
    assert str(err) == "Function 'f' calls forbidden 'os.system'"


def test_intent_violation_error_with_path():
    err = IntentViolationError("f", "os.system", path=("a", "b"))
    assert err.func_name == "f"
    assert err.violation == "os.system"
    assert err.path == ("a", "b")
    assert str(err) == "Function 'a -> b -> f' calls forbidden 'os.system'"


def test_intent_parse_error():
    err = IntentParseError("f", "bad")
    assert err.func_name == "f"
    assert err.message == "bad"
    assert str(err) == "Function 'f' cannot be parsed: bad"


def test_exception_hierarchy():
    with pytest.raises(IntentError):
        raise IntentViolationError("f", "x")

    with pytest.raises(IntentError):
        raise IntentParseError("f", "x")

    with pytest.raises(IntentError):
        raise IntentConfigurationError("cfg")

    with pytest.raises(Exception):
        raise IntentError("base")


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------


def test_package_exports():
    assert pyintents.IntentError is IntentError
    assert pyintents.IntentViolationError is IntentViolationError
    assert pyintents.IntentParseError is IntentParseError
    assert pyintents.IntentConfigurationError is IntentConfigurationError
    assert pyintents.IntentNamespace is IntentNamespace
    assert pyintents.CallNode is CallNode
    assert pyintents.CallTree is CallTree


# ---------------------------------------------------------------------------
# introspect: get_function_identity
# ---------------------------------------------------------------------------


def test_get_function_identity_normal_function():
    def f():
        pass

    assert get_function_identity(f) == f"{f.__module__}:{f.__qualname__}"


def test_get_function_identity_unknown_module():
    def f():
        pass

    f.__module__ = None
    assert get_function_identity(f) == f"<unknown>:{f.__qualname__}"


def test_get_function_identity_callable_without_qualname():
    class C:
        def __call__(self):
            return 1

    c = C()
    c.__module__ = None
    c.__qualname__ = None
    c.__name__ = "custom"

    assert get_function_identity(c) == "<unknown>:custom"

    c.__name__ = None
    assert get_function_identity(c) == "<unknown>:None"


# ---------------------------------------------------------------------------
# introspect: _format_target
# ---------------------------------------------------------------------------


def test_format_target_all_branches():
    def expr(text: str) -> ast.expr:
        return ast.parse(text, mode="eval").body

    assert _format_target(expr("foo")) == ("foo", False)
    assert _format_target(expr("foo.bar")) == ("foo.bar", False)
    assert _format_target(expr("foo().bar")) == ("<dynamic>.bar", True)
    assert _format_target(expr("foo()")) == ("<call-result>", True)
    assert _format_target(expr("foo[0]")) == ("<subscript>", True)
    assert _format_target(expr("1")) == ("<dynamic>", True)


# ---------------------------------------------------------------------------
# introspect: AST collector
# ---------------------------------------------------------------------------


def test_collector_complex_function():
    src = """
    def outer():
        @decorator(default())
        def inner(
            pos: posann(),
            /,
            y: ann(),
            x=argdefault(),
            *args: va(),
            req,
            z: kwann() = kwdef(),
            **kwargs: kwa(),
        ):
            body_call()

        async def ainner():
            abody()

        @class_decorator(cdefault())
        class Meta(BaseCall(), metaclass=MetaCall()):
            class_attr = attr_call()

            @method_decorator(mdefault())
            def method(self, marg=margdef()):
                method_body()

            async def amethod(self):
                amethod_body()

            @nested_decorator(ndefault())
            class Nested(NestedBase()):
                nested_attr = nested_call()

        f = lambda x=lam_default(): lam_body()
        (lambda x=imm_default(): imm(x))()
        normal()
        obj.attr()
        dynamic_base().attr()
        call_result()()
        subscriptable[0]()
        (cond_call if True else other_call)()
        local_cb = helper
        local_cb()
    """

    module = ast.parse(textwrap.dedent(src))
    func_def = module.body[0]
    assert isinstance(func_def, ast.FunctionDef)

    calls, local_functions = extract_calls_from_function_def(func_def)
    targets = {call.target for call in calls}

    expected = {
        # Nested function decorators and defaults/annotations.
        "decorator",
        "default",
        "posann",
        "ann",
        "argdefault",
        "va",
        "kwann",
        "kwdef",
        "kwa",
        # Class decorators, bases, keywords.
        "class_decorator",
        "cdefault",
        "BaseCall",
        "MetaCall",
        # Class-level executable statement.
        "attr_call",
        # Method decorator and defaults.
        "method_decorator",
        "mdefault",
        "margdef",
        # Nested class.
        "nested_decorator",
        "ndefault",
        "NestedBase",
        "nested_call",
        # Lambda defaults.
        "lam_default",
        "imm_default",
        # Immediately invoked lambda body.
        "imm",
        # Ordinary calls.
        "normal",
        "obj.attr",
        # Dynamic base and dynamic attribute call.
        "dynamic_base",
        "<dynamic>.attr",
        # Call result call.
        "call_result",
        "<call-result>",
        # Subscript call.
        "<subscript>",
        # IfExp call target.
        "<dynamic>",
        # Local variable call.
        "local_cb",
    }

    assert targets == expected
    assert set(local_functions.keys()) == {"inner", "ainner"}


def test_visit_arguments_without_vararg_and_kwarg_annotations():
    collector = _OuterCallCollector()
    func_def = ast.parse("def f(*args, **kwargs): pass").body[0]
    assert isinstance(func_def, ast.FunctionDef)

    collector._visit_arguments(func_def.args)

    assert collector.calls == []
    assert collector.local_functions == {}


# ---------------------------------------------------------------------------
# introspect: _get_function_ast
# ---------------------------------------------------------------------------


def test_get_function_ast_normal():
    def sample():
        pass

    node = _get_function_ast(sample)
    assert isinstance(node, ast.FunctionDef)
    assert node.name == "sample"


def test_get_function_ast_async():
    async def async_sample():
        pass

    node = _get_function_ast(async_sample)
    assert isinstance(node, ast.AsyncFunctionDef)
    assert node.name == "async_sample"


def test_get_function_ast_source_unavailable_oserror(monkeypatch):
    def sample():
        pass

    monkeypatch.setattr(introspect.inspect, "getsource", _raise_oserror)

    with pytest.raises(IntentParseError, match="source code is not available"):
        _get_function_ast(sample)


def test_get_function_ast_source_unavailable_typeerror():
    with pytest.raises(IntentParseError, match="source code is not available"):
        _get_function_ast(len)


def test_get_function_ast_invalid_source(monkeypatch):
    def sample():
        pass

    def fake_source(_func):
        return "def broken(:"

    monkeypatch.setattr(introspect.inspect, "getsource", fake_source)

    with pytest.raises(IntentParseError, match="invalid source"):
        _get_function_ast(sample)


def test_get_function_ast_indentation_error(monkeypatch):
    def sample():
        pass

    def fake_source(_func):
        return "def f():\n  pass\n    bad\n"

    monkeypatch.setattr(introspect.inspect, "getsource", fake_source)

    with pytest.raises(IntentParseError, match="invalid source"):
        _get_function_ast(sample)


def test_get_function_ast_definition_not_found(monkeypatch):
    def sample():
        pass

    def fake_source(_func):
        return "def other():\n    pass\n"

    monkeypatch.setattr(introspect.inspect, "getsource", fake_source)

    with pytest.raises(IntentParseError, match="function definition was not found"):
        _get_function_ast(sample)


def test_get_function_ast_nested_target_second_walk(monkeypatch):
    def target_func():
        pass

    target_func.__name__ = "target"

    def fake_source(_func):
        return "if True:\n    def target():\n        pass\n"

    monkeypatch.setattr(introspect.inspect, "getsource", fake_source)

    node = _get_function_ast(target_func)
    assert node.name == "target"


def test_get_function_ast_target_name_none(monkeypatch):
    class C:
        def __call__(self):
            return 1

    cb = C()
    cb.__name__ = None

    def fake_source(_func):
        return "def anything():\n    pass\n"

    monkeypatch.setattr(introspect.inspect, "getsource", fake_source)

    node = _get_function_ast(cb)
    assert node.name == "anything"


# ---------------------------------------------------------------------------
# introspect: get_calls
# ---------------------------------------------------------------------------


def test_get_calls_returns_outer_calls_only():
    def subject():
        def inner():
            inner_body()

        inner()
        outer_body()

    assert set(get_calls(subject)) == {"inner", "outer_body"}


def test_get_calls_source_unavailable():
    with pytest.raises(IntentParseError, match="source code is not available"):
        get_calls(len)


# ---------------------------------------------------------------------------
# introspect: SafeResolver
# ---------------------------------------------------------------------------


def test_safe_resolver_all_branches():
    resolver = SafeResolver()

    # parent_func None
    assert resolver.resolve("foo", None) is None

    # Empty and dynamic names.
    assert resolver.resolve("", resolver_parent) is None
    assert resolver.resolve("<dynamic>", resolver_parent) is None

    # Unknown name.
    assert resolver.resolve("unknown_name_xyz", resolver_parent) is None

    # Fallback to builtins.
    assert resolver.resolve("len", resolver_parent) is builtins.len

    # Module attribute callable.
    assert resolver.resolve("os.getcwd", resolver_parent) is os.getcwd

    # Module attribute non-callable.
    assert resolver.resolve("os.name", resolver_parent) is None

    # Missing attribute.
    assert resolver.resolve("os.missing_attr_xyz", resolver_parent) is None

    # Class attribute function.
    resolved_method = resolver.resolve("ResolverClass.method", resolver_parent)
    assert resolved_method is not None
    assert callable(resolved_method)

    # Intermediate object is not module/type.
    assert resolver.resolve("RESOLVER_INSTANCE.anything", resolver_parent) is None

    # Parent without __globals__.
    assert resolver.resolve("foo", len) is None


# ---------------------------------------------------------------------------
# introspect: CallNode / CallLocation
# ---------------------------------------------------------------------------


def test_call_location_defaults():
    loc = CallLocation(target="a.b", short_name="b", lineno=1, col_offset=2)
    assert loc.target == "a.b"
    assert loc.short_name == "b"
    assert loc.lineno == 1
    assert loc.col_offset == 2
    assert loc.is_dynamic is False


def test_call_node_walk():
    root = CallNode(identity="root", call_name="root")
    child = CallNode(identity="child", call_name="child")
    grandchild = CallNode(identity="grandchild", call_name="grandchild")

    root.children.append(child)
    child.children.append(grandchild)

    assert [node.identity for node in root.walk()] == [
        "root",
        "child",
        "grandchild",
    ]


# ---------------------------------------------------------------------------
# introspect: CallTree
# ---------------------------------------------------------------------------


def test_calltree_direct_calls_and_search():
    tree = CallTree(calls_helper, max_depth=2)

    assert tree.root.call_name == "calls_helper"
    assert tree.root.is_source_available is True

    helper_identity = get_function_identity(helper_allowed)

    assert tree.has_call("helper_allowed")
    assert tree.has_call(helper_identity)
    assert not tree.has_call("missing_call")

    by_name = tree.find_calls("helper_allowed")
    by_identity = tree.find_calls(helper_identity)

    assert by_name
    assert by_identity
    assert by_name[0].resolved_func is helper_allowed
    assert by_name[0].lineno is not None
    assert by_name[0].col_offset is not None


def test_calltree_max_depth_zero_and_negative():
    tree = CallTree(calls_helper, max_depth=0)
    assert tree.max_depth == 0
    assert tree.root.children == []

    tree_negative = CallTree(calls_helper, max_depth=-5)
    assert tree_negative.max_depth == 0
    assert tree_negative.root.children == []


def test_calltree_root_source_unavailable():
    with pytest.raises(IntentParseError, match="source code is not available"):
        CallTree(len, max_depth=1)


def test_calltree_max_depth_zero_does_not_require_source():
    tree = CallTree(len, max_depth=0)
    assert tree.root.resolved_func is len
    assert tree.root.children == []


def test_calltree_child_source_unavailable():
    tree = CallTree(calls_len, max_depth=2)
    child = tree.root.children[0]

    assert child.call_name == "len"
    assert child.resolved_func is len
    assert child.is_source_available is False
    assert child.is_unresolved is False


def test_calltree_unresolved_non_dynamic():
    tree = CallTree(calls_local_variable_callback, max_depth=2)
    child = tree.root.children[0]

    assert child.call_name == "cb"
    assert child.is_unresolved is True
    assert child.is_dynamic is False
    assert child.is_source_available is False


def test_calltree_dynamic_unresolved():
    tree = CallTree(calls_dynamic_expression, max_depth=2)
    nodes = tree.find_calls("<dynamic>")

    assert nodes
    node = nodes[0]
    assert node.is_dynamic is True
    assert node.is_unresolved is True
    assert node.is_source_available is False


def test_calltree_local_definition():
    tree = CallTree(calls_local_function, max_depth=2)
    child = tree.root.children[0]

    assert child.call_name == "local_helper"
    assert child.is_local_definition is True
    assert child.is_source_available is True


def test_calltree_local_mutual_calls():
    def local_mutual():
        def a():
            return b()

        def b():
            return 1

        return a()

    tree = CallTree(local_mutual, max_depth=10)

    a_node = tree.root.children[0]
    assert a_node.call_name == "a"
    assert a_node.is_local_definition is True

    b_node = a_node.children[0]
    assert b_node.call_name == "b"
    assert b_node.is_local_definition is True


def test_calltree_local_recursion_is_limited_by_depth_not_cycle():
    def local_rec():
        def rec():
            rec()

        rec()

    tree = CallTree(local_rec, max_depth=3)

    rec1 = tree.root.children[0]
    rec2 = rec1.children[0]
    rec3 = rec2.children[0]

    assert rec1.call_name == "rec"
    assert rec2.call_name == "rec"
    assert rec3.call_name == "rec"
    assert rec3.children == []

    # In the current implementation local identities include owner_identity,
    # so recursive local calls do not produce the same identity on descent.
    assert not any(node.is_cycle for node in tree.root.walk())


def test_calltree_global_recursion_cycle():
    tree = CallTree(recursive_subject, max_depth=5)
    assert any(node.is_cycle for node in tree.root.walk())


def test_calltree_async_root():
    async def async_subject():
        helper_allowed()

    tree = CallTree(async_subject, max_depth=2)
    assert tree.has_call("helper_allowed")


def test_calltree_custom_resolver():
    class DummyResolver:
        def resolve(self, name, parent_func):
            return None

    tree = CallTree(calls_helper, max_depth=2, resolver=DummyResolver())
    child = tree.root.children[0]

    assert child.call_name == "helper_allowed"
    assert child.is_unresolved is True


def test_calltree_local_child_not_expanded_at_max_depth_one():
    tree = CallTree(calls_local_function, max_depth=1)
    child = tree.root.children[0]

    assert child.call_name == "local_helper"
    assert child.children == []


# ---------------------------------------------------------------------------
# namespace: RuleSet
# ---------------------------------------------------------------------------


def test_ruleset_union():
    rs1 = RuleSet(
        objects=frozenset({helper_allowed}),
        identities=frozenset({"a"}),
        names=frozenset({"n1"}),
        short_names=frozenset({"s1"}),
    )
    rs2 = RuleSet(
        identities=frozenset({"b"}),
        names=frozenset({"n2"}),
        short_names=frozenset({"s2"}),
    )

    union = rs1.union(rs2)

    assert helper_allowed in union.objects
    assert union.identities == frozenset({"a", "b"})
    assert union.names == frozenset({"n1", "n2"})
    assert union.short_names == frozenset({"s1", "s2"})


def test_ruleset_matches_all_branches():
    def sample():
        pass

    # Object match.
    rs_object = RuleSet(objects=frozenset({sample}))
    node_object = CallNode(identity="x", call_name="x", resolved_func=sample)
    assert rs_object.matches(node_object)

    # Resolved identity match.
    rs_identity = RuleSet(identities=frozenset({get_function_identity(sample)}))
    assert rs_identity.matches(node_object)

    # Node identity match.
    rs_node_identity = RuleSet(identities=frozenset({"local:x"}))
    assert rs_node_identity.matches(CallNode(identity="local:x", call_name="y"))

    # Full name match.
    rs_names = RuleSet(names=frozenset({"a.b"}))
    assert rs_names.matches(CallNode(identity="i", call_name="a.b"))

    # Short name match.
    rs_short = RuleSet(short_names=frozenset({"b"}))
    assert rs_short.matches(CallNode(identity="i", call_name="a.b"))

    # No match.
    assert not RuleSet().matches(CallNode(identity="i", call_name="a.b"))


def test_ruleset_matches_unhashable_resolved_func():
    class UnhashableCallable:
        __hash__ = None

        def __call__(self):
            return 1

    cb = UnhashableCallable()
    cb.__module__ = "m"
    cb.__qualname__ = "Foo.bar"
    cb.__name__ = None

    node = CallNode(identity="x", call_name="x", resolved_func=cb)

    # TypeError branch in RuleSet.matches.
    assert not RuleSet().matches(node)

    identity = get_function_identity(cb)
    rs = RuleSet(identities=frozenset({identity}))
    assert rs.matches(node)


# ---------------------------------------------------------------------------
# namespace: _normalize_rules
# ---------------------------------------------------------------------------


def test_normalize_rules_string_identity_like():
    rs_false = _normalize_rules(["mod:pkg.func"], include_short_names=False)
    assert "mod:pkg.func" in rs_false.identities
    assert "pkg.func" not in rs_false.names
    assert "func" not in rs_false.short_names

    rs_true = _normalize_rules(["mod:pkg.func"], include_short_names=True)
    assert "mod:pkg.func" in rs_true.identities
    assert "pkg.func" in rs_true.names
    assert "func" in rs_true.short_names


def test_normalize_rules_string_dotted_and_bare():
    rs_dotted_false = _normalize_rules(["os.path.join"], include_short_names=False)
    assert "os.path.join" in rs_dotted_false.names
    assert "os.path:join" in rs_dotted_false.identities
    assert "join" not in rs_dotted_false.short_names

    rs_dotted_true = _normalize_rules(["os.path.join"], include_short_names=True)
    assert "join" in rs_dotted_true.short_names

    rs_bare_false = _normalize_rules(["print"], include_short_names=False)
    assert "print" in rs_bare_false.names
    assert "print" in rs_bare_false.short_names


def test_normalize_rules_empty_string_and_invalid_rule():
    with pytest.raises(IntentConfigurationError, match="String rule cannot be empty"):
        _normalize_rules(["   "], include_short_names=False)

    with pytest.raises(
        IntentConfigurationError, match="Rule must be a callable or a string"
    ):
        _normalize_rules([123], include_short_names=False)


def test_normalize_rules_callable_normal():
    def sample():
        pass

    rs_false = _normalize_rules([sample], include_short_names=False)

    assert sample in rs_false.objects
    assert get_function_identity(sample) in rs_false.identities
    assert f"{sample.__module__}.{sample.__qualname__}" in rs_false.names
    assert sample.__name__ not in rs_false.short_names

    rs_true = _normalize_rules([sample], include_short_names=True)
    assert sample.__name__ in rs_true.short_names


def test_normalize_rules_callable_missing_module_or_qualname():
    class CallableThing:
        def __call__(self):
            return 1

    cb = CallableThing()
    cb.__module__ = None
    cb.__qualname__ = None
    cb.__name__ = None

    rs = _normalize_rules([cb], include_short_names=True)
    identity = get_function_identity(cb)

    assert identity in rs.identities
    assert cb in rs.objects
    assert rs.names == frozenset()
    assert rs.short_names == frozenset()


def test_normalize_rules_callable_no_name_but_qualname():
    class CallableThing:
        def __call__(self):
            return 1

    cb = CallableThing()
    cb.__module__ = "m"
    cb.__qualname__ = "Foo.bar"
    cb.__name__ = None

    rs = _normalize_rules([cb], include_short_names=True)

    assert "m:Foo.bar" in rs.identities
    assert "m.Foo.bar" in rs.names
    assert "bar" in rs.short_names


def test_normalize_rules_callable_module_without_qualname():
    class CallableThing:
        def __call__(self):
            return 1

    cb = CallableThing()
    cb.__module__ = "m"
    cb.__qualname__ = None
    cb.__name__ = "x"

    rs = _normalize_rules([cb], include_short_names=True)

    assert "m:x" in rs.identities
    assert rs.names == frozenset()
    assert "x" in rs.short_names


def test_normalize_rules_unhashable_callable():
    class UnhashableCallable:
        __hash__ = None

        def __call__(self):
            return 1

    cb = UnhashableCallable()
    cb.__module__ = "m"
    cb.__qualname__ = "Foo.bar"
    cb.__name__ = None

    rs = _normalize_rules([cb], include_short_names=True)

    assert len(rs.objects) == 0
    assert get_function_identity(cb) in rs.identities
    assert "m.Foo.bar" in rs.names
    assert "bar" in rs.short_names


# ---------------------------------------------------------------------------
# namespace: _validate_settings
# ---------------------------------------------------------------------------


def test_validate_settings():
    _validate_settings(recursive=True, usemodule=True)
    _validate_settings(recursive=False, usemodule=False)

    with pytest.raises(
        IntentConfigurationError, match="usemodule requires recursive=True"
    ):
        _validate_settings(recursive=False, usemodule=True)


# ---------------------------------------------------------------------------
# namespace: IntentNamespace._is_allowed
# ---------------------------------------------------------------------------


def make_policy(**overrides) -> _EffectivePolicy:
    params = dict(
        uses=RuleSet(),
        deny=RuleSet(),
        without=RuleSet(),
        recursive=True,
        uselocals=False,
        usemodule=False,
        allow_unknown=False,
    )
    params.update(overrides)
    return _EffectivePolicy(**params)


def test_is_allowed_uses_match():
    policy = make_policy(uses=RuleSet(names=frozenset({"foo"})))
    node = CallNode(identity="i", call_name="foo")
    assert IntentNamespace._is_allowed(node, policy) is True


def test_is_allowed_locals():
    node = CallNode(identity="local:i:foo", call_name="foo", is_local_definition=True)

    assert IntentNamespace._is_allowed(node, make_policy(uselocals=True)) is True
    assert IntentNamespace._is_allowed(node, make_policy(uselocals=False)) is False


def test_is_allowed_usemodule_all_subbranches():
    def dummy():
        pass

    dummy.__module__ = "same"

    policy = make_policy(usemodule=True)
    node = CallNode(
        identity="i",
        call_name="dummy",
        resolved_func=dummy,
        is_source_available=True,
    )

    # All conditions true.
    assert IntentNamespace._is_allowed(node, policy, root_module="same") is True

    # child_module != root_module
    assert IntentNamespace._is_allowed(node, policy, root_module="other") is False

    # root_module == "builtins"
    assert IntentNamespace._is_allowed(node, policy, root_module="builtins") is False

    # usemodule false
    assert (
        IntentNamespace._is_allowed(
            node, make_policy(usemodule=False), root_module="same"
        )
        is False
    )

    # root_module falsey
    assert IntentNamespace._is_allowed(node, policy, root_module=None) is False

    # resolved_func is None
    node_no_func = CallNode(identity="i", call_name="x", resolved_func=None)
    assert (
        IntentNamespace._is_allowed(node_no_func, policy, root_module="same") is False
    )

    # source unavailable
    node_no_source = CallNode(
        identity="i",
        call_name="x",
        resolved_func=dummy,
        is_source_available=False,
    )
    assert (
        IntentNamespace._is_allowed(node_no_source, policy, root_module="same") is False
    )


def test_is_allowed_unknown_flags():
    for allow_unknown in (True, False):
        policy = make_policy(allow_unknown=allow_unknown)

        unresolved = CallNode(identity="u", call_name="u", is_unresolved=True)
        dynamic = CallNode(identity="d", call_name="d", is_dynamic=True)
        no_source = CallNode(identity="s", call_name="s", is_source_available=False)

        assert IntentNamespace._is_allowed(unresolved, policy) is allow_unknown
        assert IntentNamespace._is_allowed(dynamic, policy) is allow_unknown
        assert IntentNamespace._is_allowed(no_source, policy) is allow_unknown


def test_is_allowed_final_false():
    def dummy():
        pass

    node = CallNode(
        identity="i",
        call_name="x",
        resolved_func=dummy,
        is_source_available=True,
    )

    assert IntentNamespace._is_allowed(node, make_policy(), root_module="same") is False


# ---------------------------------------------------------------------------
# namespace: default denied primitives
# ---------------------------------------------------------------------------


def test_default_denied_primitives_normalized():
    rs = _normalize_rules(DEFAULT_DENIED_DYNAMIC_PRIMITIVES, include_short_names=True)

    assert "eval" in rs.short_names
    assert "exec" in rs.short_names
    assert "compile" in rs.short_names
    assert "getattr" in rs.short_names


def test_namespace_default_denies_dynamic_primitives():
    ns = IntentNamespace()
    assert "eval" in ns._deny.short_names

    ns_disabled = IntentNamespace(deny_dynamic_primitives=False)
    assert "eval" not in ns_disabled._deny.short_names


# ---------------------------------------------------------------------------
# namespace: IntentNamespace configuration errors
# ---------------------------------------------------------------------------


def test_namespace_invalid_usemodule_requires_recursive():
    with pytest.raises(
        IntentConfigurationError, match="usemodule requires recursive=True"
    ):
        IntentNamespace(usemodule=True, recursive=False)


def test_intent_invalid_usemodule_requires_recursive():
    ns = IntentNamespace()

    with pytest.raises(
        IntentConfigurationError, match="usemodule requires recursive=True"
    ):
        ns.intent(usemodule=True, recursive=False)


def test_namespace_invalid_rules():
    with pytest.raises(IntentConfigurationError, match="String rule cannot be empty"):
        IntentNamespace(uses=["   "])

    with pytest.raises(
        IntentConfigurationError, match="Rule must be a callable or a string"
    ):
        IntentNamespace(uses=[123])

    ns = IntentNamespace()

    with pytest.raises(IntentConfigurationError, match="String rule cannot be empty"):
        ns.intent(uses=["   "])

    with pytest.raises(
        IntentConfigurationError, match="Rule must be a callable or a string"
    ):
        ns.intent(uses=[123])


# ---------------------------------------------------------------------------
# namespace: IntentNamespace end-to-end
# ---------------------------------------------------------------------------


def test_no_calls_passes():
    ns = IntentNamespace()
    decorated = ns.intent()(no_calls)
    assert decorated() == 1


def test_rules_accept_helper():
    rules = [
        helper_allowed,
        "helper_allowed",
        f"{helper_allowed.__module__}.{helper_allowed.__qualname__}",
        f"{helper_allowed.__module__}:{helper_allowed.__qualname__}",
    ]

    for rule in rules:
        ns = IntentNamespace(uses=[rule])
        decorated = ns.intent()(calls_helper)
        assert decorated() == 1


def test_without_exempts():
    ns = IntentNamespace(without=[helper_allowed])
    decorated = ns.intent()(calls_helper)
    assert decorated() == 1


def test_deny_has_priority_over_uses_and_without():
    ns_deny_uses = IntentNamespace(deny=[helper_allowed], uses=[helper_allowed])
    decorated = ns_deny_uses.intent()(calls_helper)

    with pytest.raises(IntentViolationError):
        decorated()

    ns_deny_without = IntentNamespace(deny=[helper_allowed], without=[helper_allowed])
    decorated2 = ns_deny_without.intent()(calls_helper)

    with pytest.raises(IntentViolationError):
        decorated2()


def test_usemodule_allows_same_module():
    ns_allowed = IntentNamespace(usemodule=True)
    assert ns_allowed.intent()(usemodule_subject)() == 1

    ns_denied = IntentNamespace(usemodule=False)
    with pytest.raises(IntentViolationError):
        ns_denied.intent()(usemodule_subject)()


def test_uselocals_allows_local_functions():
    ns_allowed = IntentNamespace(uselocals=True)
    assert ns_allowed.intent()(calls_local_function)() == 1

    ns_denied = IntentNamespace(uselocals=False)
    with pytest.raises(IntentViolationError):
        ns_denied.intent()(calls_local_function)()


def test_allow_unknown_allows_unresolved_local_variable_call():
    ns_allowed = IntentNamespace(allow_unknown=True)
    assert ns_allowed.intent()(calls_local_variable_callback)() == 1

    ns_denied = IntentNamespace(allow_unknown=False)
    with pytest.raises(IntentViolationError):
        ns_denied.intent()(calls_local_variable_callback)()


def test_allow_unknown_allows_dynamic_calls():
    ns_allowed = IntentNamespace(allow_unknown=True)
    assert ns_allowed.intent()(calls_dynamic_expression)() == 1

    ns_denied = IntentNamespace(allow_unknown=False)
    with pytest.raises(IntentViolationError):
        ns_denied.intent()(calls_dynamic_expression)()


def test_allow_unknown_allows_builtin_without_source():
    ns_allowed = IntentNamespace(allow_unknown=True)
    assert ns_allowed.intent()(calls_len)() == 2

    ns_denied = IntentNamespace(allow_unknown=False)
    with pytest.raises(IntentViolationError):
        ns_denied.intent()(calls_len)()


def test_deny_dynamic_primitives_default_and_disabled():
    ns_default = IntentNamespace(uses=["getattr"])
    with pytest.raises(IntentViolationError):
        ns_default.intent()(calls_getattr)()

    ns_disabled = IntentNamespace(deny_dynamic_primitives=False, uses=["getattr"])
    assert ns_disabled.intent()(calls_getattr)() == "helper_allowed"


def test_recursive_false_does_not_expand_children():
    ns = IntentNamespace(uses=[calls_eval], recursive=False)
    decorated = ns.intent()(calls_calls_eval)
    assert decorated() == 1


def test_recursive_true_expands_children_and_denies_eval():
    ns = IntentNamespace(uses=[calls_eval], recursive=True)
    decorated = ns.intent()(calls_calls_eval)

    with pytest.raises(IntentViolationError) as exc:
        decorated()

    assert exc.value.violation.split(" ")[0] == "eval"


def test_direct_violation_attributes():
    ns = IntentNamespace()
    decorated = ns.intent()(calls_helper)

    with pytest.raises(IntentViolationError) as exc:
        decorated()

    assert exc.value.func_name == "calls_helper"
    assert exc.value.violation.split(" ")[0] == "helper_allowed"
    assert exc.value.path == ()


def test_nested_violation_path_and_attributes():
    ns = IntentNamespace(uselocals=True)
    decorated = ns.intent()(calls_local_function_with_eval)

    with pytest.raises(IntentViolationError) as exc:
        decorated()

    assert exc.value.violation.split(" ")[0] == "eval"
    assert exc.value.func_name == "inner"
    assert exc.value.path == ("calls_local_function_with_eval",)


def test_only_warnings_not_allowed():
    ns = IntentNamespace(only_warnings=True)
    decorated = ns.intent()(calls_helper)

    with pytest.warns(UserWarning, match="Intent violation"):
        assert decorated() == 1


def test_only_warnings_deny():
    ns = IntentNamespace(deny=["helper_allowed"], only_warnings=True)
    decorated = ns.intent()(calls_helper)

    with pytest.warns(UserWarning, match="Intent violation"):
        assert decorated() == 1


def test_intent_overrides_all_parameters():
    ns = IntentNamespace()

    decorated = ns.intent(
        uses=[helper_allowed],
        recursive=True,
        without=[len],
        uselocals=True,
        usemodule=True,
        deny=["eval"],
        allow_unknown=True,
    )(calls_len_and_helper)

    assert decorated() == 1


def test_intent_recursive_override_false():
    ns = IntentNamespace(uses=[calls_eval], recursive=True)
    decorated = ns.intent(recursive=False)(calls_calls_eval)
    assert decorated() == 1


def test_intent_uselocals_override():
    ns = IntentNamespace(uselocals=False)
    decorated = ns.intent(uselocals=True)(calls_local_function)
    assert decorated() == 1


def test_intent_usemodule_override():
    ns = IntentNamespace(usemodule=False)
    decorated = ns.intent(usemodule=True)(usemodule_subject)
    assert decorated() == 1


def test_intent_allow_unknown_override():
    ns = IntentNamespace(allow_unknown=False)
    decorated = ns.intent(allow_unknown=True)(calls_local_variable_callback)
    assert decorated() == 1


def test_intent_merging_uses():
    ns = IntentNamespace(uses=[len])
    decorated = ns.intent(uses=[helper_allowed])(calls_len_and_helper)
    assert decorated() == 1


def test_intent_merging_without():
    ns = IntentNamespace(without=[len])
    decorated = ns.intent(without=[helper_allowed])(calls_len_and_helper)
    assert decorated() == 1


def test_intent_merging_deny():
    ns = IntentNamespace(deny=[len])
    decorated = ns.intent(deny=[helper_allowed])(calls_len_and_helper)

    with pytest.raises(IntentViolationError):
        decorated()


def test_wrapper_propagates_intent_parse_error(monkeypatch):
    ns = IntentNamespace()
    decorated = ns.intent()(no_calls)

    monkeypatch.setattr(introspect.inspect, "getsource", _raise_oserror)

    with pytest.raises(IntentParseError, match="source code is not available"):
        decorated()


def test_build_from_ast_cycle_branch_direct():
    tree = CallTree(no_calls, max_depth=1)

    func_def = ast.parse("def rec():\n    pass").body[0]
    assert isinstance(func_def, ast.FunctionDef)

    owner_identity = "owner"
    name = "rec"
    identity = f"local:{owner_identity}:{name}"

    node = tree._build_from_ast(
        func_def=func_def,
        name=name,
        depth=1,
        stack=frozenset({identity}),
        parent_func=None,
        local_defs={},
        owner_identity=owner_identity,
    )

    assert node.identity == identity
    assert node.is_cycle is True
    assert node.children == []


def test_calltree_dotted_call_skips_local_lookup():
    tree = CallTree(calls_os_getcwd, max_depth=2)

    nodes = tree.find_calls("os.getcwd")
    assert nodes

    node = nodes[0]
    assert node.call_name == "os.getcwd"
    assert node.resolved_func is os.getcwd
    assert node.is_dynamic is False
    assert node.is_unresolved is False

    assert tree.find_calls("missing") == []


def test_ruleset_no_match_with_resolved_func():
    assert not RuleSet().matches(
        CallNode(
            identity="i",
            call_name="x",
            resolved_func=helper_allowed,
        )
    )


def test_get_function_identity_fallback_repr():
    class NoNameCallable:
        def __call__(self):
            return 1

        def __getattribute__(self, name):
            if name in ("__qualname__", "__name__"):
                raise AttributeError(name)
            return super().__getattribute__(name)

    cb = NoNameCallable()
    identity = get_function_identity(cb)

    assert ":<" in identity


def test_calltree_call_name_fallback_to_identity():
    class NoNameCallable:
        def __call__(self):
            return 1

        def __getattribute__(self, name):
            if name in ("__qualname__", "__name__"):
                raise AttributeError(name)
            return super().__getattribute__(name)

    cb = NoNameCallable()
    tree = CallTree(cb, max_depth=0)

    assert tree.root.call_name == tree.root.identity
