"""Example with safe local nested functions."""

from pyintents import IntentNamespace, IntentViolationError

namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    uselocals=True,
)


@namespace.intent()
def ok_function() -> None:
    def local_helper() -> None:
        print("Local helper is allowed")

    local_helper()


@namespace.intent()
def bad_function() -> None:
    def local_helper() -> None:
        import os

        os.system("echo This should be blocked")

    local_helper()


if __name__ == "__main__":
    ok_function()

    try:
        bad_function()
    except IntentViolationError as exc:
        print(f"Blocked: {exc}")
