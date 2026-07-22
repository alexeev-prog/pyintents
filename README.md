<div align="center">
  <p align="center">
    <h1>pyintents</h1>
    <p><strong>Declarative capability-based access control for Python functions.</strong></p>
    <a href="https://alexeev-prog.github.io/pyintents/v0.2.2"><strong>Explore the docs »</strong></a>
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

PyIntents brings **capability-based security** to Python. Functions declare what they are allowed to do via `@intent` decorators, and the runtime enforces these permissions at call time. Define namespaces with allow and disallow rules, propagate restrictions recursively, or selectively exempt trusted functions with `without`. Permissions are dynamic and layered — grant or revoke access at runtime without touching the original code. Ideal for plugin sandboxes, AI agent tool control, environment-specific security policies, and testing. Trust explicitly, fail safely. No more functions that quietly do whatever they want.

---

## 🚀 Getting Started

### Installation

```bash
pip install pyintents
```

### Quick Example

```python
from pyintents import IntentNamespace

# Create a namespace that allows only print()
namespace = IntentNamespace(uses=[print])

@namespace.intent()
def safe_function():
    print("This is allowed")  # ✅

@namespace.intent()
def unsafe_function():
    import os
    os.system("rm -rf /")  # ❌ Raises IntentViolationError
```

---

## 🛡️ Basic Usage

### 1. Allow Specific Functions

```python
namespace = IntentNamespace(uses=[print, len])

@namespace.intent()
def my_func():
    print("Hello")   # Allowed
    return len([1])  # Allowed
```

### 2. Recursive Enforcement

```python
namespace = IntentNamespace(uses=[print], recursive=True)

def helper():
    print("Inside helper")

@namespace.intent()
def main():
    helper()  # Recursively validated
```

### 3. Exempt Trusted Functions

```python
namespace = IntentNamespace(
    uses=[print, helper],
    without=[helper]  # Exempt from checks
)

@namespace.intent()
def main():
    helper()  # Called without validation
    print("OK")
```

### 4. Runtime Layering

```python
base = IntentNamespace(uses=[print])

@base.intent(uses=[len])  # Adds len to permissions
def layered_func():
    print("Hi")
    return len("world")
```

### 5. Explicit Denial

```python
namespace = IntentNamespace(
    uses=[print],
    deny=[os.system]
)

@namespace.intent()
def restricted():
    print("OK")
    os.system("echo bad")  # ❌ Explicitly denied
```

### 6. Local Functions

```python
namespace = IntentNamespace(uses=[print])

def local_helper():
    pass

@namespace.intent(uselocals=True)
def main():
    local_helper()  # Allowed (local scope)
```

---

## 📦 API Reference

### `IntentNamespace`

| Parameter | Type | Description |
|-----------|------|-------------|
| `uses` | `list[Callable]` | Allowed functions |
| `recursive` | `bool` | Enable recursive validation (default: `False`) |
| `without` | `list[Callable]` | Exempt functions from validation |
| `uselocals` | `bool` | Allow local functions (default: `False`) |
| `deny` | `list[Callable]` | Explicitly forbidden functions |

### `@intent()` Decorator

Overrides namespace settings per function:

```python
@namespace.intent(
    uses=[print],           # Override allowed functions
    recursive=True,         # Override recursion
    without=[helper],       # Override exemptions
    uselocals=True,         # Override local scope
    deny=[os.system]        # Override denials
)
def custom_func():
    pass
```

---

## ⚠️ Exceptions

### `IntentViolationError`

Raised when a function violates declared permissions:

```python
from pyintents.exceptions import IntentViolationError

try:
    func()
except IntentViolationError as e:
    print(e)  # Function 'func' calls forbidden 'os.system'
```

---

## 🔧 How It Works

1. **AST Parsing** — PyIntents parses the function's source code using Python's `ast` module
2. **Call Tree Construction** — Builds a tree of all function calls up to the specified depth
3. **Permission Resolution** — Resolves call names to actual function objects
4. **Rule Matching** — Validates each call against:
   - `uses` — allowed functions
   - `deny` — explicitly forbidden functions
   - `without` — exempt functions
   - `uselocals` — local scope exceptions
5. **Runtime Enforcement** — Validates at call time, raising `IntentViolationError` on violations

### Limitations

- **Source Code Required** — Functions must have source code available (not built-ins or C extensions)
- **Dynamic Calls** — Calls via `getattr()` or `eval()` cannot be statically analyzed
- **Depth Limit** — Recursion depth is capped to prevent infinite loops

---

## 🎯 Use Cases

| Use Case | Description |
|----------|-------------|
| **Plugin Sandboxes** | Restrict what third-party plugins can do |
| **AI Agent Control** | Limit tool access for LLM agents |
| **Environment Policies** | Enforce different rules per environment (dev/staging/prod) |
| **Testing** | Isolate unit tests from external dependencies |
| **Security Audits** | Document and enforce capability boundaries |

---

## 📄 License

Licensed under the **GNU General Public License v3.0**.

See [LICENSE](https://github.com/alexeev-prog/pyintents/blob/main/LICENSE) for details.

---

## 🤝 Contributing

Contributions are welcome! Feel free to open issues, submit PRs, or suggest features.

---

## 📚 Documentation

- [Latest Documentation](https://alexeev-prog.github.io/pyintents/main)
- [Version 0.2.2](https://alexeev-prog.github.io/pyintents/v0.2.2)
- [GitHub Repository](https://github.com/alexeev-prog/pyintents)

---

## 🌟 Support

If you find PyIntents useful, consider:

- ⭐ Starring the repository on GitHub
- 🐛 Reporting issues
- 💡 Suggesting features
- 📖 Improving documentation

---

<p align="center">
  <i>Trust explicitly. Fail safely.</i>
</p>

<p align="right">
  <a href="#readme-top">↑ Back to top</a>
</p>
