---
name: cs-model
description: 维护软件当前真相与可复用知识：vision、领域术语、requirements、contracts、decisions、roadmaps 索引和 knowledge promotion；以当前代码/测试/已接受决策为证据，避免把过程历史当规范。
license: MIT
compatibility: Requires a writable project repository. Bundled deterministic helpers require Python 3.10+; without Python, follow the workflow manually.
---

# `cs-model` — curate current truth

State machine for substantial edits:

```text
inspect → edit → validate → index → archived
```

Tiny obvious corrections may use a `micro` work item, but current model changes still require evidence and index consistency.

If the user explicitly asks to stop at a stage, complete and internally review that stage, set state to the next stage, then return with the work active. `--until <stage>` remains an exact automation alias. This is an invocation-scoped user checkpoint, not a Gate or work completion. Without it, continue through completion.

## Runtime preflight

If `.codestable/tools/cs_context.py` is missing, internally execute the `cs` initialization procedure and return to this lifecycle in the same invocation. Do not ask the user to run onboarding or switch skills. Preserve existing project data.

## Modes

Infer mode from the request; do not ask the user to choose an internal command:

| Mode | Destination |
|---|---|
| vision | `model/vision.md` |
| domain | `model/domain.md` |
| requirement | `model/requirements/` |
| contract | `model/contracts/` |
| decision | `model/decisions/` |
| roadmap status | `model/roadmaps/` |
| promote knowledge | `knowledge/notes/` |
| reconcile/index | relevant docs + `INDEX.md` |

Create a model work aggregate for non-trivial changes:

```bash
python3 .codestable/tools/cs_context.py new model "<title>" \
  --slug <slug> --lane <micro|standard|high-risk>
```

Load:

| Stage | Read |
|---|---|
| `inspect`, `edit` | `references/inspect-edit.md` |
| `validate`, `index` | `references/validate-index.md` |

## Model invariants

1. Model documents describe what is true/required now, not how one task unfolded.
2. Current executable behavior is evidence, but an accepted requirement/decision may intentionally describe behavior not yet implemented; record drift explicitly rather than silently choosing one.
3. Accepted decisions have status and supersession links; do not rewrite history as though the old decision never existed.
4. Requirement statements are observable and stable, not implementation checklists.
5. Contracts name compatibility and failure behavior.
6. Knowledge notes are specific, evidenced and reusable; generic advice and one-off logs remain in archive.
7. INDEX files are pointers with concise summaries/tags, not duplicated content.
8. Model edits that imply executable changes create/link the appropriate feature/issue/refactor and continue when requested.

## Passive observation contract

When `/cs` supplies an observation `run_id`, reuse it; never start a duplicate trace. When this skill is invoked directly and no parent `run_id` exists, start one best-effort with `.codestable/tools/cs_observe.py start` after the work id and lane are known.

Append only meaningful metadata events (stage transition, tool failure/retry, Gate, user correction, verification). Never retrieve prior observations into delivery context and never record raw prompts, model replies, source contents, diffs, secrets, or private evaluator data. Finish the invocation with `cs_observe.py end`; signals only mark the observation `flagged` and do not trigger evolution.

## Completion contract

- source evidence and conflicts are recorded;
- duplicate or stale current statements are removed/superseded;
- links between requirement, contract and decision are valid;
- indexes point to current files with concise summaries;
- no task-history dump was promoted;
- code/model drift is either repaired or represented by a linked active work item;
- relevant validation/search checks pass.
