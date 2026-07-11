---
name: cs-refactor
description: 完整的行为保持重构生命周期。先刻画现有行为和结构问题，再设计最小重构步、增量实现、内部审查、等价性验证与归档；避免无证据抽象和顺手重写。
license: MIT
compatibility: Requires a writable project repository. Bundled deterministic helpers require Python 3.10+; without Python, follow the workflow manually.
---

# `cs-refactor` — improve structure, preserve behavior

State machine:

```text
intake → characterize → design → implement → verify → accept → archived
```

A refactor is not “large code change.” Its defining contract is preserved observable behavior, except for explicitly approved non-functional targets such as performance or operability.

If the user explicitly asks to stop at a stage, for example “先给重构设计，不要实现”, complete and internally review that stage, set state to the next stage, then return with the work active. `--until <stage>` remains an exact automation alias. This is an invocation-scoped user checkpoint, not a Gate or work completion. Without it, continue through completion.

## Runtime preflight

If `.codestable/tools/cs_context.py` is missing, internally execute the `cs` initialization procedure and return to this lifecycle in the same invocation. Do not ask the user to run onboarding or switch skills. Preserve existing project data.

## Start or resume

```bash
python3 .codestable/tools/cs_context.py new refactor "<title>" \
  --slug <slug> --lane <micro|standard|high-risk>
```

Resume from `state.json.stage`. Use one live session key and stage-specific context planning. Do not scan historical features for patterns; current code/tests and accepted model are primary.

Load:

| Current stage | Read |
|---|---|
| `intake`, `characterize`, `design` | `references/characterize-design.md` |
| `implement`, `verify`, `accept` | `references/implement-verify.md` |

## Refactor invariants

1. State the behavior and contracts that must remain unchanged.
2. Characterize weakly tested behavior before moving it.
3. Name the current structural cost with evidence: duplication, dependency cycle, change amplification, state ambiguity, dead path, etc.
4. Prefer deletion, consolidation and existing abstractions over a new framework.
5. Move one seam at a time and keep the tree verifiable.
6. Do not mix product behavior changes into the refactor; create/link a feature or issue when required.
7. Review each meaningful diff internally and repair before continuing.
8. Prove equivalence at observable boundaries, not only compilation.

## Lane behavior

- `micro`: rename/local extraction/deletion with direct tests and no public/persistent impact.
- `standard`: multi-file structural improvement within a bounded subsystem.
- `high-risk`: dependency inversion across systems, persistent representation, public compatibility, concurrency/security boundary, or rollout requiring dual paths.

A large diff is a signal to split steps, not automatically proof that a high-risk architecture Gate is needed.

## Passive observation contract

When `/cs` supplies an observation `run_id`, reuse it; never start a duplicate trace. When this skill is invoked directly and no parent `run_id` exists, start one best-effort with `.codestable/tools/cs_observe.py start` after the work id and lane are known.

Append only meaningful metadata events (stage transition, tool failure/retry, Gate, user correction, verification). Never retrieve prior observations into delivery context and never record raw prompts, model replies, source contents, diffs, secrets, or private evaluator data. Finish the invocation with `cs_observe.py end`; signals only mark the observation `flagged` and do not trigger evolution.

## Completion contract

- characterization evidence covers the preserved behavior;
- the structural objective is demonstrably improved;
- no unrequested behavior change is present;
- obsolete paths/compatibility scaffolding are removed when safe;
- tests and quality checks pass after each critical seam and at the end;
- final diff is smaller/simpler than alternatives or its added structure has concrete necessity;
- durable architecture decisions/contracts are promoted only when the refactor changes current truth.
