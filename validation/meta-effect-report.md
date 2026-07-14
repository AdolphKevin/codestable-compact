# CodeStable Compact 0.5.0 — control-plane and Meta effect report

Generated: `2026-07-14T19:08:03+08:00`

## Verdict

```text
CONTROL_AND_META_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED
```

本报告分别验证生产控制平面与 Meta 演进控制面，并引用独立的真实 Codex Host campaign。确定性结果来自真实运行的命令、测试、fixture、完整性检查与回滚检查；单任务 Host 结果不会被外推成跨任务或跨 Host 提升。

## Evidence labels

| Label | Meaning | Result |
|---|---|---|
| `[measured]` | 直接执行的确定性验证组 | 7 groups passed |
| `[soft]` | 设计或校准声明，可辅助判断 | 1 group |
| `[underpowered]` | 缺真实模型/宿主或样本不足 | 8 groups |

## Measured production control-plane results

- Evidence-state scenarios: **22/22 passed** across **52 Harness commands**.
- Completion without required evidence: **REJECTED**.
- Undeclared side effects: **REJECTED**.
- Verification provenance: **PASS** — the Harness executed commands and captured actual exit codes.
- L2 review producer boundary: **PASS** — the declared Owner producer was rejected; portable identity assurance remains declarative.
- Dynamic risk escalation: **PASS** — a critical authorization path upgraded L0 to L3 and replaced the evidence policy.
- Evidence semantics: **PASS** — `PASS`, `FAIL`, `BLOCKED`, and `PARTIAL` remained distinct.
- Evidence integrity: **PASS** — tampering caused `doctor` to fail.

## Measured Meta and release results

- Release validator: **PASS**.
- Unit tests: **67/67 passed**.
- Known-bad mutant detection: **13/13 passed**.
- Full Meta cycle: **PASS** — repeated feedback → campaign → committed hypothesis → Agent proposal → validity pre-pass → signed evaluation → scoped approval → promotion → rollback.
- Normal delivery isolation: **PASS** — passive observation may write, but normal `/cs` cannot import or read the Meta control plane.
- First-class policies: **9**; fixture-coverage audit: **PASS**.
- Registered public fixtures: **13**.
- Public fixture execution: **6 measured passed**, **0 failed**, **7 underpowered**.
- Automatic promotion eligibility without Host Adapter evidence: **False** (expected `False`).
- Fresh bootstrap + doctor + policy audit: **PASS**.

## Measured Codex Host result

- Runtime Profile: `codex-cli 0.144.3`, `gpt-5.6-sol`, `workspace-write`, ignored user config.
- External verifier: baseline **5/5**, candidate **5/5**.
- Correct `issue` route: baseline **5/5**, candidate **5/5**.
- Candidate median point estimates: wall time **-36.7%**, tool calls **-42.9%**, total input **-37.8%**, output **-33.9%**, uncached tokens **+14.8%**.
- Scope: one public synthetic task; no private held-out, signed evaluator or Gate scenario. See [`codex-host-campaign-0.4-vs-0.5.md`](codex-host-campaign-0.4-vs-0.5.md).

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

- Baseline version: `0.4.0`; tests: **56/56 passed**.
- Candidate version: `0.5.0`; tests: **67/67 passed**.

| Property | Baseline | Candidate |
|---|---|---|
| Active-state mode | `adaptive` | `evidence_state` |
| Execution control | `continuous_until_gate` | `evidence_convergence` |
| `evidence.jsonl` required | `False` | `True` |
| Lane/stage workflow cursor | `True` | `False` |
| Harness-executed verification | `False` | `True` |
| Hash-chained evidence | `False` | `True` |

The comparison demonstrates added, regression-tested evidence-state behavior while retaining the 0.4 Meta safety plane. It does not establish universal model-quality improvement.

## Public fixture result

| Fixture | Label | Status |
|---|---|---|
| `contract.active-artifact-schema` | `measured` | `passed` |
| `contract.gate-critical-invariants` | `underpowered` | `underpowered` |
| `contract.minimality-ladder` | `measured` | `passed` |
| `contract.normal-context-isolation` | `measured` | `passed` |
| `contract.playbook-bounded` | `measured` | `passed` |
| `e2e.evidence-repair-loop` | `underpowered` | `underpowered` |
| `e2e.gate-calibration` | `underpowered` | `underpowered` |
| `e2e.normal-run-no-meta` | `measured` | `passed` |
| `e2e.resume-without-reload` | `underpowered` | `underpowered` |
| `e2e.side-effect-boundary` | `underpowered` | `underpowered` |
| `regression.core-runtime` | `measured` | `passed` |
| `routing.auto-continue` | `underpowered` | `underpowered` |
| `routing.performance-to-issue` | `underpowered` | `underpowered` |

## What remains underpowered

The release executed one real Codex CLI / GPT-5.6 campaign. Claude Code, Cursor, Gemini, multi-task and private held-out campaigns were not executed, so the following claims remain underpowered:

- route accuracy and autonomous evidence convergence across tasks and other host/model profiles;
- completion-gate precision/recall and intervention behavior;
- token/context/tool-call cost comparison;
- real-project delivery improvement and cross-task knowledge utility;
- portability of a promoted policy across profiles.

Host-dependent fixtures correctly returned `underpowered` instead of being silently counted as pass. This is the intended Goodhart/overclaiming safeguard.

## Candidate identity

- Version: `0.5.0`
- Python: `3.10.20`
- Platform: `macOS-15.7.1-arm64-arm-64bit`

Machine-readable reports: [`meta-effect-report.json`](meta-effect-report.json) and [`control-plane-report.json`](control-plane-report.json).
