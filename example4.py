from pyintents import IntentNamespace

main_namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    usemodule=True,
)


@main_namespace.intent()
def func() -> None:
    from os import system as print

    print("echo Hello")


if __name__ == "__main__":
    try:
        func()
    except Exception as exc:
        print(f"Error: {exc}")
