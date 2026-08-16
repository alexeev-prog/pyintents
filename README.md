<div align="center">
  <p align="center">
    <h1>pyintents</h1>
    <p><strong>Declarative capability-based access control for Python functions.</strong></p>
    <a href="https://alexeev-prog.github.io/pyintents/index.html"><strong>Explore the docs »</strong></a>
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

## Overview

PyIntents brings capability-based security to Python through declarative intents.

The library allows functions to explicitly declare what they are allowed to do using an `@intent` decorator. PyIntents enforces these permissions at call time by performing static analysis on the function's source code and its entire call graph. It validates every call in the chain against the declared policy before any code is executed.

This approach provides a fail-closed security model: by default, anything not explicitly allowed is denied. Dynamic primitives such as `eval`, `exec`, `getattr`, and `globals` are blocked by default. Unknown or unresolvable calls are treated as violations unless explicitly permitted.

PyIntents is useful for:
- Plugin systems and sandboxes
- AI agent tool control and capability restriction
- Environment-specific security policies
- Testing and dependency isolation
- Security audits and explicit capability boundaries

> Trust explicitly. Fail safely.

PyIntents is not a full operating-system-level sandbox. It is a declarative policy layer for Python functions. For strong isolation of untrusted code, combine it with process isolation, containers, WASM, or a dedicated sandboxing solution.

---

## Architecture

PyIntents consists of three main components:

### 1. Introspection Module (`introspect.py`)

This module is responsible for parsing source code and extracting call information.

- `_get_function_ast()` retrieves the AST of a function using `inspect.getsource()` and `ast.parse()`. If source code is unavailable, it raises `IntentParseError`.
- `_OuterCallCollector` is an AST visitor that traverses the function body and collects:
  - Call locations (`CallLocation`) with target name, line number, and dynamic flag
  - Local function definitions for deferred analysis
  - Shadowing protection to prevent assignment to protected names
- `_format_target()` converts AST call expressions to textual representations and detects dynamic calls.
- `SafeResolver` resolves dotted names to callable objects without executing descriptors or properties. It uses `inspect.getattr_static()` and validates intermediate objects as modules or classes.

### 2. Call Graph Construction (`CallTree`)

`CallTree` builds a directed graph of function calls.

- `CallNode` represents a node in the call graph, storing identity, call name, resolved function reference, position, and state flags (`is_local_definition`, `is_dynamic`, `is_unresolved`, `is_source_available`, `is_cycle`).
- `CallTree` recursively traverses calls up to a configurable depth.
- Local functions are analyzed when called within the parent scope.
- External functions are resolved through `SafeResolver`.
- Cycle detection prevents infinite recursion during traversal.

### 3. Policy Engine (`namespace.py`)

`IntentNamespace` defines and enforces security policies.

- `IntentNamespace.__init__()` configures the policy with parameters:
  - `uses`: allowlist of permitted functions
  - `deny`: blocklist of forbidden functions
  - `without`: exempt from allowlist checks
  - `recursive`: enable recursive validation
  - `uselocals`: allow local nested functions
  - `usemodule`: allow functions from the same module
  - `allow_unknown`: permit unresolved or dynamic calls
  - `deny_dynamic_primitives`: block dynamic primitives by default
  - `only_warnings`: emit warnings instead of raising exceptions
- `RuleSet` normalizes rules into four forms: objects, identities (`module:qualname`), full names (`module.qualname`), and short names.
- `@namespace.intent()` decorator wraps functions and validates them on each call.
- `_validate_tree()` traverses the call graph and checks each node against the policy.

### 4. Exceptions (`exceptions.py`)

- `IntentError`: base exception class
- `IntentViolationError`: raised when a function violates declared permissions
- `IntentParseError`: raised when source code cannot be parsed
- `IntentConfigurationError`: raised for invalid configuration
- `IntentShadowingError`: raised when a protected name is shadowed in local scope

---

## Getting Started

### Installation

```bash
pip install pyintents
```

Python 3.12+ is recommended.

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

By default, PyIntents validates the function before execution. If a forbidden or unknown call is found anywhere in the statically visible call chain, the decorated function is not executed.

---

## Basic Usage

### 1. Allow Specific Functions

```python
from pyintents import IntentNamespace

namespace = IntentNamespace(uses=[print, len])


@namespace.intent()
def my_func():
    print("Hello")   # Allowed
    return len([1])  # Allowed
```

Rules can be specified as callable objects or strings:

```python
namespace = IntentNamespace(uses=["print", "len"])
```

### 2. Recursive Enforcement

Recursive validation is enabled by default. PyIntents checks not only the decorated function but also every function it calls, and every function those call, and so on.

