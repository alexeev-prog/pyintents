<div align="center">
  <h1>pyintents</h1>
  <p><strong>Explicit capabilities and conservative call-policy analysis for Python.</strong></p>
  <a href="https://alexeev-prog.github.io/pyintents/index.html">Explore the docs »</a>
</div>

## Overview

PyIntents offers two complementary tools:

- **`IntentDispatcher`** authorizes access to a fixed registry of trusted handlers,
  checks arguments, and accepts only bounded, plain JSON-like data.
- **`IntentNamespace`** checks statically visible function calls before execution.
  It helps detect accidental policy violations in trusted application code.

**Neither API is a Python sandbox.** Do not run hostile Python in the same process
as your secrets, policy objects, or privileged handlers. Static analysis cannot
prove the complete behavior of arbitrary Python: descriptors, operators,
callbacks, mutable globals, decorators, native extensions, and concurrency all
matter. A decorator can also be bypassed by directly accessing the original
function. Use an OS-isolated worker and a trusted broker for hostile code.

## Installation

```bash
pip install pyintents
```

Python 3.12+ is required. The library has no runtime dependencies.

## Explicit capability dispatch

Use this API when controlling AI tools, plugin requests, or privileged actions.
Construct the registry and grants in trusted code, not from a client's claims.

```python
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

print(dispatcher.dispatch("greeting.create", {"name": "Alice"}))

try:
    dispatcher.dispatch("shell.run", {"command": "anything"})
except IntentViolationError as exc:
    print(f"Blocked: {exc}")
```

### Dispatcher guarantees and responsibilities

- Registry and grants are copied at construction; deny takes precedence.
- No dynamic import, name-to-attribute lookup, `eval`, or `pickle` is used.
- Unknown/ungranted IDs and invalid payloads are rejected before handler execution.
- Handlers and validators must be trusted synchronous functions. Generators and
  coroutine functions are rejected at registration.
- Validators must return **exactly `True`**. Exceptions propagate without invoking
  the handler. Validators should be pure and must enforce resource-level policy:
  allowed file paths, network destinations, operation types, and argument ranges.
- Data is copied into plain `dict`, `list`, `str`, `int`, `float`, `bool`, and
  `None`. Custom objects, subclasses, non-string keys, non-finite floats, and
  integers larger than 4096 bits are rejected. Callable payloads are never accepted.
- Default limits: `max_nodes=10_000`, `max_depth=32`, `max_bytes=1_000_000`.
  Configured `max_depth` cannot exceed 128.
  The string budget uses a conservative four bytes per character. Limits apply
  separately to each copied request/result, not to handler runtime or transport
  allocation. Decode size-limited requests before dispatching.
- The validator receives a separate copy so it cannot rewrite handler arguments.
  Results are checked and copied too. A rejected result **does not roll back** a
  completed side effect. Handler exceptions propagate; dispatch never retries.

The dispatcher is an authorization component, not authentication, scheduling,
an IPC server, rate limiting, persistence, or OS isolation. Keep it in a trusted
process. A child process with the same unrestricted OS privileges is not enough.

## Static call policies

```python
from pyintents import IntentNamespace, IntentViolationError

namespace = IntentNamespace(uses=[print, len])


@namespace.intent()
def allowed():
    print("Allowed")
    return len([1, 2])


def other():
    return 3


@namespace.intent()
def denied():
    return other()


allowed()
try:
    denied()
except IntentViolationError as exc:
    print(f"Blocked: {exc}")
```

### Rules

| Rule | Meaning |
|---|---|
| `uses=[helper]` | Allow precisely this function object, not another object with matching metadata |
| `uses=["package:helper"]` | Match diagnostic module/qualified-name metadata; trusted-code convenience only |
| `uses=["package.helper"]` | Match a dotted call name or normalized metadata |
| `uses=["helper"]` | Match a short call name; deliberately broad |
| `deny=[helper]` | Deny this exact object, including aliases |
| `without=[helper]` | Exempt this call from allowlist checks, but still traverse its body and enforce deny |

