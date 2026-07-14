# Harden evidence-state completion controls

- Work: `2026-07-14-harden-evidence-state-controls`
- Kind: `issue`
- Lane: `high-risk`

## 1. Intent and acceptance

- Outcome: Harness completion accepts only policy-valid evidence, covers every actual Git change, blocks invalid-ledger archive, and binds test evidence to source bytes only.
- Acceptance: The five reproduced bypasses fail; existing 0.4/0.5 regression, control-plane, Meta and release checks pass.
- Non-goals: Cryptographic reviewer identity without a Host Adapter; replacing the existing local hash-chain design.

## 2. Evidence

- Repository observations: Generic artifact records can satisfy command-backed evidence; unregistered writes can complete; completed tampered ledgers can archive; untracked directories evade risk scanning; source hashes include `.git`.
- Relevant current model / executable contracts:
- Baseline or reproduction: Each defect was reproduced in an isolated temporary project before edits.

## 3. Design or root cause

- Chosen mechanism / root cause: Completion validates evidence provenance and a task-scoped Git baseline; archive rechecks integrity; Git enumeration expands untracked files; release hashing excludes control metadata.
- Existing path reused: `completion_snapshot`, `collect_git_changes`, artifact fingerprints, and existing unittest/control-plane scenarios.
- Alternatives rejected and why: No new service, dependency, signing protocol or filesystem watcher; reviewer identity remains explicitly declarative until a Host Adapter can attest it.
- Compatibility / rollback / rollout (when relevant):

## 4. Plan

- [x] Add failing regression coverage for each reproduced bypass.
- [x] Apply the smallest shared-runtime fixes.
- [x] Re-run targeted, release, control-plane and Meta verification.
- [x] Regenerate source-bound validation artifacts and summary.

## 5. Changes and decisions

- Changed: Added requirement-to-source validation, task-start Git baseline comparison, untracked-file expansion, executable-only critical path classification, integrity-aware archive gating and stable release source hashing.
- Changed: Added five negative runtime tests, one observation CLI regression test, and extended the isolated control-plane scenario from 18 to 22 assertions.
- Decisions made during execution: Portable reviewer identity remains declarative; the runtime rejects the declared Owner producer but leaves trusted identity attestation to Host Adapters.
- Decisions made during execution: Side-effect completion checks are explicitly Git-visible and require a Git worktree, including `--no-writes` tasks.

## 6. Verification and review

- Commands and results: `python3 scripts/validate_skills.py` — PASS.
- Commands and results: `python3 scripts/validate_control_plane.py --baseline <0.4 archive>` — 22/22 assertions, 52 Harness commands, PASS.
- Commands and results: `python3 -m unittest discover -s tests -v` — baseline 56/56 and candidate 67/67, PASS.
- Commands and results: `python3 scripts/validate_meta_effect.py --baseline <0.4 archive> --candidate-test-evidence ... --baseline-test-evidence ...` — CONTROL_AND_META_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED.
- Observable acceptance evidence: `validation/control-plane-report.json`, `validation/meta-effect-report.json`, source-bound unittest evidence and release manifest share the candidate source SHA-256 `c9f37692ca431b32ab10391ace5f04b18c1071918fa14f3637d954612e481dca`.
- Internal review findings and repairs: Removed overclaiming around reviewer identity, documented Git-worktree dependence, and verified generated validation state no longer changes the source hash.

## 7. Promotion and closure

- Model updates: None; the runtime, tests and public control-plane documentation are the durable source of truth.
- Knowledge promoted: None; no separate note is needed for a behavior already enforced by tests and references.
- Remaining follow-ups: Real host/model route accuracy, convergence, cost and delivery impact remain underpowered pending Host Adapter campaigns.
- Closure summary: All five reproduced control-plane defects plus the observation CLI defect found during closure are fixed; regression coverage passes, release evidence is regenerated, and no commit was created.
