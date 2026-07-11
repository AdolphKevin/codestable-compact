# CodeStable Compact 0.4.0 — Meta effect report

Generated: `2026-07-11T10:34:36+08:00`

## Verdict

```text
CONTROL_PLANE_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED
```

本报告验证的是 **Meta 控制面、评测效度防线与版本安全机制是否真实运行**。它不会把没有真实 Host Adapter 的 GPT / Claude Code / Cursor / Codex 行为标成提升。

## Evidence labels

| Label | Meaning | Result |
|---|---|---|
| `[measured]` | 直接执行的确定性测试/fixture | 6 evidence groups passed |
| `[soft]` | 设计或校准声明，可辅助判断 | 1 group |
| `[underpowered]` | 缺真实模型/宿主或样本不足 | 8 groups |

## Measured control-plane results

- Release validator: **PASS**.
- Unit tests: **54/54 passed**.
- Known-bad mutant detection: **13/13 passed**.
- Full Meta cycle: **PASS** — repeated feedback → campaign → committed hypothesis → Agent proposal → validity pre-pass → signed evaluation → scoped approval → promotion → rollback.
- Normal delivery isolation: **PASS** — passive observation may write, but normal `/cs` cannot import or read the Meta control plane.
- First-class policies: **9**; fixture-coverage audit: **PASS**.
- Registered public fixtures: **13**.
- Public fixture execution: **6 measured passed**, **0 failed**, **7 underpowered**.
- Automatic promotion eligibility without Host Adapter evidence: **False** (expected `False`).
- Fresh bootstrap + doctor + policy audit: **PASS**.

## Known-bad mutants exercised

- `test_policy.PolicyRegistryTest.test_no_fixture_coverage_no_evolution`
- `test_evolution.ManualEvolutionTest.test_proposal_must_be_agent_authored`
- `test_evolution.ManualEvolutionTest.test_proposal_without_required_fixture_layer_is_rejected`
- `test_evolution.ManualEvolutionTest.test_underpowered_prepass_cannot_create_evaluation_challenge`
- `test_meta_validity.MetaValidityAndAuthorityTest.test_missing_required_context_blocks_attribution`
- `test_meta_validity.MetaValidityAndAuthorityTest.test_brittle_oracle_blocks_evaluation`
- `test_meta_validity.MetaValidityAndAuthorityTest.test_uncalibrated_scorer_blocks_evaluation`
- `test_meta_validity.MetaValidityAndAuthorityTest.test_same_profile_judge_is_rejected`
- `test_evolution.ManualEvolutionTest.test_overlay_cannot_smuggle_undeclared_surface`
- `test_evolution.ManualEvolutionTest.test_signed_result_rejects_tampering_raw_trace_and_replay`
- `test_meta_validity.MetaValidityAndAuthorityTest.test_missing_measured_quality_gates_block_acceptance`
- `test_meta_validity.MetaValidityAndAuthorityTest.test_owner_checkpoint_cannot_be_downgraded_and_meta_rollback_works`
- `test_evolution.ManualEvolutionTest.test_corrupt_rollback_snapshot_blocks_promotion`

These checks cover missing fixture coverage, script-authored proposals, incomplete fixture layers, low-k stochastic evidence, missing context, brittle oracle, uncalibrated scorer, same-profile Judge, undeclared surface smuggling, signed-result tampering/replay, missing measured quality gates, authority downgrade and corrupt rollback snapshots.

## Baseline comparison

- No baseline source tree was supplied; capability comparison was not run.

## Public fixture result

| Fixture | Label | Status |
|---|---|---|
| `contract.active-artifact-schema` | `measured` | `passed` |
| `contract.gate-critical-invariants` | `underpowered` | `underpowered` |
| `contract.minimality-ladder` | `measured` | `passed` |
| `contract.normal-context-isolation` | `measured` | `passed` |
| `contract.playbook-bounded` | `measured` | `passed` |
| `e2e.explicit-stage-boundary` | `underpowered` | `underpowered` |
| `e2e.feature-review-loop` | `underpowered` | `underpowered` |
| `e2e.gate-calibration` | `underpowered` | `underpowered` |
| `e2e.normal-run-no-meta` | `measured` | `passed` |
| `e2e.resume-without-reload` | `underpowered` | `underpowered` |
| `regression.core-runtime` | `measured` | `passed` |
| `routing.auto-continue` | `underpowered` | `underpowered` |
| `routing.performance-to-issue` | `underpowered` | `underpowered` |

## What remains underpowered

The portable release did not execute live GPT 5.5/5.6, Claude Code, Cursor, ChatGPT Codex or other provider sessions. The following claims therefore remain underpowered until an adapter runs the same baseline/candidate challenge with an exact Runtime Profile:

- route accuracy and continuous execution under each host/model;
- Gate precision/recall and checkpoint behavior;
- token/context/tool-call cost comparison;
- long-running lifecycle adherence;
- real project delivery improvement and cross-task knowledge utility;
- portability of a promoted policy across profiles.

Host-dependent fixtures correctly returned `underpowered` instead of being silently counted as pass. This is the intended Goodhart/overclaiming safeguard.

## Candidate identity

- Version: `0.4.0`
- Python: `3.10.20`
- Platform: `macOS-15.7.1-arm64-arm-64bit`

Machine-readable report: [`meta-effect-report.json`](meta-effect-report.json).
