# Inspect a refactor contract

A refactor needs two independently testable claims: supported behavior remains stable, and a named structural property improves.

## Characterize supported behavior

Trace callers, data/control flow, state transitions, ordering, errors, retries, concurrency, serialization and public or persistent contracts. Identify existing characterization tests or create evidence at the nearest observable boundary.

Separate supported behavior from accidental implementation detail. Record uncertainty as an assumption rather than freezing it silently.

## Define structural acceptance

Use a measurable property: one source of truth, removed cycle, deleted duplicate branches, reduced public surface, bounded ownership or a simpler dependency direction. “Cleaner” is not acceptance.

Set invariants, non-goals, allowed paths and rollback. Core state, authorization, persistence, schema or migration surfaces may raise the task to L3 even when product behavior is intended to remain unchanged.

## Bound a proposal when required

For L2/L3, state the canonical path after the change, safe incremental seams, equivalence evidence, obsolete-path removal condition and rollback/compatibility behavior. Reject broad rewrites that cannot produce evidence until the end or abstractions that add more concepts than they remove.
