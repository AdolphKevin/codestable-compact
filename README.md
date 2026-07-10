# CodeStable Compact 0.4.0

> 一个入口、五条软件生命周期、按需上下文，以及可观测、可评估、由证据驱动进化的 Harness Meta 闭环。

CodeStable Compact 是一套面向**软件本身生命周期**的 Agent Skills。普通开发仍然只需要：

```text
/cs <真实开发诉求>
```

入口会恢复或自动路由到 feature、issue、refactor、roadmap、model，并在同一轮继续执行。设计审查、代码审查和 QA 是生命周期内部循环；只有真正需要授权的 Gate 才暂停。

0.4.0 在 0.3.0 的被动 Observation 与可信 Evaluator 基础上，把此前分散的反馈、策略、fixture、候选、评测、接受与回滚能力接成了显式 Meta 闭环：

```text
正常 /cs
  = 软件交付生命周期 + best-effort 临时轨迹

显式 /cs feedback
  = 生产反馈分诊 + 反馈转回归 fixture

显式 /cs meta
  = 已选择证据 + 离线 Harness 维护
```

**正常 `/cs` 不会读取历史轨迹，不会自动诊断，不会生成候选，不会跑 Harness 基准，也不会修改当前策略。**

## 0.4.0 的核心变化

### 策略成为一等公民

Harness 不再只是一组散落的 Prompt 和脚本。每项可调整策略都必须在：

```text
.codestable/meta/policy-registry.json
```

中声明：

- 策略 ID；
- 所在可编辑 surface；
- 允许的变更类型；
- routing / contract / e2e / regression fixture；
- 必需覆盖层；
- Agent 或 owner 的审批权限。

硬规则：

```text
No fixture coverage, no evolution.
无 fixture 覆盖，不允许进化。
```

仅仅出现在 `harness/manifest.json` 的 editable surface 里还不够；没有覆盖策略语义的 fixture，候选注册会被确定性拒绝。

当前注册了 9 个可进化策略：

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

审计命令与当前结果：

```bash
python3 .codestable/tools/cs_policy.py audit
```

```text
Policies: 9
Fixtures: 12
Coverage issues: 0
Result: PASS
```

### 生产反馈成为标准管道

每次 Skill 运行继续只写一份轻量飞行记录：

```text
.codestable/observations/<state>/<run-id>/
├── meta.json
├── events.jsonl
└── outcome.json
```

Schema v3 可以记录紧凑元数据：

```text
route / lane / stage
policy activation
context 与 knowledge 读取
knowledge 写入和 promotion
gate 通过/拒绝及 reason code
checkpoint 停顿
人工干预次数
token/tool/context 聚合值（宿主能提供时）
任务 verifier 结果
```

确认是生产问题后，显式运行 `cs_feedback.py triage`，将其分类为：

```text
harness_policy
evaluation_defect
model_profile_variance
project_knowledge
product_code
environment
insufficient_evidence
```

只有 `harness_policy` 会进入 Harness 维护；评测缺陷先修 fixture/scorer，项目知识问题更新 `.codestable/knowledge`，产品问题修代码。

### 创意归 Agent，测量归脚本

Meta 工具不会自动改 Prompt。它只负责：

```text
校验 → 锁定 → 测量 → 标注 → 记账 → 比较 → 执行权限规则
```

Agent 负责写：

- 已提交且冻结的 hypothesis；
- 人类可读 variant 文档；
- 提案 JSON；
- 最小 candidate overlay。

脚本作者不能伪装成提案 Agent；`authorship.kind=script` 会被拒绝。

### 效度预检先于负向结论

真实评测里，常见的“技能缺陷”其实来自：

```text
fixture 缺 onboarding 上下文
subject matter 引用不完整
oracle 对措辞过脆
scorer 未校准
随机任务样本太少
judge 与被测 profile 未隔离
hypothesis 在看到结果后被改写
```

0.4.0 把这些风险变成硬前置检查。任何声称提升或负向结论，都必须先通过：

```text
context completeness
required refs
structured/tolerant oracle
scorer calibration
stochastic k >= 5
judge/profile isolation
committed hypothesis provenance
```

Candidate 内容不可变由后续的评测 challenge、结果导入和晋升检查锁定，不属于效度预检本身。

每项数值证据必须标记：

