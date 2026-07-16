# tests/test_introspect.py
import builtins
from unittest.mock import patch

from pyintents.introspect import CallNode, CallTree, get_calls


def sample_function():
    print("Hello")
    len([1, 2, 3])
    return sum([1, 2, 3])


def recursive_function():
    recursive_function()
    print("Recursive")


class TestClass:
    def method(self):
        print("Method")
        return self

    @staticmethod
    def static_method():
        print("Static")


def function_with_attributes():
    import os

    os.system("echo test")
    os.path.join("a", "b")


def function_with_nested_calls():
    def inner():
        print("Inner")

    inner()
    print("Outer")


class TestGetCalls:
    def test_get_calls_basic(self):
        calls = get_calls(sample_function)
        assert "print" in calls
        assert "len" in calls
        assert "sum" in calls
        assert len(calls) == 3

    def test_get_calls_with_attributes(self):
        calls = get_calls(function_with_attributes)
        assert "os.system" in calls
        assert "os.path.join" in calls

    def test_get_calls_nested(self):
        calls = get_calls(function_with_nested_calls)
        assert "inner" in calls
        assert "print" in calls

    def test_get_calls_no_source(self):
        def dynamic_func():
            pass

        with patch("inspect.getsource", side_effect=OSError):
            calls = get_calls(dynamic_func)
        assert calls == []

    def test_get_calls_syntax_error(self):
        def invalid_func():
            pass

        with patch("inspect.getsource", return_value="invalid python !@#$"):
            calls = get_calls(invalid_func)
        assert calls == []

    def test_get_calls_builtin(self):
        calls = get_calls(print)
        assert calls == []


class TestCallNode:
    def test_call_node_creation(self):
        node = CallNode(name="test")
        assert node.name == "test"
        assert node.calls == []
        assert node.parent is None
        assert node.source is None
        assert node.resolved_func is None
        assert node.is_local is False

    def test_call_node_with_parent(self):
        parent = CallNode(name="parent")
        child = CallNode(name="child", parent=parent)
        assert child.parent == parent

    def test_call_node_repr(self):
        node = CallNode(name="root")
        child1 = CallNode(name="child1")
        child2 = CallNode(name="child2")
        node.calls.extend([child1, child2])

        repr_str = node.__repr__()
        assert "root" in repr_str
        assert "child1" in repr_str
        assert "child2" in repr_str

    def test_call_node_repr_nested(self):
        root = CallNode(name="root")
        child = CallNode(name="child")
        grandchild = CallNode(name="grandchild")
        child.calls.append(grandchild)
        root.calls.append(child)

        repr_str = root.__repr__()
        assert "root" in repr_str
        assert "child" in repr_str
        assert "grandchild" in repr_str

    def test_call_node_equality(self):
        node1 = CallNode(name="test")
        node2 = CallNode(name="test")
        node3 = CallNode(name="different")

        assert node1 == node2
        assert node1 != node3
        assert node1 != "string"

    def test_call_node_equality_with_parent(self):
        parent1 = CallNode(name="parent")
        parent2 = CallNode(name="parent")
        node1 = CallNode(name="child", parent=parent1)
        node2 = CallNode(name="child", parent=parent2)

        assert node1 == node2


class TestCallTree:
    def test_call_tree_creation(self):
        tree = CallTree(sample_function, max_depth=1)
        assert tree.root is not None
        assert tree.root.name == "sample_function"

    def test_call_tree_max_depth_zero(self):
        tree = CallTree(sample_function, max_depth=0)
        assert tree.root is not None
        assert len(tree.root.calls) == 0

    def test_call_tree_max_depth_negative(self):
        tree = CallTree(sample_function, max_depth=-1)
        assert tree.max_depth == 0

    def test_call_tree_cyclic_detection(self):
        def func_a():
            func_b()

        def func_b():
            func_a()

        tree = CallTree(func_a, max_depth=5)
        assert tree.root is not None

    def test_call_tree_resolve_function(self):
        tree = CallTree(sample_function)
        func = tree._resolve_function("print", sample_function)
        assert func is not None
        assert callable(func)

    def test_call_tree_resolve_function_builtin(self):
        tree = CallTree(sample_function)
        func = tree._resolve_function("len", sample_function)
        assert func is builtins.len

    def test_call_tree_resolve_function_not_found(self):
        tree = CallTree(sample_function)
        func = tree._resolve_function("nonexistent", sample_function)
        assert func is None

    def test_call_tree_resolve_function_attribute(self):
        tree = CallTree(sample_function)
        func = tree._resolve_function("sys.exit", sample_function)

    def test_call_tree_is_local_function(self):
        tree = CallTree(sample_function)
        result = tree._is_local_function("print", sample_function)
        assert result is False

    def test_call_tree_with_class_method(self):
        obj = TestClass()
        tree = CallTree(obj.method)
        assert tree.root is not None

    def test_call_tree_with_static_method(self):
        tree = CallTree(TestClass.static_method)
        assert tree.root is not None

    def test_call_tree_resolved_func_attribute(self):
        def func():
            print("test")

        tree = CallTree(func)
        assert tree.root.resolved_func is not None
        assert callable(tree.root.resolved_func)
