# Inspect a roadmap and establish contracts

Use a roadmap only when several independently observable outcomes or systems must coordinate.

## Inspect current reality

Trace current entry points, ownership, contracts, active work and accepted decisions. Record the observable end state, why one bounded task cannot close it, constraints, invariants, risks and unknowns.

## Define only cross-task contracts

Specify the minimum API, event, schema, authorization, ownership, failure, migration, compatibility and observability contracts required for independent work. Do not design every internal implementation.

Turn an unknown into a discovery task only when it blocks a contract and the discovery has an observable result. Keep facts, assumptions and risks explicit so the roadmap can change when evidence changes.

## Bound side effects and authority

Identify persistent/public/security boundaries, rollout and rollback needs, and decisions that require product or operational authority. Do not use roadmap ceremony to hide an unbounded critical task.
