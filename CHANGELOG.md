# Changelog

## 0.3.0 — 2026-07-10

- Replaced continuous telemetry/evolution semantics with **Always observable, selectively evolvable**.
- Added `cs_observe.py` for best-effort temporary `pending / flagged / selected` observations.
- Added read-only `cs_harness.py` so normal work can use promoted rules without entering the evolution control plane.
- Made normal `/cs` explicitly write-only for observations and prohibited history retrieval or automatic evolution.
- Removed threshold campaigns, auto-diagnosis, auto-proposal, direct `eval-record`, auto-promotion and automatic canary evolution.
- Added explicit evidence selection and diagnosis classes before candidate creation.
- Added immutable `cs_eval.py` challenges, evaluator-only HMAC signing, baseline content and candidate definition/content locks, plus aggregate result import with lock/hash/replay/schema checks.
- Made every Harness promotion require a human Gate, actor and reason.
- Added immutable Harness snapshots, lineage and explicit rollback; promotion/rollback now reject corrupted version snapshots.
- Added 0.2-alpha telemetry migration, config schema migration, new adapter contract and expanded tests.

## 0.2.0-alpha — 2026-07-10

- Added a separate, bounded Harness-evolution outer loop without changing the `/cs` delivery UX.
- Added structured run telemetry and verifier-grounded failure signatures.
- Added declared editable/protected surfaces and candidate overlays.
- Added campaign locks, held-in/held-out/safety evaluation records and conservative promotion decisions.
- Added Harness version snapshots, lineage, canary decisions and rollback.
- Added a structured incremental playbook and scoped retrieval.
- Kept private held-out tasks and evaluator implementation outside the portable package.

## 0.1.0 — 2026-07-10

- Introduced `/cs` as an auto-routing and auto-executing entry.
- Collapsed feature, issue, refactor and roadmap sub-stages into lifecycle skills.
- Added risk-based human Gates and automatic internal review loops.
- Added hash-based context receipts and stage-specific read plans.
- Made archived work opt-in for retrieval.
- Added a dependency-free runtime, migration helper, validation and tests.
