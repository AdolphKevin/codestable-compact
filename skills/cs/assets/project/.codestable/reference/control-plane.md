# Evidence-convergence invariants

1. `/cs` routes and continues in the same invocation. Routing is not a hand-off or Gate.
2. The Owner may choose any implementation path. `inspect`, `propose`, `execute`, `verify` and `learn` are repeatable control actions, not ordered stages.
3. Progress is defined by confirmed facts, closed assumptions/risks and recorded evidence—not by the current action label or document count.
4. `state.json` is the control state and `evidence.jsonl` is the evidence source. Code-written and task-complete are different conditions.
5. The Harness owns Git-visible side-effect comparison, risk escalation and completion authority. The Owner cannot lower risk during an active task or satisfy command-backed requirements with artifact assertions.
6. Reviewer responsibility is adversarial: challenge scope, regression, hidden effects, dual paths, weak tests and unsupported completion. Portable producer identity is declarative unless a Host Adapter attests it.
7. L0/L1 may remain lightweight. L2/L3 require explicit contracts and stronger independent evidence. Newly discovered impact may only preserve or increase risk.
8. `PASS`, `FAIL`, `BLOCKED` and `PARTIAL` remain distinct. Missing infrastructure is not a business assertion failure; partial evidence is not a pass.
9. Completion requires current-bound, acceptance-scoped risk evidence, no blocking assumption/risk/blocker, and full coverage of Git-visible changes since the task baseline. A later source, registered-change, task-state, proposal, invariant or acceptance-contract mutation makes prior PASS evidence stale until the matching verification is rerun. Archive rechecks integrity and eligibility; it never creates completion.
10. Normal work may best-effort write a passive observation, but must not read observation/Meta history or mutate the Harness.
11. Durable learning is admitted only as a fixture, rule, invariant, checker, scenario, routing policy or failure signature with a real consumer.
12. Harness evolution remains explicit, fixture-covered, independently evaluated and rollback-capable.
