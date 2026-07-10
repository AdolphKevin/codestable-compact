# CodeStable Compact 0.4 架构

## 1. 设计主旨

CodeStable 编排软件系统的生命周期，而不是一连串 Agent 角色。持久状态以文件形式保存在项目本地；模型与运行时可以替换。

0.4 将系统分为三个平面：

```text
交付平面    模型 + 知识 + 活跃工作 + 代码/测试
观察平面    临时、紧凑的生产轨迹
Meta 平面   反馈 + 策略 + fixture + campaign + 评测 + 版本
```

交付平面始终处于活动状态。正常工作期间只能写入观察平面。只有显式执行 `/cs feedback` 或 `/cs meta` 维护时，才会进入 Meta 平面。

## 2. 信息半衰期

| 层级 | 含义 | 生命周期 | 正常检索 |
|---|---|---:|---|
| `model/` | 当前软件事实和已接受的约束 | 长期 | 定向检索 |
| `knowledge/` | 可复用的项目工程知识 | 长期 | 定向检索 |
| `work/active/` | 当前变更状态 | 短期 | 仅指定工作项 |
| `source/tests/config` | 可执行证据 | 当前 | 按范围检索 |
| `work/archive/` | 历史过程 | 历史 | 默认关闭 |
| `observations/` | 临时生产飞行记录 | 临时 | 正常工作从不读取 |
| `meta/` | 反馈、策略、campaign 和证据索引 | 维护期 | 仅显式读取 |
| `evolution/` | candidate/版本控制状态 | 维护期 | 仅显式读取 |
| `evals/` | 公开 fixture 和受保护协议 | 评测期 | 仅显式读取 |

这种分层同时避免历史 feature 过载和 Meta 上下文污染。

## 3. 用户可见拓扑

```text
                        ┌───────────┐
真实请求 ─────────────▶ │    cs     │
                        └─────┬─────┘
                  优先恢复     │否则分类
        ┌──────────────┬──────┼──────┬──────────────┐
        ▼              ▼      ▼      ▼              ▼
     cs-feat        cs-issue cs-refactor cs-roadmap cs-model
        │              │      │      │              │
        └──────────────┴──────┴──────┴──────────────┘
                         立即继续
```

`/cs` 不是只显示路由建议的界面。生命周期技能仍可供专家直接调用和测试，但普通用户只需要 `/cs`。

## 4. 交付状态机

所有可执行工作都使用：

```text
created → active → blocked? → active → done → archived
                 └─ cancelled ────────────────▶ archived
```

各类型专属阶段：

```text
feature:  intake → evidence → design → implement → verify → accept
issue:    intake → reproduce → analyze → fix → verify → accept
refactor: intake → characterize → design → implement → verify → accept
roadmap:  discover → frame → contracts → decompose → review → activate
model:    inspect → edit → validate → index
```

每个活动工作项只有：

```text
state.json    确定性控制状态和显式链接
work.md       意图/证据/设计/变更/验证的聚合记录
context.json  当前实时会话的文件哈希读取收据
```

阶段从 `state.json` 读取，绝不通过 Glob 扫描旧阶段文档来推断。

## 5. 上下文规划器

正常上下文采用白名单：

```text
当前对话
当前活动 state/work
显式链接的 model/knowledge
当前相关的 code/tests/config
有边界的当前状态检索
```

默认排除：

```text
archive 正文
observations
feedback/meta campaign
evolution/evaluation 状态
Harness 版本历史
```

只有内容哈希未变化时，`context.json` 收据才允许在同一实时会话中复用。新的冷会话会使用新的会话键并重新读取必要材料；磁盘收据不会被当作模型记忆。

## 6. 内部审查与人类 Gate

设计审查、代码审查和 QA 都是生命周期中的自动循环。阶段结束本身不是 Gate。

只在以下情况暂停：

- 不可逆或破坏性操作；
- 确实需要选择公共契约；
- 安全或权限策略；
- 未经批准的持久化迁移；
- 实质性的成本或可用性风险；
- 无法解决的已接受决策冲突；
- 当前权限无法完成验收；
- 用户明确要求批准；
- 按策略确定的 Harness owner 审批。

Gate 必须给出证据、待决事项、建议、备选方案及其后果。

## 7. 被动观察平面

正常交付只启动一条 observation，并将其 `run_id` 传递给嵌套的生命周期技能。

Schema v3 事件可以表示：

```text
route_selected
stage_started / stage_finished
policy_applied
context_loaded / knowledge_read / knowledge_written
gate_evaluated
checkpoint_paused
human_intervention
token_usage
tool_failed / tool_retried
verification_finished
run_finished
```

记录器只保存紧凑的元数据和哈希，不保存原始 Prompt、模型回复、源码、Diff、secret、私有评测 fixture 或任务轨迹。记录失败不会阻塞交付。

正常交付从不读取旧 observation。signal 只会将 run 移至 `flagged`，不会触发反馈分诊或 Meta 优化。

## 8. 生产反馈平面

`cs_feedback.py` 将指定的已完成 observation 转换为分类后的反馈项。分类可以防止所有不良结果都被当作 Harness 变更：

| 原因 | 去向 |
|---|---|
| `harness_policy` | 固化 fixture，并可能进入 Meta campaign |
| `evaluation_defect` | 修复 fixture/oracle/scorer |
| `model_profile_variance` | 形成 profile 限定的证据，不晋升到 Core |
| `project_knowledge` | 更新项目 knowledge/model |
| `product_code` | 修复软件 |
| `environment` | 修复 runtime/tooling |
| `insufficient_evidence` | 保留证据，不生成 proposal |