```python
namespace = IntentNamespace(uses=[print])


def helper():
    print("Inside helper")


@namespace.intent(uses=[helper])
def main():
    helper()
```

`helper` is validated recursively. If `helper` called `os.system`, the violation would be detected.

### 3. Allow Functions From the Same Module

If your module has many internal helper functions, allowing each one manually can be tedious. Use `usemodule=True`:

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
- Functions defined in the same module as the decorated function are automatically allowed
- Their calls are still recursively validated
- Functions from other modules are not automatically allowed
- `usemodule` requires `recursive=True`

### 4. Allow Local Nested Functions

`uselocals=True` allows functions defined inside the decorated function:

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
- `uselocals=True` allows nested local functions as call targets
- It does not automatically allow module-level global functions
- The contents of local functions are still validated recursively

For module-level helpers, use `usemodule=True` or explicit `uses=[...]`.

### 5. Exempt Trusted Functions From Allowlist Checks

`without` exempts a function from allowlist checks, but deny rules are still enforced:

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

Important: `without` does not mean "ignore everything inside this function forever." It means:
- This function does not need to be explicitly allowed by `uses`
- Forbidden calls inside it can still be rejected
- The function's body is still recursively validated

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

Deny rules have priority over allow rules. If a function appears in both `uses` and `deny`, it is denied.

### 7. Runtime Layering

Decorator-level rules extend or override namespace-level rules:

```python
base = IntentNamespace(uses=[print])


@base.intent(uses=[len])
def layered_func():
    print("Hi")
    return len("world")
```

The decorated function inherits `print` from the namespace and adds `len` as an additional allowed call.

### 8. Unknown and Dynamic Calls Are Blocked by Default

PyIntents is fail-closed by default. Unknown calls are denied unless explicitly allowed.

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
but this is discouraged as it weakens security.

### 9. Warning Mode

Use `only_warnings=True` to emit warnings instead of raising exceptions:

```python
import warnings
warnings.simplefilter("always")

namespace = IntentNamespace(
    uses=[print],
    only_warnings=True,
)


def helper():
    import os
    os.system("echo warning")


@namespace.intent()
def func():
    print("Hello")
    helper()


func()  # Executes but prints a warning about os.system
```

This is useful for auditing existing codebases before enforcing strict policies.

### 10. Override Namespace Defaults Per Function

```python
namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    usemodule=False,
)


@namespace.intent(
    usemodule=True,
    allow_unknown=True,
)
def custom():
    pass
```

---

## Rule Specification

Rules can be specified in several formats:

| Format | Example | Description |
|--------|---------|-------------|
| Callable object | `print` | Direct function reference |
| String with colon | `"builtins:print"` | Module:qualname identity |
| Dotted string | `"os.system"` | Full module.attribute name |
| Bare string | `"system"` | Short name (least precise) |

When a string rule contains a colon, it is treated as an identity (`module:qualname`). When it contains a dot but no colon, it is treated as a full name (`module.qualname`). Otherwise, it is treated as a short name.

### Matching Priority

Rules are matched in the following order:
1. Object reference (requires hashable callable)
2. Identity (`module:qualname`)
3. Full name (`module.qualname`)
4. Short name (last part after dot)

This priority ensures precise matching when available and fallback matching for convenience.

---

## Exceptions

### IntentViolationError

Raised when a function violates declared permissions:

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
    print(exc)  # Function 'bad' calls forbidden 'os.system'
```

The exception includes the full call path, e.g., `Function 'func -> outer -> inner' calls forbidden 'os.system'`.

### IntentParseError

Raised when function source code is unavailable or cannot be parsed:

```python
from pyintents.exceptions import IntentParseError
```

This can occur for built-in functions, C extensions, or functions defined interactively.

### IntentConfigurationError

Raised when namespace or decorator configuration is invalid:

```python
from pyintents.exceptions import IntentConfigurationError
```

For example, enabling `usemodule=True` without `recursive=True`.

### IntentShadowingError

Raised when a protected name is shadowed in the local scope:

```python
namespace = IntentNamespace(uses=[print])


@namespace.intent()
def bad():
    print = os.system  # IntentShadowingError
    print("echo")
```

This prevents the common Python attack pattern of reassigning a trusted name to a malicious function.

---

## API Reference

### IntentNamespace

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
    only_warnings=False,
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
| `only_warnings` | `bool` | `False` | Emit warnings instead of raising exceptions |

### @namespace.intent()

Overrides or extends namespace settings per function:

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

Available parameters match those of `IntentNamespace.__init__`.

---

## Security Model

PyIntents follows a fail-closed model with explicit trust:

- Only explicitly allowed calls are permitted
- Recursive validation is enabled by default
- Unknown calls are denied
- Dynamic primitives are denied by default
- Functions without available source code are treated with caution
- Shadowing of protected names is blocked
- Violations prevent execution

### Pre-Execution Validation

PyIntents validates the call chain before execution. This means:

```python
@namespace.intent()
def func():
    print("Func")
    outer()
