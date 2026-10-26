"""Trusted capability registry: no dynamic function lookup or shell access."""

from pyintents import Capability, IntentDispatcher, IntentViolationError


def validate_greeting(payload):
    return (
        set(payload) == {"name"}
        and type(payload["name"]) is str
        and 0 < len(payload["name"]) <= 80
    )


def greet(payload):
    return {"message": f"Hello, {payload['name']}!"}


dispatcher = IntentDispatcher(
    {"greeting.create": Capability(greet, validate_greeting)},
    grants=["greeting.create"],
)


if __name__ == "__main__":
    print(dispatcher.dispatch("greeting.create", {"name": "Alice"}))

    for name, payload in [
        ("shell.run", {"command": "not available"}),
        ("greeting.create", {"name": 123}),
    ]:
        try:
            dispatcher.dispatch(name, payload)
        except IntentViolationError as exc:
            print(f"Blocked: {exc}")
