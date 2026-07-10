# Observable Harness 与按需自进化设计

## 1. 目标

CodeStable 0.3.0 的目标不是让每次 `/cs` 都尝试“反思并修改自己”，而是建立两条严格隔离的路径：

```text
日常软件交付：始终可观测，但不自进化
Harness 维护：只有明确选中问题证据后才进化
```

核心表述：

> **Always observable, selectively evolvable。始终可观测，按需才进化。**

这解决两个同时存在的需求：

1. 真正出现 Harness 问题时，有足够证据可以复现、诊断和评测；
2. 正常开发不承担历史扫描、额外模型调用、候选生成、基准评测或规则漂移成本。

## 2. 为什么不能每次都自进化

把以下外环附加到每次任务：

```text
任务完成 → 反思 → 提案 → 回归 → 修改 Harness
```

会造成：

- 正常工作延迟和 token 成本增加；
- 单次偶发失误被错误固化；
- Harness 持续漂移，难以定位回归；
- 任务上下文被历史轨迹和元讨论污染；
- Agent 同时做选手、出题人和裁判；
- Skill 本身越来越大，重新制造启动负担。

因此 0.3.0 明确禁止：

```text
自动弱点挖掘
自动诊断
自动提案
自动评测
自动晋升
基于任务数量或失败数量的阈值触发
```

## 3. 三阶段模型

```text
Observe       正常运行只写临时证据
Select/Diagnose  用户明确发现问题后选择并判断
Evolve/Evaluate  仅对确认的 Harness 问题生成候选与验证
```

### 观察（Observe）

普通 `/cs` 仍按原生命周期工作，旁路调用确定性 recorder。它没有额外模型回合，也不读取其他 run。

### 选择与诊断（Select/Diagnose）

用户、维护者或当前会话明确指出某个运行方式有问题，先把相关 run 标记/选择，再判断根因属于 Harness、项目知识、产品代码、模型波动、环境或证据不足。

### 进化与评测（Evolve/Evaluate）

只有 Harness 分类才能创建候选。候选必须在隔离环境中与 baseline 对照，并通过独立签名 Evaluator。通过后仍需人工 Gate 才能影响未来任务。

## 4. 被动 Observation

每次 Skill invocation 产生：

```text
.codestable/observations/pending/<run-id>/
├── meta.json
├── events.jsonl
└── outcome.json
```

### `meta.json`

示例：

```json
{
  "schema_version": 2,
  "run_id": "run-20260710-143012-a83f",
  "state": "pending",
  "status": "finished",
  "work_id": "2026-07-10-slow-stage",
  "task_id": "slow-stage",
  "kind": "issue",
  "lane": "standard",
  "entry": "cs",
  "route": "cs-issue",
  "start_stage": "intake",
  "end_stage": "accept",
  "harness": {
    "version": "h-0003",
    "manifest_sha256": "..."
  },
  "environment": {
    "repository_commit": "...",
    "model_profile": "host:model-version",
    "adapter": "host-adapter"
  },
  "event_count": 8,
  "signals": []
}
```

### `events.jsonl`

只保存有诊断价值的元数据事件：

```json
{"seq":1,"type":"route_selected","payload":{"route":"cs-issue"}}
{"seq":2,"type":"stage_started","payload":{"stage":"analyze"}}
{"seq":3,"type":"tool_failed","payload":{"tool":"shell","signature":"git-status-timeout","attempt":1}}
{"seq":4,"type":"tool_retried","payload":{"signature":"git-status-timeout","attempt":2}}
{"seq":5,"type":"verification_finished","payload":{"verifier":"pytest","status":"passed"}}
```

### `outcome.json`

```json
{
  "schema_version": 2,
  "run_id": "run-...",
  "status": "completed",
  "task_validation": {
    "status": "passed",
    "verifier_id": "project-tests",
    "command": "pytest -q",
    "exit_code": 0,
    "evidence": [],
    "issued_by": "task-runner"
  },
  "signals": [],
  "metrics": {
    "tool_calls": 12,
    "context_bytes": 42000
  },
  "selected_for_evolution": false
}
```

## 5. Observation 的边界和成本

默认约束：

```text
单 run 最大 256 KB
最多 500 个事件
单事件 payload 最大 8 KB
字符串最大 2048 字符
pending 保留 30 天
flagged 保留 180 天
pending 最多 200 个
```

明确禁止记录：

