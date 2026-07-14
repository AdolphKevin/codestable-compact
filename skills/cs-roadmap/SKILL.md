---
name: cs-roadmap
description: 在 CodeStable Compact 控制平面内把跨能力、跨系统或契约未收敛的目标拆成可独立验证的任务合同。路线本身按事实、风险和依赖收敛，并可在同一调用中激活首个可执行任务。
license: MIT
compatibility: Requires a CodeStable Compact project runtime. Repository and current model access are needed to establish real contracts, dependencies and risk boundaries.
---

# Roadmap outcome lens

Use when one bounded feature/issue/refactor cannot responsibly close the outcome because several independently observable outcomes, systems, migrations or contracts must be coordinated.

A roadmap is a current dependency/contract model, not a waterfall plan or a list of departments. It should reduce uncertainty and enable autonomous bounded tasks.

Read only what is needed:

| Need | Reference |
|---|---|
| Inspect current system and establish cross-task contracts | `references/inspect-contracts.md` |
| Form outcome tasks, verify decomposition and activate ready work | `references/propose-activate.md` |

## Roadmap contract

Record:

- observable end state and affected actors/systems;
- why one bounded task is insufficient;
- in/out scope, invariants and constraints;
- public/persistent/security/ownership boundaries;
- success, rollout and rollback measures;
- known unknowns and decisions requiring authority.

Inspect current model, code entry points, accepted decisions and overlapping active work before proposing decomposition. Do not interview abstractly when repository evidence can answer.

## Establish only necessary contracts

Define the minimum cross-task contracts that let work proceed independently: API/event/schema/auth, ownership, dependency direction, migration/compatibility, failure semantics and observability.

Do not pre-design every internal implementation. Unknowns become bounded discovery tasks only when they block a contract and have an observable output.

## Propose outcome tasks

Each item has:

- stable id/title and kind;
- independently observable outcome/acceptance;
- risk level and side-effect boundary;
- real dependencies/contracts;
- evidence policy or validation access;
- rollout/rollback only when needed;
- state such as queued, ready, active, completed or dropped.

Prefer vertical outcomes over “backend/frontend/database” activity buckets. Do not create fake dependencies for a tidy diagram or ceremony-only fragments.

## Challenge and activate

Review for missing outcomes, undefined contracts, false ordering, unbounded high-risk work, giant items and duplicated scope. A real strategic/security/data choice may require an explicit Owner checkpoint; ordinary decomposition repair does not.

Promote one current roadmap document only when humans/Agents will use it to coordinate future work. Update its index.

When execution was requested and an item is ready, create its task contract, link the roadmap/contracts and continue into Owner execution under the active contract in the same invocation. Do not stop with “next invoke cs-feat.”

Roadmap completion means its coordination objective and item state are evidenced; it does not allow child tasks to inherit unverified completion.
