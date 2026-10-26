"""Parameter shadowing cannot substitute an allowed global function."""

from pyintents import IntentError, IntentNamespace


def safe():
    return "Allowed"


def forbidden():
    return "Not allowed"


namespace = IntentNamespace(uses=[safe])


@namespace.intent()
def func(safe):
    return safe()


if __name__ == "__main__":
    try:
        func(forbidden)
    except IntentError as exc:
        print(f"Blocked: {exc}")
