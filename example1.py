"""Basic PyIntents example."""

from pyintents import IntentNamespace, IntentViolationError

namespace = IntentNamespace(
    uses=[print],
    recursive=True,
)


@namespace.intent()
def safe_function() -> None:
    print("This is allowed")


@namespace.intent()
def unsafe_function() -> None:
    other_function()


def other_function():
    return "Not allowed"


if __name__ == "__main__":
    safe_function()

    try:
        unsafe_function()
    except IntentViolationError as exc:
        print(f"Blocked: {exc}")
