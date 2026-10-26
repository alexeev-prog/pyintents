"""Replacing an allowed global is rejected by object-identity rules."""

from pyintents import IntentError, IntentNamespace


def safe():
    return "Allowed"


def forbidden():
    return "Not allowed"


namespace = IntentNamespace(uses=[safe])


@namespace.intent()
def func():
    return safe()


if __name__ == "__main__":
    safe = forbidden
    try:
        func()
    except IntentError as exc:
        print(f"Blocked: {exc}")
