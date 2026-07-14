# Validation artifacts

## Current 0.5 evidence

- [`refactor-summary.md`](refactor-summary.md) — implementation scope, architectural delta, measured results and remaining limits.
- [`control-plane-report.md`](control-plane-report.md) / [`control-plane-report.json`](control-plane-report.json) — isolated L0/L2/L3 evidence-state, side-effect, reviewer, status and integrity scenarios.
- [`meta-effect-report.md`](meta-effect-report.md) / [`meta-effect-report.json`](meta-effect-report.json) — release checks, fixture-covered Meta loop and baseline/candidate comparison.
- [`codex-host-campaign-0.4-vs-0.5.md`](codex-host-campaign-0.4-vs-0.5.md) / [`codex-host-campaign-0.4-vs-0.5.json`](codex-host-campaign-0.4-vs-0.5.json) — real Codex CLI 0.4/0.5 A/B on one public performance-fix task, five runs per variant.
- [`candidate-0.5-test-evidence.json`](candidate-0.5-test-evidence.json) / [`candidate-0.5-unittest.log`](candidate-0.5-unittest.log) — source-bound 67-test candidate evidence.
- [`baseline-0.4-test-evidence.json`](baseline-0.4-test-evidence.json) / [`baseline-0.4-unittest.log`](baseline-0.4-unittest.log) — source-bound 56-test unpacked-baseline evidence.
- [`release-validator.log`](release-validator.log), [`control-plane-validator.log`](control-plane-validator.log), and [`meta-effect-validator.log`](meta-effect-validator.log) — concise command outputs from the final release checks.

The control-plane proof directories preserve task state, hash-chained ledgers, machine proof and tamper samples. Their SHA-256 values are recorded in `control-plane-report.json`.

## Historical evidence

The 0.4 host and self-evolution experiments are preserved under [`history/0.4/`](history/0.4/). They are historical inputs, not evidence for the 0.5 production control plane.
