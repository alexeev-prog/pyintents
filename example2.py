"""Example with safe local nested functions."""

from pyintents import IntentError, IntentNamespace

namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    uselocals=True,
)


@namespace.intent()
def ok_function() -> None:
    def local_helper():
        print("Local helper is allowed")

    local_helper()


@namespace.intent()
def bad_function() -> None:
    def local_helper():
        return eval("1")

    local_helper()


if __name__ == "__main__":
    ok_function()

    try:
        bad_function()
    except IntentError as exc:
        print(f"Blocked: {exc}")