| 标签 | 含义 | 可用于晋升 |
|---|---|---|
| `[measured]` | 直接执行的确定性检查，或足量重复的真实宿主测量 | 是 |
| `[soft]` | 有帮助但依赖专家/Judge 或弱 oracle 的证据 | 不能单独支持 |
| `[underpowered]` | 缺真实 adapter、样本不足、上下文不全或 scorer 未校准 | 否 |

### 自治触发只聚合信号

`cs_meta.py trigger-scan` 的默认阈值是 `minimum_matching_signals = 3`。它只把相同 signal/policy、adapter/model_profile 与 Harness identity 的反馈归为一组，并默认只预览。只有显式 `--apply` 时，才可以为达到阈值的分组创建预算受限的 campaign。

它绝不能自动：

```text
诊断
生成 hypothesis
生成 proposal
运行 evaluation
接受
晋升
```

这避免因为单次偶发或定时任务触发而修改生产 Harness。

### 策略级审批权限

权限不是“一律人工”或“一律自动”，而是由策略和变更类型决定：

```text
prompt copy / 已评测 playbook
  → 可以由 Agent 在全 measured 证据后批准

workflow routing / retrieval strategy / workflow policy / Gate threshold / artifact schema / runtime tool
  → 必须由 owner 批准
```

提案本身不能选择审批级别。

### 双向可追溯与回滚

每次接受的版本会关联：

```text
生产 feedback
policy 与 fixture
hypothesis commit/hash
proposal 与 variant
效度预检
trusted evaluation
quality gates
runtime profile
批准类型/批准者/理由
```

被否决的候选和测量结果保留索引，供维护者显式查重。回滚从不可变快照恢复，并记录 actor 与 reason。

## 为什么 Runtime Profile（运行时配置档案）是一等变量

CodeStable 的实际效果取决于：

```text
Harness policy
× 项目代码和 .codestable 状态
× 模型
× 宿主（Claude Code / Cursor / Codex / ChatGPT 等）
× Adapter / 工具权限 / 上下文预算
```

因此一个有效评测结论必须绑定精确 profile，例如：

```text
claude-code/<model>/<adapter-version>
codex/<model>/<toolset>
cursor/<model>/<workspace-mode>
```

生产反馈按相同 signal/policy、adapter/model_profile 与 Harness identity 分组；评测 challenge 另行锁定 model profile、adapter 和 budget。一个 profile 上通过的候选默认只产生该 scope 的证据，不会自动宣称跨模型、跨宿主普遍更好。

## Meta 闭环

```text
observe
→ feedback triage
→ fixture register
→ threshold group or explicit campaign
→ diagnose
→ hypothesis freeze
→ proposal register
→ 效度预检
→ trusted evaluation
→ decide
→ measured quality gates
→ acceptance check
→ policy-scoped promote / rollback
```

## 文档导航

- [架构总览](docs/architecture.md)
- [设计决策](docs/design-decisions.md)
- [使用示例](docs/examples.md)
- [灵感来源审查](docs/inspiration-review.md)
- [Meta 自迭代协议](docs/meta-loop.md)
- [从 CodeStable 迁移](docs/migration-from-codestable.md)
- [问题与方案映射](docs/problem-solution-map.md)
- [可观测 Harness 与 Meta 自迭代设计](docs/self-evolving-harness.md)
- [宿主与可信评测器契约](adapters/evolution-host-contract.md)

## 用户可见技能

| 技能 | 职责 |
|---|---|
| `cs` | 唯一日常入口；初始化、恢复、自动路由、观察、反馈和显式 Meta 维护 |
| `cs-feat` | 新能力完整生命周期 |
| `cs-issue` | 缺陷、回归、异常和性能退化修复 |
| `cs-refactor` | 行为保持的结构改善 |
| `cs-roadmap` | 跨 feature 的计划、契约与切分 |
| `cs-model` | vision、domain、requirement、contract、decision 和可复用知识 |

普通用户不需要记住后五个；`/cs` 会自动选择并继续。

## 功能开发流程合并

```text
cs-feat
  intake → evidence → design → implement → verify → accept → archive
```

设计审查、代码审查和 QA 保留为自动审查与修复循环，不再是用户要手动切换的技能。

## 按需上下文与历史隔离

每个 active work 只有三个必需文件：

```text
.codestable/work/active/<work-id>/
├── state.json
├── work.md
└── context.json
```

普通读取顺序：