```

If `outer` eventually calls something forbidden, `func` will not execute at all. This prevents partially executed functions from producing side effects before a violation is detected.

### Shadowing Protection

PyIntents protects against local shadowing of allowed names:

```python
# This is blocked
@namespace.intent()
def bad():
    print = os.system
    print("echo Hello")
```

```python
# This is also blocked
@namespace.intent()
def bad():
    from os import system as print
    print("echo Hello")
```

Without this protection, an attacker could reassign `print` to `os.system` and bypass the allowlist.

---

## Limitations

PyIntents is a static and runtime policy layer, not a complete sandbox.

Python is highly dynamic, so some behavior cannot be fully analyzed statically:

```python
getattr(os, "system")("echo bad")
eval("os.system('echo bad')")
globals()["os"].system("echo bad")
```

PyIntents mitigates many of these cases by denying dynamic primitives by default, but no AST-only solution can guarantee complete isolation.

For strong security boundaries, use:

- Subprocesses with restricted permissions
- Containers
- seccomp
- WASM
- RestrictedPython
- Custom import hooks
- Runtime monitoring

### Performance Considerations

Currently, `CallTree` is built on every call to a decorated function. This is acceptable for functions called infrequently but may impact performance in hot code paths. Future versions may add caching to reuse the call graph across invocations.

### Source Code Requirement

PyIntents requires source code to be available for analysis. Built-in functions, C extensions, and functions defined interactively cannot be analyzed. Such calls are either blocked or treated as unknown depending on policy settings.

### Dynamic Code Execution

PyIntents cannot analyze strings passed to `eval` or `exec`. Even if `eval` is denied by default, allowing it through `uses` creates a bypass for all other restrictions.

---

## Use Cases

| Use Case | Description |
|---|---|
| Plugin Sandboxes | Restrict what third-party plugins can do within your application |
| AI Agent Control | Limit tool access for LLM-powered agents |
| Environment Policies | Enforce different rules per deployment environment |
| Testing | Isolate unit tests from external dependencies and system calls |
| Security Audits | Document and enforce capability boundaries in your codebase |
| Internal APIs | Prevent accidental access to dangerous internal helpers |
| Privilege Separation | Minimize the attack surface of privileged functions |

---

## How It Works

PyIntents performs static policy validation before the decorated function is executed.

The pipeline is:

1. **AST Parsing**
   PyIntents parses the function source code using Python's `ast` module.

2. **Call Graph Construction**
   It builds a tree of statically visible function calls. Local functions are deferred until called. External functions are resolved safely.

3. **Safe Resolution**
   Call names are resolved to actual function objects when possible using `inspect.getattr_static()` without executing descriptors.

4. **Shadowing Detection**
   The AST is analyzed for assignments or imports that shadow protected names.

5. **Rule Matching**
   Each call is validated against:
   - `uses` allowlist
   - `deny` blocklist
   - `without` exemptions
   - `uselocals` local function policy
   - `usemodule` same-module policy
   - Unknown-call policy (`allow_unknown`)
   - Dynamic-primitive policy

6. **Pre-Execution Enforcement**
   If a violation is found, the decorated function is not executed. An exception is raised (or a warning is emitted if `only_warnings=True`).

Example call path:
```text
func -> outer -> inner -> os.system
```

If `os.system` is forbidden or unknown, PyIntents blocks the root call to `func` before any code inside `func` runs.

---

## Documentation

- [Latest Documentation](https://alexeev-prog.github.io/pyintents/main)
- [GitHub Repository](https://github.com/alexeev-prog/pyintents)

---

## License

Licensed under the GNU General Public License v3.0.

See [LICENSE](https://github.com/alexeev-prog/pyintents/blob/main/LICENSE) for details.

---

## Contributing

Contributions are welcome.

Feel free to:

- Open issues for bugs or feature requests
- Submit pull requests with improvements
- Suggest new features or use cases
- Improve documentation
- Report security concerns

### Development

```bash
# Clone the repository
git clone https://github.com/alexeev-prog/pyintents.git
cd pyintents

# Install development dependencies
pip install -e .[dev]

# Run tests
pytest

# Run linting
ruff check .
mypy .
```

---

## Support

If you find PyIntents useful, consider:

- Starring the repository on GitHub
- Reporting issues
- Suggesting features
- Improving documentation
- Sharing it with others who might benefit

<p align="center">
  <i>Trust explicitly. Fail safely.</i>
</p>

<p align="right">
  <a href="#readme-top">↑ Back to top</a>
</p>
