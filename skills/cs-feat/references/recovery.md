# Recover inconsistent active work

Recovery reconciles the evidence state; it does not infer a missing workflow stage.

## Inspect before changing state

Read `state.json`, `context.json`, `evidence.jsonl`, registered paths and repository status. Run the Harness doctor. Treat a broken evidence hash chain, missing artifact fingerprint or out-of-bound write as a blocker rather than reconstructing proof from prose.

## Reconcile safely

- restore or migrate legacy state through the runtime;
- re-register actual changed paths inside the authorized boundary;
- re-run command evidence whose artifact or environment is no longer trustworthy;
- resolve assumptions/risks only with a cited result;
- preserve `FAIL`, `BLOCKED` and `PARTIAL` history;
- escalate risk when recovered scope is wider than declared.

Do not fabricate old validation as current evidence. Do not mark completion merely because code appears finished. If repository state cannot be reconciled without destructive action, record a blocker and require the relevant authorization or rollback decision.
