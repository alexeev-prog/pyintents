<div align="center">
  <p align="center">
    <h1>pyintents</h1>
    <p><strong>Declarative capability-based access control for Python functions.</strong></p>
    <a href="https://alexeev-prog.github.io/pyintents/v0.2.0"><strong>Explore the docs »</strong></a>
  </p>
  <p align="center">
    <a href="#-getting-started">Getting Started</a>
    ·
    <a href="#-basic-usage">Basic Usage</a>
    ·
    <a href="https://alexeev-prog.github.io/pyintents/main">Latest Documentation</a>
    ·
    <a href="https://github.com/alexeev-prog/pyintents/blob/main/LICENSE">License</a>
  </p>
</div>

<hr>

<p align="center">
  <img src="https://img.shields.io/github/languages/top/alexeev-prog/pyintents?style=for-the-badge">
  <img src="https://img.shields.io/github/languages/count/alexeev-prog/pyintents?style=for-the-badge">
  <img src="https://img.shields.io/badge/Maintained-yes-green.svg?style=for-the-badge">
  <img alt="GitHub License" src="https://img.shields.io/github/license/alexeev-prog/pyintents?style=for-the-badge&logo=gnu">
  <img alt="GitHub forks" src="https://img.shields.io/github/forks/alexeev-prog/pyintents?style=for-the-badge&logo=github">
  <img src="https://img.shields.io/github/stars/alexeev-prog/pyintents?style=for-the-badge">
  <img src="https://img.shields.io/github/issues/alexeev-prog/pyintents?style=for-the-badge">
  <img src="https://img.shields.io/github/last-commit/alexeev-prog/pyintents?style=for-the-badge">
  <img alt="GitHub commits since latest release" src="https://img.shields.io/github/commits-since/alexeev-prog/pyintents/latest?style=for-the-badge">
  <img alt="GitHub Release Date" src="https://img.shields.io/github/release-date-pre/alexeev-prog/pyintents?style=for-the-badge">
  <img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/alexeev-prog/pyintents/docs.yml?style=for-the-badge&logo=github&label=docs">
  <img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/alexeev-prog/pyintents/python-package.yml?style=for-the-badge&logo=python&label=python%20package%20lint">
  <img src="https://img.shields.io/pypi/wheel/pyintents?style=for-the-badge">
  <img alt="PyPI - Downloads" src="https://img.shields.io/pypi/dm/pyintents?style=for-the-badge">
  <img alt="PyPI - Version" src="https://img.shields.io/pypi/v/pyintents?style=for-the-badge">
  <img alt="GitHub contributors" src="https://img.shields.io/github/contributors/alexeev-prog/pyintents?style=for-the-badge">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/alexeev-prog/pyintents/refs/heads/main/docs/pallet-0.png">
</p>

---

## 📖 Overview

**PyIntents** brings capability-based security to Python.

Functions declare what they are allowed to do through an `@intent` decorator, and PyIntents enforces these permissions at call time. You define namespaces with allow and deny rules, recursively validate call chains, exempt trusted helpers when needed, and keep unknown or dynamic behavior blocked by default.

PyIntents is useful for:

- plugin sandboxes;
- AI agent tool control;
- environment-specific security policies;
- testing and dependency isolation;
- security audits and explicit capability boundaries.

> **Trust explicitly. Fail safely.**

PyIntents is not a full operating-system-level sandbox. It is a declarative policy layer for Python functions. For strong isolation of untrusted code, combine it with process isolation, containers, WASM, or a dedicated sandboxing solution.

---

## 🚀 Getting Started

### Installation

```bash
pip install pyintents
```

Python 3.12+ is recommended.

---

### Quick Example

```python
from pyintents import IntentNamespace

# Allow only print()
namespace = IntentNamespace(uses=[print])


@namespace.intent()
def safe_function():
    print("This is allowed")  # OK


@namespace.intent()
def unsafe_function():
    import os
    os.system("echo bad")  # IntentViolationError
```

By default, PyIntents validates the function **before execution**.

If a forbidden or unknown call is found anywhere in the statically visible call chain, the decorated function is not executed.

---

## 🛡️ Basic Usage

### 1. Allow Specific Functions

