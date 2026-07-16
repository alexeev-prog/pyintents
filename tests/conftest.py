# tests/conftest.py
import pytest

from pyintents.namespace import IntentNamespace


@pytest.fixture
def basic_namespace():
    return IntentNamespace(uses=[print])


@pytest.fixture
def recursive_namespace():
    return IntentNamespace(uses=[print], recursive=True)


@pytest.fixture
def strict_namespace():
    return IntentNamespace()


@pytest.fixture
def sample_function():
    def func():
        print("Hello")
        return 42

    return func


@pytest.fixture
def nested_function():
    def inner():
        print("Inner")

    def outer():
        print("Outer")
        inner()

    return outer


@pytest.fixture
def function_with_import():
    def func():
        import os

        os.system("test")

    return func
