# Problem / solution map

| Production problem | Compact 0.5 control |
|---|---|
| AI follows a human hand-off workflow | Repeated `inspect / propose / execute / verify / learn` actions; no fixed order |
| “Analysis completed” is proved by documents | Facts, assumptions, risks and unknowns live in the state ledger; only useful artifacts persist |
| Code written is confused with task completed | Harness owns completion and checks behavior evidence |
| Agent reports tests without proof | `verify` executes commands and records exit/timing/output/artifacts |
| Environment failure is confused with business failure | Separate `PASS / FAIL / BLOCKED / PARTIAL` statuses |
| Initial scope underestimates real impact | Git-visible paths since the task baseline and declared side effects monotonically escalate risk |
| Configuration can silently weaken quality | Bootstrap/runtime repair exact canonical risk policies |
| Owner reviews its own work | L2/L3 review rejects the Owner producer label and requires an artifact; trusted identity is adapter-attested |
| A summary invents proof | Machine-generated proof can only reference existing valid evidence |
| Old and new implementations coexist | Reviewer and completion challenge residual dual paths; refactor acceptance includes deletion |
| Long process documents pollute context | Durable artifact requires a named consumer; session analysis stays local |
| Every task pays the same process cost | L0–L3 adaptive evidence policies |
| Traditional department roles are simulated | Only Owner, Harness and Reviewer responsibility boundaries |
| Normal delivery self-optimizes circularly | Normal/Meta planes are structurally isolated |
| Harness changes without regression coverage | No fixture coverage, no evolution |
| Optimizer grades itself | External signed aggregate evaluator, private holdout and judge isolation |
| Same failure repeats after retrospective | Learning must enter fixture/rule/invariant/checker path |

## Completion is a conjunction

```text
clear goal
+ bounded side effects
+ sufficient facts
+ no blocking uncertainty
+ risk-appropriate PASS evidence
+ valid independent challenge where required
+ intact evidence chain
= eligible for Harness completion
```

No single document, test command, reviewer sentence or Owner confidence can independently grant completion.
