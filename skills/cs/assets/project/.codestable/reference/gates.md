# Boundary and completion policy

CodeStable has two different controls. Do not conflate them.

## Side-effect authorization Gate

Pause only when execution needs authority that the task contract does not grant, including:

- irreversible or destructive operations;
- security, permission, secret or trust-boundary decisions;
- persistent data migration without an approved strategy;
- materially different public compatibility choices;
- financial, availability or operational exposure;
- an unresolved accepted-decision conflict;
- unavailable access needed for observable acceptance;
- explicit user approval;
- policy-scoped Harness promotion.

A Gate contains the exact operation/decision, evidence, affected boundary, recommendation, alternatives, consequences and the smallest blocked scope. Route choice, ordinary design review and test repair are not Gates.

## Risk-adaptive completion Gate

The Harness derives required evidence from current risk:

```text
L0 Trivial      diff_check + format_check
L1 Local        scope_inspect + targeted_test + lightweight_review
L2 Cross-module audit_ledger + proposal + integration_test + independent_review + proof
L3 Critical     full_audit + invariant_contract + live_validation + rollback_proof
                + independent_review + regression_fixture
```

Risk can increase when changed paths, side-effect categories or discovered system impact expand. The stronger policy replaces the weaker one immediately.

Completion is denied when any required current-bound PASS evidence is absent, stale or narrower than its declared acceptance scope; when the evidence chain is invalid; when the Git baseline is unavailable; when a Git-visible change is unregistered/outside scope; when a blocking assumption/risk/blocker remains; when L2/L3 invariants are missing; or when the declared review producer is the Owner. Source, registered-change, relevant-state, proposal, invariant and acceptance hashes are re-evaluated on every gate check. Independent review additionally binds the reviewed diff, and external artifacts are re-fingerprinted. Portable reviewer identity is declarative unless a Host Adapter provides trusted attestation.

A stale PASS is retained as historical evidence but cannot satisfy the current requirement. The gate reports `evidence.<type>.stale` or `evidence.<type>.scope` with the affected evidence ID, so the Agent knows exactly which verification must be rerun.

Archive rechecks current evidence integrity and completion eligibility. A historical `COMPLETED` verdict remains recorded after later tampering, but invalid state cannot be archived as valid completion.

`BLOCKED` and `PARTIAL` are legitimate terminal reports for an invocation, but neither grants `done` or archive eligibility.