```text
当前对话
→ 当前 work state
→ work.md 当前阶段
→ 显式链接的 model / knowledge
→ 当前相关代码和测试
→ 定向 current-state 搜索
```

默认不搜索：

```text
work/archive
observations
meta
evolution
evals
Harness version history
```

完成时只把仍然成立的事实提升到 `model/` 或 `knowledge/`，完整过程进入 archive。这样历史 feature 数量不会成为启动成本。

## 目录结构

```text
.codestable/
├── model/                 # 当前软件真相
├── knowledge/             # 经验证的项目工程知识
├── work/                  # active 与 archive 生命周期
├── observations/          # 正常运行的临时飞行记录
├── meta/                  # 显式 Meta campaign、策略清单与证据索引
├── evolution/             # 低层 candidate/version 状态
├── evals/                 # 公开 fixture 与受保护评测协议
├── harness/               # active policy、playbook、版本和 lineage
├── reference/             # 生命周期策略正文
└── tools/                 # Python 标准库确定性工具
```

## 常用命令

### 正常开发

```text
/cs 提交暂存操作很慢，帮我排查并修复
/cs 增加导出功能
/cs continue
/cs doctor
```

### 观察与反馈

```text
/cs observe status
/cs observe list gate.false_positive
/cs observe flag <run-id>
/cs feedback triage <run-id>
/cs feedback fixture <feedback-id> <fixture-file>
```

### 显式 Meta 维护

```text
/cs meta status
/cs meta policy-audit
/cs meta trigger-scan
/cs meta trigger-scan --apply
/cs meta diagnose <campaign>
/cs meta hypothesis-freeze <campaign>
/cs meta proposal-register <campaign>
/cs meta validity-prepass <campaign/candidate>
/cs meta evaluation-challenge <campaign/candidate>
/cs meta decide <campaign/candidate>
/cs meta quality-gate <campaign>
/cs meta acceptance-check <campaign/candidate>
/cs meta promote <campaign/candidate>
/cs meta rollback <version>
```

`/cs evolve ...` 是兼容别名，不维护第二套行为。

`/cs meta rollback <version>` 是交互简写；确定性 CLI 执行回滚时还必须提供 `--approved-by` 和 `--reason`。

## 初始化和升级

安装 `skills/` 到支持 Agent Skills 的宿主，然后在项目仓库执行：

```text
/cs init
```

未初始化时直接提交开发请求也可以；入口会初始化后在同一轮继续。

升级：

```text
/cs upgrade
```

Bootstrap 会备份被替换的 runtime 文件，保留项目 model、knowledge、work、observations、反馈和项目自定义 fixture，并将危险的旧自动进化配置迁移回显式手动模式。

## 验证范围

发布包自带三类验证：

1. **[measured] 控制面与契约**：单元测试、fixture/policy audit、正常路径隔离、提案权限、效度预检、签名评测锁、owner 审批、版本和回滚。
2. **[measured] 已知坏策略检测**：故意注入缺 fixture、脆弱 oracle、低 k、脚本提案、越权审批、结果篡改等 mutant，验证系统会拒绝。
3. **[underpowered] 跨宿主真实 LLM 效果**：便携包不包含 GPT、Claude Code、Cursor 或 Codex 的真实执行服务；没有实际 Host Adapter 数据时，相关 fixture 明确标为 underpowered，不计作效果提升。

因此本地报告能证明 Meta 闭环与防护机制真实工作；要证明某个候选在某个模型/宿主上更好，必须由对应 Adapter 执行 baseline/candidate，并导入外部签名的 aggregate result。

当前验证结论：

```text
CONTROL_PLANE_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED
```

| 验证项 | 结果 |
|---|---|
| 0.4.0 单元测试 | 54/54 通过 |
| 0.3.0 基线测试 | 33/33 通过 |
| 已知坏策略检测 | 13/13 通过 |
| 公开 fixture | 共 12 个；6 个 measured 通过、0 个失败、6 个 underpowered |
| 自动晋升资格 | `promotion_eligible = false` |

发布验证报告见 [Meta 效果验证报告](validation/meta-effect-report.md)。

## 开发验证

```bash
python3 scripts/validate_skills.py
python3 scripts/validate_meta_effect.py
python3 -m unittest discover -s tests -v
```

所有 Runtime 工具仅依赖 Python 标准库。
