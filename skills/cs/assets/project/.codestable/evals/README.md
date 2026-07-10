# Evaluation and validity boundary

`protocol.json` defines protected evaluation conditions: proposal authorship, fixture coverage, validity pre-pass, minimum repeats, required held-in/held-out/safety splits, aggregate-only result schema, non-regression rules and policy-scoped promotion authority.

Public fixtures live under `fixtures/` and declare:

- first-class policies covered;
- routing/contract/e2e/regression layers;
- onboarding and subject-matter context;
- tolerant oracle;
- calibrated scorer evidence;
- deterministic or stochastic execution;
- local runner or required host adapter.

`cs_fixture.py` can measure deterministic public fixtures locally. Host/model-dependent fixtures are explicitly `underpowered` when no real adapter is provided; they are never silently counted as measured success.

Private held-out fixtures and the evaluator implementation stay outside candidate workspace. The project receives only aggregate results signed with an evaluator-only key. `cs_eval.py import` verifies challenge/nonce, baseline and candidate hashes, proposal/validity/fixture locks, model/adapter/budget profile, required metrics, result size/schema and signature.
