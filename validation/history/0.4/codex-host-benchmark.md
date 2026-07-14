# CodeStable 0.3 vs 0.4 — real Codex host benchmark

## Verdict

```text
NO_QUALITY_DELTA_MEASURED; COST_REGRESSION_POINT_ESTIMATE; EFFECT_ATTRIBUTION_UNDERPOWERED
```

The real Codex CLI completed 15 isolated runs of the same deterministic performance-fix task. All runs passed the external verifier.

| Metric (median) | 0.3.0, n=10 | 0.4.0, n=5 | Change |
|---|---:|---:|---:|
| Verifier pass rate | 100% | 100% | 0 pp |
| Wall time | 167.7 s | 176.8 s | +5.5% |
| Uncached tokens | 43,781 | 50,678 | +15.8% |
| Total input tokens | 525,190 | 585,260 | +11.4% |
| Output tokens | 6,170 | 6,215 | +0.7% |
| Tool calls | 19 | 20 | +5.3% |

Runtime Profile: `codex-cli 0.144.1`, `gpt-5.6-sol`, `workspace-write`, user config ignored. Each run used a fresh Git workspace, the exact same task and an external deterministic verifier. Raw model responses and task-level traces were not retained.

## A/A calibration

The ten 0.3 runs were split into two groups of five. Baseline-to-baseline median differences were substantial:

- wall time: -24.6%;
- uncached tokens: -5.4%;
- total input tokens: -15.1%;
- output tokens: -14.2%;
- tool calls: -10.5%.

Therefore the A/B point estimates do not establish a causal cost regression. They do establish that 0.4 did not produce an observable quality gain on this task, while its measured resource use was not lower.

## Limits

- One synthetic task cannot establish cross-task delivery quality.
- No route/Gate conclusion is available because the runs produced no readable route state.
- ChatGPT login exposed token usage but no trustworthy USD price.
- This is measured host execution evidence, not a signed private-held-out promotion evaluation.

Machine-readable evidence: [`codex-host-benchmark.json`](codex-host-benchmark.json).
