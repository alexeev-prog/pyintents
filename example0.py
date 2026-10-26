"""Recursive policy validation, using harmless denied functions."""

from pyintents import IntentError, IntentNamespace

main_namespace = IntentNamespace(uses=[print], usemodule=True, deny=["forbidden"])


def forbidden():
    return "This call must not run"


def inner():
    return forbidden()


def outer():
    print("Outer")
    inner()


@main_namespace.intent()
def func():
    print("Func")
    outer()


if __name__ == "__main__":
    try:
        func()
    except IntentError as exc:
        print(f"Blocked before printing Func: {exc}")
