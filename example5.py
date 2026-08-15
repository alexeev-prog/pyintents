import os
from pyintents import IntentNamespace
import pprint

main_namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    usemodule=True,
)

print = os.system


@main_namespace.intent()
def func() -> None:
    print("echo Hello")


if __name__ == "__main__":
    try:
        func()
    except Exception as exc:
        pprint.pprint(f"Error: {exc}")
