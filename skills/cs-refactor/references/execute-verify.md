# Execute and verify a refactor

## Move one coherent seam

Make a bounded structural change, then run the narrowest evidence that can detect semantic drift. The Owner may inspect, propose, execute and verify in any order needed by feedback.

Prefer consolidation and deletion. Do not keep forwarding layers, compatibility aliases, duplicate truth or fallback paths without a supported contract and explicit removal condition. Register changed paths so the Harness can raise risk when scope expands.

## Prove both claims

Evidence must observe:

1. preserved supported behavior and invariants; and
2. the stated structural improvement.

Use characterization/current tests plus contract, serialization, ordering, concurrency or integration evidence where relevant. Search for residual duplicate symbols and paths after the canonical route is established.

Independent reviewer for L2/L3 challenges hidden semantic changes, errors/retry ordering, public/persistent compatibility, test coupling to implementation, broad churn and old paths that remain reachable.

Completion is denied when only tests pass but the structural objective is unproven, or when the new structure exists beside the obsolete implementation. Durable learning is limited to a real architecture invariant or checker that future work will consume.