Callable instances are not accepted as rules. String rules are not unforgeable
capabilities. Unresolved/dynamic targets cannot be authorized solely by a name;
they require the explicitly unsafe `allow_unknown=True` setting. Default dynamic
primitive denial matches both names and builtin objects, so aliases of `exec`,
`eval`, `getattr`, etc. remain denied even when included in `uses`.

### Settings

```python
IntentNamespace(
    uses=None,
    recursive=True,
    without=None,
    uselocals=False,
    usemodule=False,
    deny=None,
    allow_unknown=False,
    deny_dynamic_primitives=True,
    only_warnings=False,
    strict=True,
    max_nodes=10_000,
    analysis_depth=100,
)
```

- `recursive=True`: traverse statically resolvable child functions.
- `uselocals=True`: allow stable nested definitions; their bodies are still checked.
- `usemodule=True`: allow source-available functions with matching module metadata;
  requires `recursive=True` and is a convenience for trusted modules only.
- `strict=True`: reject unsupported implicit-execution syntax. This includes
  imports, classes, attribute reads outside call targets, subscripts, operators,
  truth tests, loops/comprehensions, context managers, formatting, `await`,
  yields, pattern matching, nested decorators/annotations, and argument unpacking.
  This is intentionally restrictive, **not a sound safe-Python subset**.
- `strict=False`: audit more ordinary Python syntax without claiming that implicit
  calls were checked. Use only with trusted code.
- `allow_unknown=True`, `recursive=False`, and `only_warnings=True` weaken checks.
  Warning mode continues on policy violations, not on parse/budget failures.
- `max_nodes` and `analysis_depth`: bounded graph expansion, with controlled
  `IntentParseError` on exhaustion. Each extracted source is limited to 1,000,000
  characters. No graph cache is used because bindings are mutable.

`@namespace.intent(...)` can add `uses`, `deny`, and `without` and override
`recursive`, `uselocals`, `usemodule`, and `allow_unknown`. Syntax profile and
analysis budgets belong to the namespace and cannot be weakened per decorator.

### Important limitations

Even strict mode does not control behavior inside explicitly allowed opaque
functions. `len(obj)` can invoke `obj.__len__`, `print(obj)` can invoke
`obj.__str__`, and `sorted(..., key=callback)` invokes callbacks. A permitted
function is a trust decision, not a proof that its arguments are safe.

Source is retrieved from the actual code object without following `__wrapped__`.
Source files, linecache, code objects, globals, and policy configuration must all
be trusted. This does not cryptographically bind source text to executable code.
Changing bindings during/after validation is still a time-of-check/time-of-use
problem. Threads, signals, callbacks, and mutations can invalidate a decision.

Async functions preserve coroutine identity and are checked when the coroutine
starts executing, not when it is created. Strict mode rejects `await` in analyzed
bodies. Audit mode cannot protect across suspension points. Generators and async
generators are explicitly unsupported by the decorator.

**There is no ACID/rollback guarantee.** A static precheck does not make filesystem,
network, or database effects transactional. Implement database transactions,
idempotency, and compensation in trusted handlers where applicable.

## Exceptions

All inherit from `IntentError` and are exported from `pyintents`:

- `IntentViolationError`: a forbidden call, capability, or payload.
- `IntentParseError`: unavailable source, unsupported strict syntax, or analysis budget.
- `IntentConfigurationError`: invalid rules, handlers, settings, or function kinds.
- `IntentShadowingError`: assignment/import conflicts with a protected name.

`CallTree`, `CallNode`, `get_calls`, and `SafeResolver` are introspection utilities,
not execution guards. `CallTree` defaults to `strict=False` for inspection.

## Examples and development

Run `uv run python example1.py` for basic policies or
`uv run python example_dispatcher.py` for explicit capabilities. Examples use only
harmless operations and can be run without privileged commands.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
uv run mypy src/pyintents
uv run sphinx-build -W -b html docs /tmp/opencode/pyintents-docs
```

See [the security model](docs/security.rst) and
[migration notes](docs/migration.rst) for the hardening-related compatibility changes.
