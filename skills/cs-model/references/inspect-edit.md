# Model: inspect and edit

## Inspect evidence

Start from the exact requested concept and `model/INDEX.md`; do not open every model document. Inspect relevant code/tests/config and accepted decisions when needed.

Classify each statement:

- current truth/requirement;
- proposed future behavior;
- accepted decision;
- superseded history;
- reusable engineering knowledge;
- task-specific process detail.

Only the first three belong in current model; reusable knowledge goes to knowledge; the rest stays in work/archive.

When sources conflict, use this decision order:

1. explicit current user/product authority;
2. accepted requirement/contract/decision;
3. executable tests and externally supported behavior;
4. implementation details;
5. historical work prose.

Do not hide drift. State the conflict and create/link executable work if alignment is needed.

## Edit by mode

### Vision

Keep purpose, boundaries and durable success criteria. Avoid quarter-specific task lists.

### Domain

Use the project's actual language. Record meaning, aliases and invariants. Remove or mark replaced terms; do not invent synonyms for style.

### Requirement

Describe actor/context, observable capability, boundaries and acceptance examples. Link contracts/decisions; omit implementation plan.

### Contract

Describe inputs/outputs, compatibility, failure semantics, versioning and ownership. Include persistent/event/API shape only at the appropriate precision.

### Decision

Record context, decision, consequences, status and supersession. A decision requires a real trade-off that constrains future work; ordinary local implementation choices stay in `work.md`.

### Knowledge

State trigger, symptom/risk, explanation, proven response, evidence and last validation. It must help a future task without reading the original archive.

## Minimal edit

Prefer modifying the existing canonical document and deleting duplicate statements. Do not create a new file merely because a new task mentioned the concept.