- Prompt、messages、完整模型回答；
- 源文件正文、diff、patch；
- Secret、credential、环境变量；
- private held-out、逐任务 evaluator trace；
- 任意用于重建完整私密会话的内容。

Recorder 失败遵循 best-effort：

```text
软件任务继续
不额外询问用户
不退化为完整日志
必要时在最终结果中做简短维护提示
```

普通 `/cs` 不能读取 `observations/`。确定性 prune 或写索引不等于把历史装入模型上下文。

## 6. Observation 状态

```text
pending   普通临时运行记忆
flagged   带明确问题信号，尚未诊断
selected  已被显式加入 evolution case
```

`flagged` 不是“已证明需要改 Skill”。例如用户纠正 route 时可以写：

```text
routing.user_corrected
```

但原因可能是：

- 用户表达模糊；
- 项目知识缺失；
- route 规则确实有问题；
- 一次模型随机波动。

因此 flag 只用于以后选择，不触发任何外环。

## 7. 显式 Case 选择

命名选择：

```bash
python3 .codestable/tools/cs_evolve.py case-new \
  --title "repeated identical tool retry" \
  --run run-101 --run run-118
```

或在用户明确请求后按 signal 选择：

```bash
python3 .codestable/tools/cs_evolve.py case-new \
  --title "routing correction pattern" \
  --signal routing.user_corrected --signal-limit 20
```

机械约束：

- 只接受 finished observation；
- 选中的 run 必须使用同一 baseline Harness version；
- 生成压缩 `evidence.json`；
- 不复制完整 events 到 case；
- 不扫描未选中的历史；
- 不自动创建 diagnosis 或 candidate。

## 8. 先诊断，再提出候选

分类：

| Classification | 后续 |
|---|---|
| `harness` | 映射到 declared surface 后可提案 |
| `project_knowledge` | 更新 model/knowledge，关闭 case |
| `product_code` | 创建/继续 issue/refactor，关闭 case |
| `model_variance` | 保留证据或增加 repeats，不改 Harness |
| `environment` | 修复 adapter/tool/sandbox，不改 Harness |
| `insufficient_evidence` | 等待更多显式证据，不改 Harness |

Harness diagnosis 必须声明：

```text
可复用机制
对应 editable surface
证据摘要
置信度
预期可观察行为
```

“这次回答不好”不是可接受机制。

## 9. 不可变内核与可修改表面

可修改面：

```text
routing-policy
retrieval-policy
minimality-policy
learned-playbook
lifecycle-policy
artifact-schema
context-tool
```

受保护面：

```text
config
Gate policy
observation/evolution/evaluator tools
evaluation protocol
observations and case evidence
manifest and registry
version snapshots
private held-out and signing key
sandbox/network/resource policy
```

候选 overlay 必须精确包含声明的 surface 路径，不能夹带额外文件。提案冻结每个文件的 base 与 candidate SHA-256。

所有 surface 都要求人工 promotion Gate。风险等级决定审查深度，不决定是否可以自动晋升。

## 10. 可信评测器

### 评测挑战（Challenge）

`cs_eval.py challenge` 生成不可变请求：

```json
{
  "challenge_id": "eval-...",
  "nonce": "random-256-bit-value",
  "baseline_version": "h-0003",
  "baseline_content_sha256": "...",
  "candidate_content_sha256": "...",
  "candidate_definition_sha256": "...",
  "protocol_sha256": "...",
  "locks": {
    "model_profile": "...",
    "adapter": "...",
    "evaluator": "...",
    "budget": "..."
  },
  "required_splits": ["held_in", "held_out", "safety"],
  "repeats": 3
}
```

### 隔离执行

Adapter 必须保证：

```text
baseline/candidate 使用同一模型与预算
fresh sandbox/worktree/container
candidate 看不到 private held-out
worker/proposer 看不到 evaluator signing key
Evaluator 实现和评分规则不可被候选修改
```

### 签名聚合结果

项目只接收：

```json
{
  "challenge": {"id":"...","sha256":"...","nonce":"..."},
  "case_id": "...",
  "candidate_id": "...",
  "baseline_version": "h-0003",
  "baseline_content_sha256": "...",
  "candidate_content_sha256": "...",
  "candidate_definition_sha256": "...",
  "protocol_sha256": "...",
  "locks": {"...":"..."},
  "splits": {
    "held_in": {
      "baseline": {"pass_count":6,"total":10,"metrics":{}},
      "candidate": {"pass_count":8,"total":10,"metrics":{}}
    },
    "held_out": {"baseline":{},"candidate":{}},
    "safety": {"baseline":{},"candidate":{}}
  },
  "signature": {
    "algorithm": "hmac-sha256",
    "key_id": "evaluator-prod-1",
    "value": "..."
  }
}
```

