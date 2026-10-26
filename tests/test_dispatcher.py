import math

import pytest

from pyintents import (
    Capability,
    IntentConfigurationError,
    IntentDispatcher,
    IntentViolationError,
)


@pytest.fixture
def broker():
    effects = []

    def validate(payload):
        return set(payload) == {"text"} and type(payload["text"]) is str

    def handler(payload):
        effects.append(payload["text"])
        return {"echo": payload["text"]}

    return IntentDispatcher(
        {"echo": Capability(handler, validate)}, grants=["echo"]
    ), effects


def test_dispatches_only_validated_data(broker):
    dispatcher, effects = broker
    assert dispatcher.dispatch("echo", {"text": "hello"}) == {"echo": "hello"}
    assert effects == ["hello"]


@pytest.mark.parametrize(
    "name,payload",
    [
        ("unknown", {}),
        ("echo", {}),
        ("echo", {"text": 123}),
        ("echo", {"text": "ok", "extra": True}),
        ("echo", []),
        (123, {}),
    ],
)
def test_denies_before_handler(broker, name, payload):
    dispatcher, effects = broker
    with pytest.raises(IntentViolationError):
        dispatcher.dispatch(name, payload)
    assert not effects


@pytest.mark.parametrize(
    "value", [object(), lambda: None, math.inf, math.nan, 1 << 5000, (1,), {1: "bad"}]
)
def test_rejects_non_plain_data(broker, value):
    with pytest.raises(IntentViolationError):
        broker[0].dispatch("echo", {"text": value})
    assert not broker[1]


def test_does_not_invoke_object_hooks(broker):
    class Hostile(dict):
        def items(self):
            raise AssertionError("items")

        def __repr__(self):
            raise AssertionError("repr")

    with pytest.raises(IntentViolationError):
        broker[0].dispatch("echo", Hostile(text="bad"))


def test_registry_and_grants_are_snapshots():
    registry = {"echo": Capability(lambda p: p, lambda p: True)}
    grants = ["echo"]
    dispatcher = IntentDispatcher(registry, grants=grants, deny=["echo"])
    registry.clear()
    grants.clear()
    with pytest.raises(IntentViolationError):
        dispatcher.dispatch("echo", {})


def test_validator_cannot_rewrite_handler_arguments():
    def validate(payload):
        payload["nested"][0] = "changed"
        return True

    dispatcher = IntentDispatcher(
        {"echo": Capability(lambda p: p, validate)}, grants=["echo"]
    )
    payload = {"nested": ["original"]}
    result = dispatcher.dispatch("echo", payload)
    assert result == payload == {"nested": ["original"]}
    assert result is not payload
    assert result["nested"] is not payload["nested"]


@pytest.mark.parametrize("answer", [None, 1, "yes", [], False])
def test_validator_must_return_exact_true(answer):
    effects = []
    dispatcher = IntentDispatcher(
        {"echo": Capability(lambda p: effects.append(p), lambda p: answer)},
        grants=["echo"],
    )
    with pytest.raises(IntentViolationError):
        dispatcher.dispatch("echo", {})
    assert not effects


@pytest.mark.parametrize(
    "limits,payload",
    [
        ({"max_nodes": 2}, {"x": 1}),
        ({"max_depth": 1}, {"x": [[1]]}),
        ({"max_bytes": 4}, {"x": "long"}),
    ],
)
def test_data_budgets(limits, payload):
    dispatcher = IntentDispatcher(
        {"echo": Capability(lambda p: p, lambda p: True)}, grants=["echo"], **limits
    )
    with pytest.raises(IntentViolationError, match="budget"):
        dispatcher.dispatch("echo", payload)


def test_cycles_rejected():
    payload = {}
    payload["cycle"] = payload
    dispatcher = IntentDispatcher(
        {"echo": Capability(lambda p: p, lambda p: True)}, grants=["echo"]
    )
    with pytest.raises(IntentViolationError, match="budget"):
        dispatcher.dispatch("echo", payload)


def test_invalid_result_does_not_imply_rollback():
    effects = []

    def handler(payload):
        effects.append("done")
        return object()

    dispatcher = IntentDispatcher(
        {"echo": Capability(handler, lambda p: True)}, grants=["echo"]
    )
    with pytest.raises(IntentViolationError):
        dispatcher.dispatch("echo", {})
    assert effects == ["done"]


def test_exceptions_propagate_without_retry():
    effects = []

    def handler(payload):
        effects.append("once")
        raise RuntimeError("handler failure")

    dispatcher = IntentDispatcher(
        {"echo": Capability(handler, lambda p: True)}, grants=["echo"]
    )
    with pytest.raises(RuntimeError, match="handler failure"):
        dispatcher.dispatch("echo", {})
    assert effects == ["once"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"grants": "echo"},
        {"grants": ["missing"]},
        {"grants": [], "deny": ["missing"]},
        {"grants": [], "max_nodes": 0},
        {"grants": [], "max_depth": True},
    ],
)
def test_invalid_dispatcher_configuration(kwargs):
    with pytest.raises(IntentConfigurationError):
        IntentDispatcher({"echo": Capability(lambda p: p, lambda p: True)}, **kwargs)


def test_async_handlers_rejected():
    async def handler(payload):
        return payload

    with pytest.raises(IntentConfigurationError):
        Capability(handler, lambda p: True)


@pytest.mark.parametrize("name", ["", "a" * 129])
def test_request_id_length_rejected(broker, name):
    with pytest.raises(IntentViolationError):
        broker[0].dispatch(name, {})


@pytest.mark.parametrize("name", ["", "1bad", "with space", "écho", "x" * 129])
def test_invalid_registered_id(name):
    with pytest.raises(IntentConfigurationError):
        IntentDispatcher({name: Capability(lambda p: p, lambda p: True)}, grants=[])


def test_depth_budget_cannot_exceed_stack_safe_limit():
    with pytest.raises(IntentConfigurationError):
        IntentDispatcher({}, grants=[], max_depth=129)


def test_plain_data_roundtrip():
    dispatcher = IntentDispatcher(
        {"echo": Capability(lambda p: p, lambda p: True)}, grants=["echo"]
    )
    payload = {"all": [None, True, False, 42, -1, 1.5, "hello", {}]}
    assert dispatcher.dispatch("echo", payload) == payload


def test_validator_exception_never_invokes_handler():
    effects = []

    def validate(payload):
        raise ValueError("invalid resource")

    dispatcher = IntentDispatcher(
        {"echo": Capability(lambda p: effects.append(p), validate)}, grants=["echo"]
    )
    with pytest.raises(ValueError):
        dispatcher.dispatch("echo", {})
    assert not effects
