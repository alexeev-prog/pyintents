import os

from pyintents import IntentNamespace

main_namespace = IntentNamespace(uses=[print], recursive=True)


def inner():
    os.system("echo Inner")


def outer():
    print("Outer")
    inner()


@main_namespace.intent(uselocals=True)
def func():
    print("Func")
    outer()


func()
