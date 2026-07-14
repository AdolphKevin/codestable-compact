# Changelog

## 0.5.0 — 2026-07-14

- Repositioned CodeStable Compact as a software-production control plane: Agent-selected paths inside Harness-controlled objective, fact, side-effect, validation and completion boundaries.
- Replaced the lane/stage workflow cursor with one evidence-state task model covering goal, proposal, facts, assumptions, risks, changes, evidence, blockers and completion.
- Added repeatable `inspect`, `propose`, `execute`, `verify` and `learn` actions without treating them as ordered phases.
- Added risk-adaptive L0–L3 evidence policies, monotonic runtime escalation and exact completion requirements.
- Added append-only, SHA-256-chained `evidence.jsonl`; command verification is executed by the Harness and records command, cwd, exit code, bounded output, duration and artifacts.
- Distinguished `PASS`, `FAIL`, `BLOCKED` and `PARTIAL`; prevented unavailable environments and partial evidence from masquerading as business-test failures or passes.
- Enforced side-effect allowlists, independent L2/L3 review, machine-derived proof, L3 rollback evidence and completion-verdict persistence across reload/archive.
- Rewrote the public skills and hidden references around evidence convergence, removed fixed-phase references and renamed the canonical lifecycle reference to `control-plane.md`.
- Updated passive observation to schema v4 with action, risk, evidence and completion metadata while preserving strict normal-run isolation from Meta history.
- Preserved the explicit, fixture-covered Meta evolution plane and renamed the lifecycle policy/fixtures around evidence convergence and repair.
- Added an isolated control-plane effect validator covering L0/L2/L3 completion, side effects, real command provenance, reviewer independence, dynamic escalation, status semantics and tamper detection.

## 0.4.0 — 2026-07-10

- Made Harness policy a first-class, fixture-covered object through `meta/policy-registry.json`; enforced **no fixture coverage, no evolution**.
- Added schema-v3 passive traces for stage, Gate outcome/reason, checkpoints, human interventions, token aggregates, policy activation and knowledge read/write metadata.
- Added `cs_feedback.py` for production observation triage and feedback-to-regression-fixture registration.
- Added explicit `cs_meta.py` orchestration for signal scans, campaigns, diagnosis, committed hypothesis freezing, Agent-authored proposal registration, validity pre-pass, quality gates, scoped acceptance, promotion and rollback.
- Kept normal `/cs` write-only for observations and structurally isolated from the Meta/evaluation control plane.
- Added dry-run-first repeated-signal aggregation; `--apply` can only open bounded campaigns and cannot propose/evaluate/promote.
- Added `cs_fixture.py` with `[measured]`, `[soft]` and `[underpowered]` evidence labels; missing real host adapters remains underpowered.
- Added mandatory validity checks for fixture context, required references, oracle tolerance, scorer calibration, stochastic `k>=5`, judge isolation and committed provenance.
- Enforced Agent-authored variants while keeping deterministic scripts limited to validation, locking, measurement and bookkeeping.
- Replaced one-size-fits-all human promotion with policy/change-type authority: low-risk prompt/playbook changes may use Agent approval after measured gates; routing, Gate, lifecycle, schema and runtime changes require owner approval.
- Linked accepted/rejected strategy evidence to policy, fixtures, hypothesis, candidate, runtime profile, evaluation, quality gates and immutable Harness lineage.
- Added public routing/contract/e2e/regression fixtures, policy coverage audits, known-bad mutant checks and a labelled Meta effect report.

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
