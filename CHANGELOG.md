## [Unreleased]

### 🚀 Features

- Add trusted capability dispatch with fixed grants, mandatory validators and bounded plain data
- Add conservative strict syntax checks and call graph analysis budgets

### 🐛 Bug Fixes

- Resolve lexical bindings and actual function builtins instead of substituting globals
- Detect local recursion and block aliases of denied dynamic primitives
- Match function-object rules by identity without metadata fallback
- Inspect actual code objects without following wrapped functions or calling arbitrary repr
- Preserve coroutine wrappers and reject unsupported generator roots
- Export IntentShadowingError and remove development tools from runtime dependencies

### 📚 Documentation

- Clarify static-analysis limitations, trusted broker boundaries and lack of rollback
- Add migration notes, dispatcher examples and harmless policy demonstrations

### 🧪 Testing

- Add adversarial policy and dispatcher regression suites
- Require 85% coverage in the test session

## [0.3.0] - 2026-08-16

### 🚀 Features

- Add protection against shadowing (assign and imports)

### 📚 Documentation

- Update CHANGELOG.md for v0.2.0 [skip ci]
## [0.2.0] - 2026-08-04

### 🚀 Features

- Add usemodule, update readme, improve stability and safety

### 🐛 Bug Fixes

- Fix docs, examples and add article

### 💼 Other

- Fix typing errors

### 📚 Documentation

- Update CHANGELOG.md for v0.1.0 [skip ci]
- Update docs workflow
- Update docs workflow
- Update docs workflow
- Update docs workflow
- Update docs workflow
- Update docs workflow
- Update docs

### 🧪 Testing

- Create tests for 100% coverage
## [0.1.0] - 2026-07-16
