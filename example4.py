"""Strict mode rejects imports instead of executing module initialization."""

from pyintents import IntentError, IntentNamespace

namespace = IntentNamespace()


@namespace.intent()
def func():
    import math

    return math.pi


if __name__ == "__main__":
    try:
        func()
    except IntentError as exc:
        print(f"Blocked: {exc}")
