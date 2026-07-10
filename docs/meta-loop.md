# Meta 自迭代协议

## 1. 目的

Meta 能力把一次已经手工验证过的工程流程产品化：

```text
生产偶发
→ 分诊
→ 固化回归 fixture
→ 提出最小策略变体
→ 先验证评测效度
→ baseline/candidate 对照
→ 接受或拒绝
→ 可回滚版本
```

它不是一个每次 `/cs` 自动运行的“反思 Agent”。正常交付只记录证据；Meta 是显式、离线、预算受限的维护流程。

## 2. M1：轨迹与反馈

### 正常轨迹

运行开始时记录 Harness identity、`model_profile`、`adapter`、repository commit、route、lane 和 stage。运行中只追加紧凑事件，结束时写 verifier 与宿主可提供的聚合成本。

必要事件：

```text
stage start/finish
gate result/reason
checkpoint pause
human intervention
token/tool/context aggregates
policy activation
knowledge read/write
verification outcome
```

轨迹不保存原始 Prompt、源码、Diff 或私有评测数据。

### 生产分诊

```bash
python3 .codestable/tools/cs_feedback.py triage \
  --run <run-id> \
  --classification harness_policy \
  --signal <signal> \
  --summary "<summary>" \
  --policy <policy-id> \
  --actor <actor>
```

必须先回答：这是策略缺陷、评测缺陷、模型/宿主差异、项目知识问题、产品代码、环境，还是证据不足？

### 反馈转为 fixture

Agent 根据真实事件构造最小、脱敏、可重复的 fixture，并注册其生产 provenance：

```bash
python3 .codestable/tools/cs_feedback.py fixture-register \
  --feedback <feedback-id> --file <fixture.json> --actor <actor>
```

单条偶发可以止于这里，不必开 campaign。

## 3. M2：可进化面盘点

运行：

```bash
python3 .codestable/tools/cs_policy.py audit
```

审计输出显示每个 policy 的 surface、fixture、覆盖层、允许变更和权限。缺失任何一项时，该 policy 不可进化。

首版策略包括：

```text
entry.routing-and-continuation
context.selective-loading
implementation.minimality-ladder
memory.promoted-playbook
lifecycle.stage-transitions
gate.risk-thresholds
artifacts.active-work-schema
runtime.context-tool
interaction.route-summary-copy
```

策略 ID 是长期概念，surface path 是当前实现。二者分离使未来文件重构不必改变评测语义。

## 4. M3：Meta Campaign

### 攒信号

```bash
python3 .codestable/tools/cs_meta.py trigger-scan
```

默认只输出类似提案的分组摘要，不改变状态。分组键包含：

```text
signal
policy
Adapter/Model Profile
baseline Harness identity
```

显式 `--apply` 最多按预算打开少量 campaign；不会继续执行后续步骤。

### 诊断

```bash
python3 .codestable/tools/cs_meta.py diagnose ...
```

只有 `harness` 诊断才能继续。若发现 fixture/oracle 缺陷，先修评测，不允许把错误量尺上的分数当成策略证据。

### 冻结 hypothesis

Agent 编写文档并提交到 Git，然后 `hypothesis-freeze` 锁定内容哈希和 commit。Hypothesis 必须在评测结果之前声明：

```text
目标机制
目标指标及标签
影响 policy/change type
fixture 集
预期改善
回归风险
falsification 条件
runtime profile scope
```

### Agent 提案

Agent 写 proposal/variant/overlay，脚本只做准入校验。一个提案应只处理一个机制，最多修改声明的少量文件，不能顺手重写整个 Skill。

## 5. 效度铁律

`validity-prepass` 是负向结论和声称提升的共同前置条件。

| 风险 | 检查 |
|---|---|
| 缺少引导上下文 | `context.complete` 与必需引用 |
| 缺领域材料 | `subject_matter_refs` |
| scorer 关键词过拟合 | 校准证据与变异用例 |
| oracle 太脆 | 结构化断言与容差 |
| 随机方差 | stochastic `k>=5` |
| Judge 泄漏或同源偏差 | Judge 与被测 Profile 隔离 |
| 事后改 hypothesis | Git commit + hash lock |

效度预检输出 `measured`、`soft`、`underpowered`。未达到 measured 通过时不能创建可信 challenge。

Candidate 定义和内容锁由后续的 challenge 创建、结果导入与晋升检查执行。

## 6. 评测

### 本地公开 fixture

```bash
python3 .codestable/tools/cs_fixture.py run --all
```

确定性 contract/runtime fixture 可以在包内真实执行。需要真实模型或宿主的 routing/e2e fixture，如果没有 Adapter，会返回 `underpowered` 而不是“通过”。

### 外部可信评测

`evaluation-challenge` 锁定 baseline/candidate、policy/fixture、效度结果、Runtime Profile、Adapter、预算和协议。外部 Evaluator：

1. 在全新且等价的沙箱中运行 baseline/candidate；
2. 持有私有 held-out 任务和签名密钥；
3. 不把私有任务挂载给候选；
4. 只返回聚合结果；
5. 通过 `cs_eval.py import` 导入。

### 不在线 A/B

生产任务只提供 feedback 和回归来源。候选不在真实用户任务上随机分流。所有候选评测都离线运行，晋升后再通过普通 observation 做 canary 观察。

## 7. 接受

`decide` 先检查签名评测中的目标提升、held-out/safety 不回归和必需指标。之后必须记录：

```text
policy_audit
validity_prepass
regression
package
```

四个 measured 质量门槛。

`acceptance-check` 再读取策略注册表决定检查点：

| 变更 | 权限 |
|---|---|
| Prompt 文案 | measured 证据通过后由 Agent 批准（若 policy 声明） |
| 已评测的 playbook 条目 | measured 证据通过后由 Agent 批准 |
| 工作流路由 | Owner |
| 检索策略 | Owner |
| 工作流策略 | Owner |
| Gate 阈值 | Owner |
| 生命周期策略 | Owner |
| 产物 schema | Owner |
| 运行时工具 | Owner |

## 8. 回滚与否决记忆

晋升生成不可变版本快照和 lineage。回滚校验快照后恢复。

被拒绝的提案、效度结果、评测和理由仍保留，供维护者在注册后续提案前显式查重。Meta 记忆不会进入正常任务上下文。

## 9. M4：自治触发边界

可由 cron 调用的仅是：

```text
retention prune
feedback queue summary
trigger-scan preview
trigger-scan --apply（仅开 campaign，受预算限制）
```

Cron 不拥有：

```text
Agent 提案权限
Evaluator 密钥
owner 批准
晋升权限
```

任何失败都不得阻塞正常 `/cs`。

## 10. 如何判断“真实效果”

一份发布报告必须区分：

### 已实测

```text
控制面状态机是否完整
无 fixture 是否被拦截
脚本提案是否被拦截
效度缺陷是否被发现
低 k 是否 underpowered
越权审批是否被拒绝
评测篡改/重放是否被拒绝
版本/回滚是否可靠
正常 /cs 是否仍隔离 Meta
```

### 尚未充分实测

```text
GPT 5.5 vs GPT 5.6
Claude Code vs Cursor vs Codex
不同宿主的 token / checkpoint / Gate 行为
某个候选在真实项目上的交付提升
```

后者只有在对应 Host Adapter 真实运行同一 Runtime Profile 的 baseline/candidate 后，才能从 underpowered 升级为 measured。不能用本地单元测试代替。
