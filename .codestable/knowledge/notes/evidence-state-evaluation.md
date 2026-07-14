# Evidence-state 交付评测判读

- Status: current
- Last validated: `2026-07-14`
- Applies to: Harness 版本对比、Host campaign、资源指标解释、completion quality

## Trigger

当一次 Harness 或 Skill 改动表现为更少的 tool calls、更短耗时或更低 token 用量时，用本条目判断它是有效提效还是跳过了必要工作。

## Current rule

1. Tool calls 是 adapter 定义的资源代理，不是交付质量指标，也不能单独作为 promotion Gate。
2. 先比较外部 acceptance/verifier、正确路由、风险对应证据、副作用边界、回归结果和 completion integrity；这些不退化后，资源下降才可描述为效率改善。
3. 更少调用如果来自重复读取、阶段切换或 bookkeeping，是可接受收敛；如果来自省略 Inspect、验证、Reviewer 或边界检查，就是质量风险。
4. 总 input、cached input、uncached input、output、tool calls 和耗时必须分别报告。总 input 下降而 uncached input 上升时，不能宣称 token 成本整体下降。
5. 每个结果必须绑定 exact host/model/adapter/budget/source identity。单任务或单 Host 的中位数只能作为 measured point estimate，不能外推成跨任务因果效果。
6. 跨任务质量、completion precision/recall 或 policy promotion 需要多任务 held-out、`k>=5`、有效性预检、独立 evaluator；需要 trusted promotion 时还必须使用私有 held-out 和签名 aggregate。

## Current measured boundary

在 source SHA-256 `3523f2156c3c77328402e1dfe4758a782c438fe5ccd03f622312a5707594e406` 上：

- 静态与回归证据为 candidate `67/67`、控制平面 `22/22`、已知负向防线 `13/13`；
- 一个真实 Codex CLI / GPT-5.6 性能修复任务中，0.4 与 0.5 都是 verifier `5/5`、正确 `issue` route `5/5`；
- 0.5 的 tool calls 中位数下降 `42.9%`，但 uncached tokens 上升 `14.8%`；这证明该任务上的资源点估计发生变化，不证明普遍质量或费用提升；
- Claude Code、Cursor、Gemini、多任务、私有 held-out、签名 evaluator 和人工 Gate 场景仍未测。

## Proven response

看到“tool calls 下降”时，按以下顺序评审：

1. 确认 verifier 与 acceptance 无退化；
2. 确认证据来源、风险升级、副作用和归档完整性仍由 Harness 强制；
3. 比较调用分类与 cached/uncached 构成，而不是猜测减少原因；
4. 将未知原因和样本限制标为 `underpowered`；
5. 只有多任务证据满足 promotion 协议后，才把点估计提升为可推广结论。

## Evidence

- [`validation/codex-host-campaign-0.4-vs-0.5.md`](../../../validation/codex-host-campaign-0.4-vs-0.5.md)
- [`validation/control-plane-report.md`](../../../validation/control-plane-report.md)
- [`validation/meta-effect-report.md`](../../../validation/meta-effect-report.md)
- [`validation/release-manifest.json`](../../../validation/release-manifest.json)

