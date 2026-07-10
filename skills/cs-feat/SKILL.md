---
name: cs-feat
description: 完整的新功能交付生命周期。一次调用内完成意图澄清、代码取证、设计、自审、实现、代码审查、QA、验收、知识提升与归档；按 stage 续作，只在真实风险 Gate 暂停。
license: MIT
compatibility: Requires a writable project repository. Bundled deterministic helpers require Python 3.10+; without Python, follow the workflow manually.
---

# `cs-feat` — full feature lifecycle

This is one lifecycle, not a router to design/implementation/review/QA sub-skills.

State machine:

```text
intake → evidence → design → implement → verify → accept → archived
```


## Runtime preflight

If `.codestable/tools/cs_context.py` is missing, internally execute the `cs` initialization procedure and return to this lifecycle in the same invocation. Do not ask the user to run onboarding or switch skills. Preserve existing project data.

Internal loops:

```text
design review failure → design
code review failure   → implement
QA/accept failure     → implement or design, according to root cause
```

These loops continue automatically. Never tell the user to invoke another feature skill.

## Start or resume

Use an existing feature work id when supplied. Otherwise create one:

```bash
python3 .codestable/tools/cs_context.py new feature "<title>" \
  --slug <slug> --lane <micro|standard|high-risk>
```

`state.json.stage` decides where to continue. Do not Glob for old design/review/QA files. Generate one session key per live conversation and run the context planner for the current stage.

Load exactly one stage reference unless a repair requires the adjacent stage:

| Current stage | Read |
|---|---|
| `intake`, `evidence`, `design` | `references/intake-design.md` |
| `implement` | `references/implement.md` |
| `verify`, `accept` | `references/verify-accept.md` |
| corrupt/mismatched state | `references/recovery.md` |

Also apply project-local `.codestable/reference/retrieval.md`, `gates.md` and `minimality.md`. Do not reread them when unchanged and already present in the live conversation.

## Feature invariants

1. Acceptance describes observable behavior, not files to edit.
2. Inspect actual code/test/config flows before asking implementation questions.
3. Current code, tests, accepted contracts and decisions outrank archived feature prose.
4. A design is only as large as the lane requires.
5. Reuse existing paths and dependencies before adding an abstraction.
6. Review and QA happen inside this skill.
7. A passing review needs no separate report; record only evidence, findings, repairs and decisions in `work.md`.
8. Completion promotes durable truth before moving the task to archive.

## Lane behavior

### Micro

- Fill intent/acceptance, concise evidence, changes and verification.
- Design may be one sentence naming the existing path reused.
- No separate checklist; use at most a few bullets in `work.md`.
- Still inspect the diff and run the smallest credible test.

### Standard

- Record bounded design, affected contracts, plan and explicit acceptance evidence.
- Implement in reviewable steps.
- Run relevant tests plus project-standard quality checks.

### High-risk

- Record compatibility, migration, rollout, rollback, observability and failure modes.
- Split implementation into independently verifiable steps.
- Create a human Gate only when the remaining choice needs authority, not merely because design ended.

## Stage transitions

Advance state only after the current stage exit criteria pass:

```bash
python3 .codestable/tools/cs_context.py set --work <id> --stage <next-stage>
```

Do not pre-mark future steps complete. If Git evidence shows work ahead of state, reconcile `work.md` and state before proceeding.

## Passive observation contract

When `/cs` supplies an observation `run_id`, reuse it; never start a duplicate trace. When this skill is invoked directly and no parent `run_id` exists, start one best-effort with `.codestable/tools/cs_observe.py start` after the work id and lane are known.

Append only meaningful metadata events (stage transition, tool failure/retry, Gate, user correction, verification). Never retrieve prior observations into delivery context and never record raw prompts, model replies, source contents, diffs, secrets, or private evaluator data. Finish the invocation with `cs_observe.py end`; signals only mark the observation `flagged` and do not trigger evolution.

## Completion contract

Before `done`:

- acceptance is demonstrated against the original intent;
- diff review has no unresolved blocking finding;
- tests/quality checks are recorded with results;
- public/current behavior is reflected in model when appropriate;
- reusable pitfalls are promoted to knowledge, not copied wholesale;
- follow-ups that are not required for acceptance are explicitly separated.

Then mark done and archive. The archive is not searched by default in future features.
