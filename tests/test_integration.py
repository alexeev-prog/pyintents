# tests/test_integration.py
import os

import pytest

from pyintents import IntentNamespace


class TestIntegrationScenarios:
    def test_complete_workflow(self):
        ns = IntentNamespace(uses=[print], recursive=True)

        def inner():
            print("Inner")

        def outer():
            print("Outer")
            inner()

        @ns.intent(uses=[outer])
        def func():
            print("Func")
            outer()

        func()

    def test_without_overrides_all(self):
        ns = IntentNamespace(uses=[print], recursive=True)

        def inner():
            os.system("echo Inner")

        @ns.intent(without=[inner])
        def func():
            inner()

        func()

    def test_complex_nested_calls(self):
        ns = IntentNamespace(uses=[print, len], recursive=True)

        def level3():
            print("Level3")
            len([1, 2])

        def level2():
            print("Level2")
            level3()

        def level1():
            print("Level1")
            level2()

        @ns.intent(uses=[level1])
        def func():
            level1()

        func()

    def test_recursive_function_detection(self):
        ns = IntentNamespace(uses=[print], recursive=True)

        def recursive():
            print("Recursive")
            recursive()

        @ns.intent(uses=[recursive])
        def func():
            recursive()

        with pytest.raises(RecursionError):
            func()

    def test_method_calls_in_class(self):
        ns = IntentNamespace(uses=[print], recursive=True)

        class TestClass:
            def method1(self):
                print("Method1")

            def method2(self):
                self.method1()
                print("Method2")

        obj = TestClass()

        @ns.intent(uses=[obj.method2])
        def func():
            obj.method2()

        func()

    def test_static_method_calls(self):
        ns = IntentNamespace(uses=[print], recursive=True)

        class TestClass:
            @staticmethod
            def static_method():
                print("Static")

        @ns.intent(uses=[TestClass.static_method])
        def func():
            TestClass.static_method()

        func()

    def test_class_method_calls(self):
        ns = IntentNamespace(uses=[print], recursive=True)

        class TestClass:
            @classmethod
            def class_method(cls):
                print("Class")

        @ns.intent(uses=[TestClass.class_method])
        def func():
            TestClass.class_method()

        func()

    def test_builtin_functions_usage(self):
        ns = IntentNamespace(uses=[print, len, sum, max, min], recursive=True)

        @ns.intent()
        def func():
            print("Test")
            len([1, 2, 3])
            sum([1, 2, 3])
            max([1, 2, 3])
            min([1, 2, 3])

        func()

    def test_multiple_intent_decorators(self):
        ns1 = IntentNamespace(uses=[print])
        ns2 = IntentNamespace(uses=[len])

        @ns1.intent()
        @ns2.intent()
        def func():
            print("test")
            len([1, 2])

        func()

    def test_dynamic_function_creation(self):
        ns = IntentNamespace(uses=[print])

        def create_func():
            def dynamic():
                print("Dynamic")

            return dynamic

        func = create_func()
        wrapped = ns.intent()(func)

        wrapped()

    def test_lambda_functions(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent()
        def func():
            lambda x: print(x)

        func()

    def test_decorator_with_args(self):
        ns = IntentNamespace(uses=[print])

        @ns.intent(uses=[len], recursive=True)
        def func():
            print("test")
            len([1, 2])

        func()
