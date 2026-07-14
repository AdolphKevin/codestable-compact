---
name: cs-feat
description: 在 CodeStable Compact 控制平面内交付新的可观察能力。Owner 自主探索、提出和实现最小变化；Harness 根据风险约束副作用并要求真实验证，必要时由独立 Reviewer 反证完成声明。
license: MIT
compatibility: Requires a CodeStable Compact project runtime and a writable repository for implementation tasks. Uses only project-local tools and project-standard verification commands.
---

# Feature outcome lens

Use this skill when the first independently verifiable outcome is a new supported capability or externally observable behavior. It is not a fixed feature workflow.

Receive from `/cs` when available: task id, risk, session key, passive observation run id and invocation-specific write constraint. A direct invocation must initialize/resume the same control state rather than create phase files.

## Control contract

- Owner chooses the order of inspection, experiments, implementation and tests.
- Harness owns allowed writes, risk escalation, evidence recording and completion.
- Reviewer challenges omitted scope, regressions, weak acceptance evidence and duplicate paths.
- Actions `inspect`, `propose`, `execute`, `verify`, `learn` may repeat or be skipped when the current risk/evidence state permits.

Read only the relevant guide:

| Need | Reference |
|---|---|
| Establish current behavior, boundaries, assumptions or a bounded change | `references/inspect-propose.md` |
| Implement or adapt the change | `references/execute.md` |
| Build evidence, challenge completion and admit learning | `references/verify-learn.md` |
| Repair inconsistent active state | `references/recovery.md` |

## Feature contract

Before completion, `goal` must identify:

- observable capability;
- acceptance examples and boundary/error behavior;
- compatibility and invariants when relevant;
- explicit non-goals;
- write/side-effect boundary.

Do not ask for information already visible in the request, repository, tests or accepted model. Ask only when a genuine product/authority choice changes the capability or side effects.

## Inspect

Establish the real entry point, call/data path, nearest executable contract, affected state/schema/prompt/side effect and open unknowns. Record concise facts and assumptions in the ledger. Link only current model/knowledge that constrains the feature.

For L1, a `scope_inspect` snapshot is sufficient when it proves a bounded surface. L2/L3 require an audit/invariant contract appropriate to the policy.

## Propose when needed

L0/L1 may proceed without a design artifact when the change is obvious and bounded. L2/L3 require a falsifiable proposal stating:

- the behavior and mechanism to change;
- why this is the smallest coherent mechanism;
- what intentionally remains unchanged;
- evidence capable of disproving it.

A proposal is mutable understanding, not a hand-off document. Update it when execution evidence contradicts it.

## Execute

Implement the smallest independently observable slice inside the allowed paths. Follow current conventions, preserve unrelated behavior and remove superseded paths once the canonical path is proven. Register actual changed paths; registration may raise risk.

Avoid speculative abstractions, dependencies, compatibility aliases, configuration switches and process artifacts. Do not hide expanded scope behind a local patch.

## Verify and review

Derive verification from acceptance and risk, not implementation structure. Include primary behavior, negative/boundary behavior, compatibility/invariants and project-standard checks.

Use Harness-backed command evidence. A passing test that cannot fail on the old behavior is not adequate evidence. L2/L3 require a separate reviewer artifact produced by someone other than the Owner.

When evidence fails, repair understanding or implementation and repeat any useful action. `FAIL`, `BLOCKED` and `PARTIAL` remain distinct.

## Complete and learn

Completion requires the Harness gate, not a feature summary. Promote only durable current capability/contract/decision or a reusable failure rule with a real future consumer. Archive only after `COMPLETED`.

A new regression fixture, checker, invariant or reviewer/routing rule is justified only by a real failure mode. Do not create a retrospective as a substitute.
