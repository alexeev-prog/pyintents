Migration from the original 0.3 behavior
==========================================

This hardening introduces deliberate compatibility changes. Existing code should
review its trust assumptions before enabling previously permissive settings.

* ``IntentNamespace`` defaults to ``strict=True``. Unsupported syntax raises
  ``IntentParseError``. Use ``strict=False`` only for trusted-code auditing.
* Callable-object rules no longer grant access to matching module/qualified-name
  metadata. Register the exact function, or explicitly select a string rule when
  broad metadata matching is intended.
* Callable instances are opaque and cannot be used as rules or decorated roots.
* Names cannot authorize unresolved or dynamic targets unless the explicitly
  unsafe ``allow_unknown=True`` option is selected.
* Default deny rules block aliases of dynamic builtin primitives too.
* Local recursion is detected rather than expanding until RecursionError.
* Async wrappers preserve coroutine kind and check at execution time. Generator
  and async-generator roots raise ``IntentConfigurationError``.
* Analysis has node/depth/source budgets. Warning mode does not suppress parse
  errors or budget exhaustion.
* Development tools are no longer installed as runtime dependencies. Contributors
  should use ``uv sync --all-groups``.

For AI tools and privileged operations, prefer ``IntentDispatcher`` with trusted
registry/grants and per-capability argument validation. It does not sandbox code;
hostile plugins still require external OS isolation and an authenticated broker.
