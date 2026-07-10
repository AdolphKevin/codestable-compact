# Feature: verification, acceptance, promotion and archive

## Verification

Build a verification matrix from the original acceptance, not from the implementation:

| Acceptance / risk | Evidence |
|---|---|
| primary behavior | automated test or direct observable run |
| boundary/error | negative or edge test |
| compatibility | old-client/old-data test when relevant |
| quality | project lint/typecheck/build/test commands |
| rollout/operation | migration dry run, metric/log or rollback exercise when relevant |

Run relevant project-standard checks. Do not claim success from code inspection alone when executable verification is available.

If a check fails:

1. determine whether code, design, test or environment is wrong;
2. return to the responsible stage;
3. repair;
4. rerun affected checks and the acceptance matrix.

Unavailable infrastructure is a Gate only when no local substitute or evidence can establish acceptance.

## Acceptance review

Compare result with every intent/non-goal/compatibility statement. Inspect the final diff once more for accidental scope expansion. Separate required follow-ups from optional improvements.

Do not create an `acceptance.md`; append concise evidence and conclusion to `work.md`.

## Promotion

Promote only durable information:

- current capability → `model/requirements/`;
- public event/API/schema → `model/contracts/`;
- architecture trade-off constraining future work → `model/decisions/`;
- domain language → `model/domain.md`;
- reusable pitfall/diagnostic/constraint → `knowledge/notes/`.

Update the corresponding INDEX row. Do not promote local execution logs, rejected local alternatives or generic advice.

## Close

Set validation result, mark status done and archive with an evidence-based summary. After archive, future normal search must use current model/knowledge, not this work history.
