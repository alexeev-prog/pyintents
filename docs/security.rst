Security model
==============

Choose the correct boundary
---------------------------

``IntentNamespace`` is a static policy checker for trusted code, not a sandbox.
It does not intercept every Python call, enforce operating-system permissions,
or guarantee that inspected source matches mutable runtime behavior.

``IntentDispatcher`` is a trusted authorization component. Its fixed registry
maps capability IDs to trusted handlers and validators. Each dispatcher has a
fixed set of grants, with explicit deny taking precedence. Every request checks
authorization before copying data, validating arguments, and invoking a handler.

For hostile Python, use an OS-isolated worker that sends bounded requests to a
trusted broker. Do not give the worker dispatcher objects, handler references,
policy mutation access, credentials, or unrestricted filesystem/network access.
The broker must authenticate the session and select grants itself. Never accept
the grant list from the request. A subprocess alone is not a sandbox.

Transport and handler responsibilities
------------------------------------------

Use a size-limited data protocol, not pickle. Reject oversized requests before
decoding. The dispatcher only accepts exact plain JSON-like types and copies
request/result values; arbitrary objects, callable values, subclasses, and
non-string mapping keys are rejected without inspecting their metadata.

Default traversal limits are 10,000 nodes, depth 32, and a conservative string
budget of 1,000,000 bytes (four bytes per character). Integers are limited to
4096 bits; configured maximum depth cannot exceed 128. Floats must be finite.
Limits apply separately to each copy and do
not limit transport allocation, handler execution time, or external operations.

Validators must return exactly True, should be pure, and receive a separate copy
of the original arguments. They must constrain the actual resource, not just
the argument type: paths, hostnames, operation names, tenant ownership, and quotas.
Filesystem symlinks and races require appropriate OS APIs inside the handler.

Handlers execute once; exceptions propagate without automatic retries. Result
validation occurs after execution, so a rejected result cannot undo effects.
The dispatcher adds no global lock: concurrent handlers must manage their own
state, transaction boundaries, and resource limits.

Static analysis hardening
-------------------------

The analyzer resolves actual function builtins and refuses to substitute globals
for parameters, closures, or locally bound names. Local definitions must have a
single stable binding before they can be treated as local call targets. Graph
cycles use object identity and stable local-definition IDs, not mutable display
names. Graph growth, depth, and extracted source size are bounded.

Function-object rules match only the exact object. String rules match names and
metadata for convenience and are not capabilities. Default dynamic primitive
denials include builtin objects, blocking aliases. Opaque callable instances are
not introspected, and source retrieval does not follow ``__wrapped__``.

Strict mode rejects many unsupported implicit-execution constructs instead of
silently treating them as checked. It is intentionally conservative, not a
verified language subset. Explicitly allowed builtins can still invoke object
protocols or callbacks. Mutable globals, descriptors behind call targets, source
changes, native code, and concurrency can invalidate static conclusions.

Async functions are validated at coroutine execution. Await is unsupported in
strict mode; audit mode offers no protection across suspension. Decorated
generators and async generators are rejected.

No ACID promise
---------------

Pre-execution checking is not atomicity, consistency, isolation, or durability.
Use database transactions where available, and design idempotency or explicit
compensation for non-transactional effects. Do not retry privileged operations
blindly after transport errors.
