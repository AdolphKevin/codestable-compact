# CodeStable Compact 0.4 vs 0.5 — real Codex Host campaign

Generated: `2026-07-14T17:38:18+08:00`

## Verdict

```text
ONE_TASK_QUALITY_PARITY; ROUTE_ACCURACY_10/10; RESOURCE_POINT_ESTIMATES_MIXED; CROSS_TASK_AND_CROSS_HOST_EFFECT_UNDERPOWERED
```

使用 `codex-cli 0.144.3`、`gpt-5.6-sol`、`workspace-write` 和 ignored user config，在新建 Git workspace 中随机串行运行 0.4 与 0.5 各 5 次。每次处理同一个 `dedupe` 性能缺陷，并由进程外确定性 verifier 检查顺序、接口和大输入性能。没有保存模型原始回复或任务级 trace。

| Metric (median) | 0.4.0, n=5 | 0.5.0, n=5 | Change |
|---|---:|---:|---:|
| External verifier pass | 5/5 | 5/5 | 0 pp |
| Correct `issue` route | 5/5 | 5/5 | 0 pp |
| Wall time | 189.2 s | 119.8 s | -36.7% |
| Tool calls | 21 | 12 | -42.9% |
| Total input tokens | 613,142 | 381,465 | -37.8% |
| Output tokens | 7,332 | 4,849 | -33.9% |
| Uncached tokens | 49,480 | 56,783 | +14.8% |

0.5 在这个任务上保持交付与路由正确，且完成更快、调用工具更少、总上下文吞吐更低；但 uncached token 中位数上升，不能据此宣称费用更低。只有每组五次的聚合中位数，没有 A/A 方差校准或多任务样本，因此资源变化是 measured point estimate，不是普遍因果效果。

## Evidence identity

- Baseline source SHA-256: `675369484f61ddbd42a36bd855cd2fb645f74205570b957faf9f9e3f24a1b722`
- Candidate source SHA-256: `3523f2156c3c77328402e1dfe4758a782c438fe5ccd03f622312a5707594e406`
- Timeout: 900 seconds per run
- Machine-readable aggregate: [`codex-host-campaign-0.4-vs-0.5.json`](codex-host-campaign-0.4-vs-0.5.json)

该 campaign 没有私有 held-out、外部 evaluator 签名或人工 Gate 场景，因此不能用于自动 policy promotion，也不能替代跨 Host campaign。
