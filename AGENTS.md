# Repository guidance

This repository contains portable Agent Skills. Canonical behavior lives under `skills/`; host-specific adapters remain under `adapters/`.

When changing a workflow:

1. Preserve `/cs` route-and-continue in the same invocation.
2. Do not add user-visible skills for internal phases, reviewer roles or optimizer roles.
3. Keep archive, observation, feedback, Meta, evaluation and Harness-history retrieval out of normal delivery context.
4. Normal Skills may append one passive schema-v4 observation, but must never import `cs_meta.py` or diagnose/propose/evaluate/promote.
5. Pass one observation `run_id` through nested outcome skills; record only compact action, evidence status, risk escalation, completion, Gate, checkpoint, intervention, policy, knowledge and aggregate-cost metadata.
6. Never log raw prompts, model responses, source contents, diffs, secrets, private fixtures or task-level evaluator traces.
7. Normal active-rule retrieval must use read-only `cs_harness.py`.
8. Treat Harness policy as first-class: every evolvable policy needs an editable surface, allowed change type, fixture IDs, required layers and approval authority.
9. Enforce **no fixture coverage, no evolution**. Add/repair fixtures before optimizing an uncovered policy.
10. Production feedback must be triaged as Harness policy, evaluation defect, model-profile variance, project knowledge, product code, environment or insufficient evidence.
11. The Agent writes hypothesis, variant document, proposal and minimal overlay; deterministic scripts only validate, lock, measure, label, record and enforce budgets/authority.
12. A claimed gain or negative verdict requires a passing validity pre-pass: complete context, tolerant oracle, calibrated scorer, stochastic `k>=5`, judge isolation and committed provenance.
13. Evidence labels are `measured`, `soft` and `underpowered`; never promote from underpowered evidence.
14. `trigger-scan` is preview-first. Applying it may only create bounded campaigns, never diagnose, propose, evaluate, accept or promote.
15. Candidates may modify only policy-declared surfaces; protected control-plane paths remain immutable.
16. Runtime profile (host, model, adapter, budget/toolset) is part of evidence identity; do not merge incompatible profile results.
17. Never expose private held-out fixtures or evaluator signing keys to worker/proposer/candidate processes.
18. Do not accept direct unsigned evaluation records; use immutable challenge plus signed aggregate import.
19. Approval authority comes from the policy registry: routing/Gate/evidence-convergence/schema/runtime changes require owner checkpoint; only declared low-risk changes may use Agent approval after measured gates.
20. Every promotion needs accepted evaluation, measured quality gates, immutable snapshot and rollback path; keep rejected variants/evidence indexed.
21. Prefer existing state/reference files over new artifacts and use Python standard library unless a dependency is proven necessary.
22. Run `python3 scripts/validate_skills.py`, `python3 scripts/validate_control_plane.py`, `python3 scripts/validate_meta_effect.py`, and `python3 -m unittest discover -s tests -v` before release.
