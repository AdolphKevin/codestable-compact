# Issue: fix, review, verification and closure

## Fix

Implement the smallest coherent root-cause correction:

1. preserve unrelated behavior;
2. reuse the existing path and conventions;
3. add a regression test at the closest observable boundary;
4. avoid compatibility shims unless an actual supported contract requires them;
5. avoid bundling cleanup or architecture work not necessary for the fix;
6. for performance, change the measured bottleneck and keep the benchmark comparable.

If implementation evidence disproves the root cause, stop editing, return to `analyze`, update the record and continue.

## Internal diff review

Inspect the actual diff for:

- incomplete cause coverage;
- new failure modes or stale state;
- concurrency/retry/idempotency effects;
- error masking and observability loss;
- public or persistent compatibility;
- security/data exposure;
- over-broad changes and speculative abstraction;
- regression tests that cannot fail under the old behavior.

Repair and re-review automatically. Record material findings only.

## Verify

Verification must include the original signal:

- run the reproduction/characterization against the fix;
- run targeted regression tests;
- run relevant project lint/typecheck/build/test;
- exercise boundary/error cases;
- for performance, compare equivalent before/after samples and report variance, not one flattering run;
- inspect final diff and working tree for unrelated changes.

A fix is not accepted merely because “tests pass” when those tests do not observe the original symptom.

## Promote and close

Promote a knowledge note only when the diagnostic, pitfall or invariant is likely to recur. Update model when the fix reveals a durable requirement/contract/decision. Do not promote a step-by-step local debugging diary.

Mark done and archive with symptom, root cause, fix and evidence in a compact summary.