```python
from pyintents import IntentNamespace

namespace = IntentNamespace(uses=[print, len])


@namespace.intent()
def my_func():
    print("Hello")   # Allowed
    return len([1])  # Allowed
```

---

### 2. Recursive Enforcement

Recursive validation is enabled by default.

```python
namespace = IntentNamespace(uses=[print])


def helper():
    print("Inside helper")


@namespace.intent(uses=[helper])
def main():
    helper()
```

PyIntents checks not only `main`, but also what `helper` calls.

---

### 3. Allow Functions From the Same Module

If your module has many internal helper functions, allowing each one manually can be tedious.

Use `usemodule=True`:

```python
namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    usemodule=True,
)


def inner():
    print("Inner")


def outer():
    print("Outer")
    inner()


@namespace.intent()
def func():
    outer()
```

With `usemodule=True`:

- functions defined in the same module as the decorated function are allowed;
- their calls are still recursively validated;
- functions from other modules are not automatically allowed.

`usemodule` requires `recursive=True`.

---

### 4. Allow Local Nested Functions

`uselocals=True` allows functions defined inside the decorated function.

```python
namespace = IntentNamespace(
    uses=[print],
    uselocals=True,
)


@namespace.intent()
def main():
    def local_helper():
        print("Local helper")

    local_helper()
```

Important:

- `uselocals=True` allows nested local functions;
- it does **not** automatically allow module-level global functions.

For module-level helpers, use `usemodule=True` or explicit `uses=[...]`.

---

### 5. Exempt Trusted Functions From Allowlist Checks

`without` exempts a function from allowlist checks, but deny rules are still enforced.

```python
def helper():
    print("OK")


namespace = IntentNamespace(
    uses=[print],
    without=[helper],
)


@namespace.intent()
def main():
    helper()
```

Important:

`without` does not mean “ignore everything inside this function forever”.

It means:

- this function does not need to be explicitly allowed by `uses`;
- but forbidden calls inside it can still be rejected.

---

### 6. Explicit Denial

```python
import os

from pyintents import IntentNamespace

namespace = IntentNamespace(
    uses=[print],
    deny=[os.system],
)


@namespace.intent()
def restricted():
    print("OK")
    os.system("echo bad")  # Explicitly denied
```

You can also use string rules:

```python
namespace = IntentNamespace(
    uses=[print],
    deny=["os.system"],
)
```

---

### 7. Runtime Layering

Decorator-level rules extend or override namespace-level rules.

```python
base = IntentNamespace(uses=[print])


@base.intent(uses=[len])
def layered_func():
    print("Hi")
    return len("world")
```

---

### 8. Unknown and Dynamic Calls Are Blocked by Default

PyIntents is fail-closed by default.

Unknown calls are denied unless explicitly allowed or unless `allow_unknown=True` is set.

Dynamic primitives such as:

```python
eval
exec
compile
__import__
getattr
setattr
delattr
globals
locals
vars
breakpoint
```

are denied by default.

You can disable this behavior with:

```python
IntentNamespace(deny_dynamic_primitives=False)
```

but this is discouraged.

---

## 📦 API Reference

### `IntentNamespace`

```python
IntentNamespace(
    uses=None,
    *,
    recursive=True,
    without=None,
    uselocals=False,
    usemodule=False,
    deny=None,
    allow_unknown=False,
    deny_dynamic_primitives=True,
)
```

| Parameter | Type | Default | Description |
|---|---|---:|---|
| `uses` | `Iterable[Callable or str]` | `None` | Explicitly allowed functions or names |
| `recursive` | `bool` | `True` | Recursively validate called functions |
| `without` | `Iterable[Callable or str]` | `None` | Exempt from allowlist checks only |
| `uselocals` | `bool` | `False` | Allow nested functions defined inside the decorated function |
| `usemodule` | `bool` | `False` | Allow functions from the same module. Requires `recursive=True` |
| `deny` | `Iterable[Callable or str]` | `None` | Explicitly forbidden functions or names |
| `allow_unknown` | `bool` | `False` | Allow unresolved or opaque calls |
| `deny_dynamic_primitives` | `bool` | `True` | Deny dynamic primitives like `eval`, `exec`, `getattr`, etc. |

---

### `@namespace.intent()`

Overrides or extends namespace settings per function.