已确认的生产偶发可以转换为回归 fixture。注册 fixture 时会记录 feedback/run 来源并校验 schema。

## 9. 一等 Harness 策略

两个注册表职责不同：

```text
harness/manifest.json
  → 实际可编辑 surface 和受保护路径

meta/policy-registry.json
  → 概念策略、允许的变更类型、fixture 覆盖和权限
```

只有同时满足以下条件，策略才可进化：

1. 状态已列入白名单；
2. surface 存在于 Harness manifest；
3. 请求的变更类型得到允许；
4. 所有声明的 fixture 均存在且处于活动状态；
5. 所有必需 fixture 层均已覆盖；
6. overlay 只修改声明的 surface 路径。

```text
无 fixture 覆盖，不允许进化。
```

`cs_policy.py`、proposal 注册和发布验证共同强制执行这条规则。

## 10. Meta campaign 状态机

```text
feedback evidence
→ diagnose
→ proposal
→ validity_passed | validity_blocked
→ evaluation
→ quality_gates | rejected
→ accepted_pending_agent | accepted_pending_owner
→ promoted | closed
```

Campaign 只聚合彼此兼容的证据：相同的 signal/policy、Adapter/Model Profile 和 baseline Harness identity。`trigger-scan` 以预览为先，只有达到配置的支持度后才会打开 campaign；它从不生成 proposal 或执行评测。

## 11. 提案归属

Agent 负责撰写：

- hypothesis 文档；
- variant 文档；
- 提案 JSON；
- 最小 overlay。

Hypothesis 必须在 candidate 结果出现前提交并冻结。Proposal schema 要求提供目标指标、policy ID、变更类型、fixture ID、预期效果、回归风险和 hypothesis 来源。

确定性工具只负责校验、锁定、测量、标注和记录。它们会拒绝脚本生成的 proposal、受保护路径、未声明文件、过期 commit 和预算违规。

## 12. 优化前先验证评测效度

分数不会自动成为 Harness 质量的证据。效度预检会先检查测量工具：

```text
fixture 上下文是否完整？
必需引用是否存在？
oracle 是否宽容且结构化？
scorer 是否已校准？
随机任务是否满足 k >= 5？
judge 是否与被测 profile 隔离？
hypothesis 是否已预先提交并冻结？
```

证据标签：

```text
measured      已直接执行或重复次数充足
soft          可供参考，但不能作为硬 Gate
underpowered  缺少 adapter/样本/校准/上下文
```

只有通过的 measured 证据才能满足晋升 Gate。

## 13. 可信 Evaluator 边界

评测 challenge 会冻结：

```text
baseline 版本/内容
candidate 定义/内容/overlay
policy 与 fixture 证据
效度结果
protocol
Runtime Profile
model_profile
adapter
evaluator
budget
必需的 held-in/held-out/safety 数据集
nonce
```

外部 Evaluator 持有私有 held-out 任务和签名凭据，在全新且等价的 sandbox 中运行，并且只返回签名后的聚合结果。导入过程会拒绝原始任务轨迹、篡改、重放、指标缺失和任何锁定内容漂移。完整的宿主、工具集和上下文身份需要 Host Adapter 编码到这些锁定字段中。

便携包可以在本地运行确定性公开 fixture。缺少真实 adapter 的 host/model fixture 会被标记为 underpowered；这不能用来声称 GPT、Claude Code、Cursor 或 Codex 得到了提升。

## 14. Runtime Profile 范围

Harness 结果取决于：

```text
policy × 项目状态 × .codestable 状态 × model × host × adapter × budget/toolset
```

反馈组绑定 Adapter/Model Profile 与 Harness identity；评测 challenge 还会锁定预算等身份。不同已记录身份的证据不会被静默合并。

证据可以支持的适用范围只能随验证扩大：

```text
项目 + profile
→ 同一 profile 的跨项目证据
→ 受支持 profile 范围内的可移植 Core
```

当前的便携式 Meta 引擎负责记录 profile 证据和权限；host adapter 提供真实的 model/runtime 执行。

## 15. 接受机制与策略级审批

接受机制按优先级逐项判断，而不是计算一个混合总分：

1. policy 覆盖和受保护路径契约；
2. 效度预检；
3. 可信的目标改善，以及 held-out/safety 不回归；
4. 必需的 measured 回归/package Gate；
5. 正确的策略限定权限；
6. 不可变版本快照和回滚路径。

权限由 policy/change type 声明：

- 低风险 Prompt 文案或经过评测的 playbook entry 可以允许 Agent 批准；
- workflow routing、retrieval strategy、workflow policy、Gate threshold、artifact schema 和 runtime tooling 需要 owner 批准。

提案者不能降低 checkpoint。

## 16. 来源链与回滚

晋升版本会关联：

```text
feedback → fixture → policy → hypothesis commit → proposal/variant
→ validity → evaluation → quality gates → approval → version
```

反向链接保存在策略证据和版本元数据中。被拒绝的 variant 仍保留在索引中。Rollback 会校验并恢复不可变快照，同时记录 actor/reason；它不会触发另一轮优化。

## 17. 发布验证模型

本软件包明确区分实际证明了什么：

- `[measured]`：确定性 runtime 测试、policy/fixture 审计、Meta 状态机、安全锁和异常变体拒绝。
- `[soft]`：已声明的 fixture/scorer 设计证据，不能单独作为充分证据。
- `[underpowered]`：在对应 adapter 执行 fixture 前，真实的多 model/host 效果均属于此类。

这可以防止发布测试被误当作通用的 LLM 性能基准。
