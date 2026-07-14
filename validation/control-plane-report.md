# CodeStable Compact control-plane validation

Generated: `2026-07-14T19:05:29+08:00`
Version: `0.5.0`

## Verdict

```text
PASS
```

Executed **52** Harness commands and passed **22/22** assertions across L0, L2, L3, provenance, side-effect, status-classification and tamper scenarios.

## Measured checks

| Check | Result |
|---|---|
| runtime initialized | PASS |
| L0 completion denied without evidence | PASS |
| side-effect boundary rejects undeclared path | PASS |
| artifact records cannot impersonate command evidence | PASS |
| Harness recorded command exit codes | PASS |
| unregistered Git-visible write blocks completion | PASS |
| L0 completed after exact evidence | PASS |
| completed tampered evidence cannot be archived | PASS |
| completed work archived | PASS |
| L0 evidence chain valid | PASS |
| L2 state snapshots and integration passed | PASS |
| declared Owner producer cannot supply independent review | PASS |
| L2 review has a declared distinct producer and proof is derived | PASS |
| completed verdict survives reload | PASS |
| L2 evidence chain valid | PASS |
| critical executable path escalates L0 to L3 | PASS |
| all L3 evidence sources passed | PASS |
| L3 completed only after full policy | PASS |
| untracked critical directory expands to executable files and escalates risk | PASS |
| PASS/FAIL/BLOCKED/PARTIAL remain distinct | PASS |
| blocked command has no fabricated exit code | PASS |
| evidence tampering detected by doctor | PASS |

## What was actually demonstrated

- `done` was rejected before required evidence and artifact records could not impersonate command evidence.
- Unregistered Git-visible writes were detected and rejected by the side-effect boundary.
- Real command exit codes were captured by the Harness.
- The declared Owner producer was rejected for L2 review; a declaratively distinct artifact-backed producer plus machine proof was required.
- A critical executable authorization path dynamically escalated L0 to L3 and replaced the evidence policy.
- An untracked critical directory was expanded to its executable file before risk classification.
- `PASS`, `FAIL`, `BLOCKED` and `PARTIAL` remained distinct.
- Evidence-chain tampering caused `doctor` to fail with an integrity finding.
- Completed state survived reload, while later evidence tampering blocked archive without erasing the historical verdict.

## Proof artifacts

Preserved under `validation/control-plane-artifacts`. The JSON report records SHA-256 for every artifact.

Machine-readable report: [`control-plane-report.json`](control-plane-report.json).