```python
@namespace.intent(
    uses=[print],
    recursive=True,
    without=[helper],
    uselocals=True,
    usemodule=True,
    deny=[os.system],
    allow_unknown=False,
)
def custom_func():
    pass
```

---

## ⚠️ Exceptions

### `IntentViolationError`

Raised when a function violates declared permissions.

```python
from pyintents import IntentNamespace, IntentViolationError

namespace = IntentNamespace(uses=[print])


@namespace.intent()
def bad():
    import os
    os.system("echo bad")


try:
    bad()
except IntentViolationError as exc:
    print(exc)
```

---

### `IntentParseError`

Raised when function source code is unavailable or cannot be parsed.

```python
from pyintents.exceptions import IntentParseError
```

---

### `IntentConfigurationError`

Raised when namespace or decorator configuration is invalid.

```python
from pyintents.exceptions import IntentConfigurationError
```

---

## 🔧 How It Works

PyIntents performs static policy validation before the decorated function is executed.

The pipeline is:

1. **AST Parsing**
   PyIntents parses the function source code using Python's `ast` module.

2. **Call Graph Construction**
   It builds a tree of statically visible function calls.

3. **Safe Resolution**
   Call names are resolved to actual function objects when possible.

4. **Rule Matching**
   Each call is validated against:
   - `uses`;
   - `deny`;
   - `without`;
   - `uselocals`;
   - `usemodule`;
   - unknown-call policy;
   - dynamic-primitive policy.

5. **Pre-Execution Enforcement**
   If a violation is found, the decorated function is not executed.

Example:

```text
func -> outer -> inner -> os.system
```

If `os.system` is forbidden or unknown, PyIntents blocks the root call to `func` before any code inside `func` runs.

---

## 🧠 Security Model

PyIntents follows a fail-closed model.

By default:

- only explicitly allowed calls are permitted;
- recursive validation is enabled;
- unknown calls are denied;
- dynamic primitives are denied;
- functions without available source code are treated carefully;
- violations prevent execution.

### Pre-Execution Validation

PyIntents validates the call chain before execution.

This means:

```python
@namespace.intent()
def func():
    print("Func")
    outer()
```

If `outer` eventually calls something forbidden, `func` will not execute at all.

This is intentional.

It prevents partially executed functions from producing side effects before a violation is detected.

---

## ⚠️ Limitations

PyIntents is a static and runtime policy layer, not a complete sandbox.

Python is highly dynamic, so some behavior cannot be fully analyzed statically.

Examples:

```python
getattr(os, "system")("echo bad")
eval("os.system('echo bad')")
globals()["os"].system("echo bad")
```

PyIntents mitigates many of these cases by denying dynamic primitives by default, but no AST-only solution can guarantee complete isolation.

For strong security boundaries, use:

- subprocesses;
- containers;
- seccomp;
- WASM;
- RestrictedPython;
- custom import hooks;
- runtime monitoring.

---

## 🎯 Use Cases

| Use Case | Description |
|---|---|
| Plugin Sandboxes | Restrict what third-party plugins can do |
| AI Agent Control | Limit tool access for LLM agents |
| Environment Policies | Enforce different rules per environment |
| Testing | Isolate unit tests from external dependencies |
| Security Audits | Document and enforce capability boundaries |
| Internal APIs | Prevent accidental access to dangerous helpers |

---

## 📚 Documentation

- [Latest Documentation](https://alexeev-prog.github.io/pyintents/main)
- [Version 0.2.2](https://alexeev-prog.github.io/pyintents/v0.2.2)
- [GitHub Repository](https://github.com/alexeev-prog/pyintents)

---

## 📄 License

Licensed under the GNU General Public License v3.0.

See [LICENSE](https://github.com/alexeev-prog/pyintents/blob/main/LICENSE) for details.

---

## 🤝 Contributing

Contributions are welcome.

Feel free to:

- open issues;
- submit pull requests;
- suggest features;
- improve documentation;
- report security concerns.

---

## 🌟 Support

If you find PyIntents useful, consider:

- ⭐ starring the repository on GitHub;
- 🐛 reporting issues;
- 💡 suggesting features;
- 📖 improving documentation.

<p align="center">
  <i>Trust explicitly. Fail safely.</i>
</p>

<p align="right">
  <a href="#readme-top">↑ Back to top</a>
</p>
