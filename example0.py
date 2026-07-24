import os

from pyintents import IntentNamespace

main_namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    usemodule=True,
)


def inner() -> None:
    os.system("echo Inner")


def outer() -> None:
    print("Outer")
    inner()


@main_namespace.intent()
def func() -> None:
    print("Func")
    outer()


if __name__ == "__main__":
    try:
        func()
    except Exception as exc:
        print(f"Error: {exc}")
