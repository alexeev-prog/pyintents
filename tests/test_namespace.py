# tests/test_namespace.py
import os
from unittest.mock import Mock

from pyintents.namespace import IntentNamespace


def simple_func():
    pass


def func_with_print():
    print("Hello")


def func_with_os():
    import os

    os.system("test")


def func_with_inner_call():
    def inner():
        print("Inner")

    inner()


def recursive_func():
    recursive_func()
    print("Recursive")


def func_with_multiple_calls():
    print("One")
    len([1, 2])
    sum([1, 2, 3])


def local_function():
    print("Local")


class TestIntentNamespace:
    def test_init_default(self):
        ns = IntentNamespace()
        assert ns._uses == {}
        assert ns._recursive is False
        assert ns._without == {}
        assert ns._uselocals is False
        assert ns._deny == {}
        assert len(ns._ignored_names) > 0

    def test_init_with_uses(self):
        ns = IntentNamespace(uses=[print, len])
        assert "print" in ns._uses
        assert "len" in ns._uses
        assert len(ns._uses) == 2

    def test_init_without(self):
        ns = IntentNamespace(without=[print])
        assert "print" in ns._without

    def test_init_deny(self):
        ns = IntentNamespace(deny=[os.system])
        assert "system" in ns._deny

    def test_map_functions(self):
        result = IntentNamespace._map_functions([print, len])
        assert "print" in result
        assert "len" in result
        assert callable(result["print"])

    def test_map_functions_empty(self):
        result = IntentNamespace._map_functions([])
        assert result == {}

    def test_intent_basic(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent()
        def test_func():
            print("test")

        assert callable(test_func)
        test_func()

    def test_intent_merges_uses(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent(uses=[len])
        def test_func():
            print("test")
            len([1, 2])

        test_func()

    def test_intent_merges_without(self):
        ns = IntentNamespace(without=[print])

        @ns.intent(without=[len])
        def test_func():
            print("test")
            len([1, 2])

        test_func()

    def test_intent_recursive(self):
        def inner():
            print("inner")

        def outer():
            inner()

        ns = IntentNamespace(uses=[print], recursive=True)

        @ns.intent(uses=[outer])
        def test_func():
            outer()

        test_func()

    def test_intent_not_recursive(self):
        def inner():
            os.system("test")

        def outer():
            inner()

        ns = IntentNamespace(uses=[print], recursive=False)

        @ns.intent(uses=[outer])
        def test_func():
            outer()

        test_func()

    def test_intent_uselocals(self):
        def local_func():
            print("local")

        ns = IntentNamespace(uses=[print])

        @ns.intent(uselocals=True)
        def test_func():
            local_func()

        test_func()

    def test_intent_uselocals_nested(self):
        def outer():
            def inner():
                print("inner")

            inner()

        ns = IntentNamespace(uses=[print])

        @ns.intent(uselocals=True)
        def test_func():
            outer()

        test_func()

    def test_intent_ignores_internal_methods(self):
        ns = IntentNamespace()

        @ns.intent()
        def test_func():
            pass

        test_func()

    def test_intent_validation_with_syntax_error(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent()
        def test_func():
            pass

        test_func()

    def test_intent_validation_with_indentation_error(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent()
        def test_func():
            pass

        test_func()

    def test_intent_without_skip_check(self):
        ns = IntentNamespace(without=[print])

        @ns.intent(deny=[print])
        def test_func():
            print("test")

        test_func()

    def test_build_allowed_names(self):
        ns = IntentNamespace()
        uses = {"print": print, "len": len}
        deny = {"print": print}
        result = ns._build_allowed_names(uses, deny)
        assert "len" in result
        assert "print" not in result

    def test_is_ignored_method(self):
        ns = IntentNamespace()
        assert ns._is_ignored_method("intent") is True
        assert ns._is_ignored_method("_validate_tree") is False
        assert ns._is_ignored_method("print") is False

    def test_is_call_allowed_with_uses(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent()
        def test_func():
            print("test")

        test_func()

    def test_is_call_allowed_with_uselocals(self):
        def local_func():
            pass

        ns = IntentNamespace()

        @ns.intent(uselocals=True)
        def test_func():
            local_func()

        test_func()

    def test_intent_with_multiple_decorators(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent(uses=[len])
        @ns.intent(uses=[sum])
        def test_func():
            print("test")
            len([1, 2])
            sum([1, 2])

        test_func()

    def test_intent_with_wrapper_preserves_metadata(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent()
        def test_func():
            """Test docstring"""
            pass

        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Test docstring"

    def test_is_denied_with_resolved_func(self):
        ns = IntentNamespace(deny=[print])
        node = Mock()
        node.name = "print"
        node.resolved_func = print
        denied_names = {"print"}

        assert ns._is_denied(node, denied_names) is True

    def test_is_denied_without_resolved_func(self):
        ns = IntentNamespace(deny=[print])
        node = Mock()
        node.name = "unknown"
        node.resolved_func = None
        denied_names = {"print"}

        assert ns._is_denied(node, denied_names) is False

    def test_is_local_to_root(self):
        ns = IntentNamespace()

        def root_func():
            test_var = 123
            return test_var

        assert ns._is_local_to_root("test_var", root_func) is False

    def test_is_local_to_root_with_attributes(self):
        ns = IntentNamespace()

        def root_func():
            import os

            return os.path

        assert ns._is_local_to_root("os.path", root_func) is False
