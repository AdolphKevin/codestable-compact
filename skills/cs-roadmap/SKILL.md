---
name: cs-roadmap
description: 面向跨 feature 或跨系统目标的完整规划生命周期。盘点现状、收敛边界与契约、切分可独立验收的工作、审查依赖和风险，并在无真实 Gate 时自动激活第一项执行。
license: MIT
compatibility: Requires a writable project repository. Bundled deterministic helpers require Python 3.10+; without Python, follow the workflow manually.
---

# `cs-roadmap` — bound, contract, decompose, activate

State machine:

```text
discover → frame → contracts → decompose → review → activate → archived
```

A roadmap is current planning truth, not a folder of speculative future ideas. Use it only when one bounded feature cannot safely express the outcome.

If the user explicitly asks to stop at a stage, for example “先给路线图，不要激活任务”, complete and internally review that stage, set state to the next stage, then return with the work active. `--until <stage>` remains an exact automation alias. This is an invocation-scoped user checkpoint, not a Gate or work completion. Without it, continue through completion.

## Runtime preflight

If `.codestable/tools/cs_context.py` is missing, internally execute the `cs` initialization procedure and return to this lifecycle in the same invocation. Do not ask the user to run onboarding or switch skills. Preserve existing project data.

## Start or resume

```bash
python3 .codestable/tools/cs_context.py new roadmap "<title>" \
  --slug <slug> --lane <standard|high-risk>
```

`micro` is normally invalid for a roadmap; route a bounded item to feature/issue/refactor instead.

Use `state.json.stage` and session-scoped context planning. Read only current model indexes, explicit links and relevant code boundaries. Do not search every historical feature to infer architecture.

Load:

| Current stage | Read |
|---|---|
| `discover`, `frame`, `contracts` | `references/discover-contracts.md` |
| `decompose`, `review`, `activate` | `references/decompose-activate.md` |

## Roadmap invariants

1. Inspect existing systems and contracts before asking broad architecture questions.
2. Define outcome and boundaries before enumerating tasks.
3. Contracts and dependency direction precede feature ordering.
4. Each item must produce an independently observable result or risk reduction.
5. Avoid a roadmap for work that one standard feature can deliver.
6. Do not create implementation detail for distant items beyond what sequencing/contracts require.
7. Review is internal; strategy choices become a human Gate only when genuinely unresolved.
8. If the user asked to build the outcome, activate the first ready item automatically after roadmap approval/clearance.

## Runtime artifacts

The active planning process uses the normal three-file work aggregate. The accepted current roadmap is promoted to:

```text
.codestable/model/roadmaps/<slug>.md
```

Do not retain a parallel collection of roadmap draft/review/item files unless concrete tooling requires it. The accepted roadmap document contains outcome, contracts, item table, dependencies, risks and status.

## Passive observation contract

When `/cs` supplies an observation `run_id`, reuse it; never start a duplicate trace. When this skill is invoked directly and no parent `run_id` exists, start one best-effort with `.codestable/tools/cs_observe.py start` after the work id and lane are known.

Append only meaningful metadata events (stage transition, tool failure/retry, Gate, user correction, verification). Never retrieve prior observations into delivery context and never record raw prompts, model replies, source contents, diffs, secrets, or private evaluator data. Finish the invocation with `cs_observe.py end`; signals only mark the observation `flagged` and do not trigger evolution.

## Completion contract

- existing capabilities and gaps are evidenced;
- in/out boundaries are explicit;
- public/internal contracts needed for parallel or sequential work are defined;
- items have acceptance, dependencies and risk/lane;
- critical path and rollback/rollout assumptions are visible;
- internal review has no blocking inconsistency;
- human decisions, if any, are approved and recorded;
- accepted roadmap is indexed in current model;
- first executable item is created/started when requested and clear.
