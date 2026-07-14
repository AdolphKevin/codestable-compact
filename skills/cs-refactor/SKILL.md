---
name: cs-refactor
description: 在 CodeStable Compact 控制平面内改善结构、复杂度或依赖关系，同时以可执行特征化证据保护行为。Owner 自主选择重构路径，Harness 控制范围、风险、等价性证据和完成权。
license: MIT
compatibility: Requires a CodeStable Compact project runtime, a writable repository, and executable characterization or contract evidence for the behavior that must remain stable.
---

# Refactor outcome lens

Use only when observable behavior is intended to remain stable while structure, ownership, dependency direction, duplication or maintainability improves. When behavior itself is wrong, start with `cs-issue`; when a new capability is required, start with `cs-feat`.

Read only the relevant guide:

| Need | Reference |
|---|---|
| Establish behavioral contract, structural problem and safe seams | `references/inspect-contract.md` |
| Make structural moves, verify equivalence and remove obsolete paths | `references/execute-verify.md` |

## Refactor contract

State:

- structural objective and measurable improvement;
- observable behavior/invariants that must not change;
- current dependency/data/control path;
- explicit non-goals;
- allowed paths and rollback;
- evidence capable of detecting semantic drift.

“Cleaner” alone is not acceptance. Use a concrete property such as one source of truth, eliminated cycle, reduced duplicate branches, bounded ownership or smaller public surface.

## Inspect and characterize

Trace actual callers, state transitions, ordering, errors, retries, concurrency, serialization and public/persistent contracts. Add or identify characterization evidence before moving a high-risk seam.

Record assumptions when behavior is not yet known. Do not freeze accidental behavior without deciding whether it is part of the supported contract.

L2/L3 require explicit invariants and independent review. Refactors touching core state, auth, persistence or migrations can become L3 even without intended product behavior change.

## Propose only the necessary structure

Prefer deletion, consolidation and existing seams over a new generic layer. A bounded proposal should explain:

- canonical path after the change;
- incremental seams;
- how equivalence is observed;
- when obsolete paths are deleted;
- rollback/compatibility where relevant.

Reject designs that introduce more concepts than they remove, require a broad rewrite before evidence, or leave dual truth without a removal condition.

## Execute and verify continuously

Make one coherent structural move, run the narrowest discriminating evidence, inspect semantic drift and adapt. The Owner may change order as evidence warrants; this is not a prescribed sequence.

Search deliberately for remaining duplicate symbols/paths after the canonical path is proven. Remove temporary adapters and fallback branches unless a real supported rollout contract requires them.

Verification includes characterization/current tests, contract or serialization evidence where applicable, project checks and a measure tied to the structural objective. Reviewer actively looks for ordering/error/concurrency changes, hidden compatibility effects, forwarding abstractions and tests coupled only to implementation.

## Complete and learn

Harness completion requires both behavior preservation and the claimed structural improvement. “All tests pass” is insufficient when tests do not observe the protected contract or the old duplicate path still exists.

Promote only a new durable architecture constraint or invariant. Ordinary refactor rationale remains in task history.
