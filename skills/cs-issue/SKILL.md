---
name: cs-issue
description: 完整的缺陷修复生命周期。处理错误、回归、异常、卡顿和性能退化；在一次流程中完成复现、根因分析、最小修复、代码审查、回归验证、知识提升与归档。
license: MIT
compatibility: Requires a writable project repository. Bundled deterministic helpers require Python 3.10+; without Python, follow the workflow manually.
---

# `cs-issue` — reproduce, explain, fix, prove

State machine:

```text
intake → reproduce → analyze → fix → verify → accept → archived
```

Do not split report/analyze/fix/review into user-visible handoffs. Continue automatically until a true Gate or completion.

If the user explicitly asks to stop at a stage, for example “只分析原因，先不要修”, complete and internally review that stage, set state to the next stage, then return with the work active. `--until <stage>` remains an exact automation alias. This is an invocation-scoped user checkpoint, not a Gate or work completion. Without it, continue through completion.

## Runtime preflight

If `.codestable/tools/cs_context.py` is missing, internally execute the `cs` initialization procedure and return to this lifecycle in the same invocation. Do not ask the user to run onboarding or switch skills. Preserve existing project data.

## Start or resume

Create when needed:

```bash
python3 .codestable/tools/cs_context.py new issue "<title>" \
  --slug <slug> --lane <micro|standard|high-risk>
```

Use `state.json.stage`; never infer progress from the presence of old report or fix-note files. Generate one live-conversation session key, call `plan`, and read only the required/new/changed paths.

Load stage detail:

| Current stage | Read |
|---|---|
| `intake`, `reproduce`, `analyze` | `references/reproduce-analyze.md` |
| `fix`, `verify`, `accept` | `references/fix-verify.md` |

Apply project-local retrieval, Gate and minimality rules.

## Issue invariants

1. Observed symptom and intended behavior are distinct.
2. Reproduce or establish a measurable baseline before changing code whenever feasible.
3. Follow the real control/data flow to root cause.
4. The user's proposed fix is a hypothesis, not a requirement.
5. Make the smallest root-cause patch; avoid opportunistic refactor.
6. Verify the original symptom, not merely a new unit test around the changed function.
7. Internal diff review and regression QA happen in this skill.
8. Promote only a reusable diagnostic or constraint; ordinary fix history goes to archive.

## Lane behavior

- `micro`: obvious localized defect with direct reproduction and low-risk patch.
- `standard`: ordinary debugging, non-trivial root cause or performance baseline.
- `high-risk`: data corruption/loss, security, permissions, payment, public compatibility, destructive recovery, production-only failure or cross-service rollout.

Escalate when evidence reveals blast radius. A production incident can remain standard if the fix is bounded and fully testable; urgency alone is not architecture risk.

## Route transitions

Evidence may justify a linked lifecycle:

- desired behavior is actually new → transition/create `feature`;
- root cause is structural and cannot be fixed safely in a bounded patch → create linked `refactor`;
- several coordinated fixes require sequencing/contracts → create linked `roadmap`;
- current requirement/contract is wrong or missing → update through `model` as part of acceptance.

Record the relation in `state.links`. Do not ask the user to pick a skill. Pause only if the transition introduces a real Gate.

## Passive observation contract

When `/cs` supplies an observation `run_id`, reuse it; never start a duplicate trace. When this skill is invoked directly and no parent `run_id` exists, start one best-effort with `.codestable/tools/cs_observe.py start` after the work id and lane are known.

Append only meaningful metadata events (stage transition, tool failure/retry, Gate, user correction, verification). Never retrieve prior observations into delivery context and never record raw prompts, model replies, source contents, diffs, secrets, or private evaluator data. Finish the invocation with `cs_observe.py end`; signals only mark the observation `flagged` and do not trigger evolution.

## Completion contract

Before done:

- the original symptom is reproduced or the inability is explicitly evidenced;
- root cause explains the symptom and affected path;
- the patch is bounded to that cause;
- regression tests fail before/fix and pass after when practical;
- performance issues include comparable before/after measurements;
- relevant quality checks pass;
- final diff review has no blocking finding;
- production or user validation limitations are explicit;
- reusable knowledge is promoted selectively.