HMAC 不是为了让候选拥有签名能力，而是让外部 evaluator 边界证明“这个结果不是候选在项目目录里伪造的”。Key 必须只存在于 evaluator/import 进程环境。

导入拒绝：

- 缺签名或签名错误；
- nonce/challenge replay；
- baseline version/content、candidate content/definition、protocol/lock 不匹配；
- 缺少或额外 split；
- pass count 越界；
- 原始 task、trace、Prompt、source、diff 字段；
- 第二次导入；
- 导入后文件被修改。

## 11. 确定性决策

规则：

```text
accept =
  至少一个 required split 改善
  AND held_in 不回归
  AND held_out 不回归
  AND safety 全过
  AND 成本/时延/中断/上下文不超过阈值
  AND verified result 完整
```

通过状态仍然是：

```text
accepted_pending_human_gate
```

## 12. 提升 Gate

Gate 必须展示：

- 哪些 observation 被选中；
- diagnosis 与置信度；
- 具体 surface/diff/hash；
- held-in/held-out/safety 对照；
- 成本和中断指标；
- 风险、备选方案和回滚 target；
- 推荐是否提升。

显式批准后：

```bash
python3 .codestable/tools/cs_evolve.py promote \
  --case <case> --candidate <candidate> \
  --human-approved --approved-by "maintainer" \
  --reason "why"
```

Promotion 会再次验证：

```text
baseline 仍是 active
baseline content 与每个 base hash 未变化
candidate overlay/content/definition 未变化
challenge 与 verified evaluation 未变化
human actor/reason 存在
```

然后原子应用并创建不可变版本快照。

## 13. 回滚

```bash
python3 .codestable/tools/cs_evolve.py rollback \
  --version h-0003 --approved-by "maintainer" \
  --reason "new observations show Gate regression"
```

Rollback 只切换到已验证快照并记录 lineage。它不会自动开始新一轮优化。

## 14. 正常 Task Verifier 与 Harness Evaluator 的区别

### 任务验证器

正常 Feature/Issue/Refactor 本来就需要：

```text
unit/integration tests
lint/typecheck
build
acceptance script
manual observable check
```

它回答：

> 当前代码改动是否完成当前任务？

Task Verifier 结果顺便进入 observation，不代表 Harness 评测。

### Harness 评测器

仅在显式进化阶段运行：

> Candidate Harness 是否比 baseline 更好且不回归？

它需要 baseline/candidate、固定模型、固定预算、隔离环境、held-in/held-out/safety 和签名结果。

## 15. 命令总览

### 日常 active Harness 与 Observation

```bash
cs_harness.py identity
cs_harness.py playbook-query ...
cs_observe.py start ...
cs_observe.py event ...
cs_observe.py end ...
cs_observe.py flag ...
cs_observe.py list ...
cs_observe.py prune [--apply]
```

### 显式进化维护

```bash
cs_evolve.py case-new ...
cs_evolve.py case-show ...
cs_evolve.py diagnose ...
cs_evolve.py candidate-add ...
cs_eval.py challenge ...
cs_eval.py sign ...       # evaluator-only process
cs_eval.py import ...
cs_evolve.py decide ...
cs_evolve.py promote ...  # human Gate
cs_evolve.py rollback ...
```

不存在：

```text
run-start/run-end in evolution tool
automatic campaign scheduler
auto-diagnose
auto-propose
direct unsigned eval-record
auto-promote
```

## 16. 成熟度与诚实边界

0.3.0 已提供：

- 被动 observation 实现；
- 显式 evidence selection；
- 受限 candidate overlay；
- immutable challenge、baseline content、candidate content/definition 与签名结果验证；
- 非退化 decision；
- 人工 promotion Gate；
- 版本快照与 rollback；
- 宿主隔离合同和测试。

真正的“可信”仍依赖宿主做到：

- candidate 与 evaluator 隔离；
- private held-out 不挂载到 worker/proposer；
- HMAC key 不进入 worker/candidate 环境；
- baseline/candidate 使用相同运行条件。

项目内工具无法证明宿主没有把 key 泄露给候选；它能做的是让协议、锁、签名、hash、结果和提升链路可验证、可审计、可拒绝。
