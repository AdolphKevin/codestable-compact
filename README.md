# CodeStable Compact 0.5.0

CodeStable Compact 是面向 Codex / 强 Agent 的软件生产控制平面。

它不要求 Agent 按需求、设计、实现、测试等固定阶段交接，而是允许 Agent 自主选择路径，并由 Harness 控制目标、事实、副作用、风险、证据和完成权：

```text
自由推理
受控执行
证据完成
持续学习
```

## 安装与初始化

先将本仓库 `skills/` 下的六个公开 Skill 安装到宿主的 Agent Skills 搜索目录，然后在目标 Git 工作树中使用 `cs`。本文统一写作 `/cs`；使用 `$skill` 语法的宿主请写 `$cs`。

首次使用可以显式初始化：

```text
/cs init
```

也可以直接提交开发请求；当项目还没有 `.codestable/config.json` 时，入口会先初始化，再在同一次调用中继续交付。

从源码安装项目内 Runtime 时使用：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project
```

升级已安装 Runtime：

```text
/cs upgrade
```

对应的源码命令是：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project --upgrade
```

升级会先备份被替换的工具和参考文件，并保留项目维护的 model、knowledge、work、observations、feedback 与 fixtures。Runtime 工具要求 Python 3.10+，完成门要求目标位于可写 Git 工作树中。

## 日常使用

正常开发只需要一个入口：

```text
/cs 修复提交暂存操作很慢的问题
/cs 增加订单导出功能
/cs 在行为不变的前提下拆分支付模块
/cs 规划多租户迁移路线
/cs 更新订单状态机的项目知识
```

`/cs` 会恢复已有任务或自动路由到 `cs-issue`、`cs-feat`、`cs-refactor`、`cs-roadmap`、`cs-model`，并在同一次调用中继续执行；用户不需要再手动调用被选中的 Skill。默认会持续推进到真实验证和 Harness 完成判定，只有授权、外部环境或明确的人类 Gate 才会暂停。

分析范围也直接写进请求：

```text
/cs 只分析这个回归的根因，不要修改文件
/cs 先给出可验证方案，本次不要实现
```

这类请求会收窄副作用边界，并在未尝试完整交付时如实返回 `PARTIAL`，不会伪装成已完成。

常用控制命令：

| 命令 | 用途 |
|---|---|
| `/cs continue [提示]` | 按缺失事实、风险和证据恢复匹配任务 |
| `/cs status` | 只查看活动任务的控制状态 |
| `/cs route <需求>` | 只诊断路由，不执行任务 |
| `/cs doctor` | 检查 schema、证据链完整性和策略边界 |
| `/cs archive <work>` | 归档已由 Harness 完成或已取消的任务 |

`cs-feat` 等结果 Skill 仍可直接调用，但主要用于需要显式指定任务类型的宿主集成；日常入口保持 `/cs`。

## 核心定位

```text
User intent
    ↓
Task contract
    ↓
Owner Agent ── Inspect / Propose / Execute / Verify / Learn（可重复、可重排）
    ↓
Tool plane ── repository / terminal / tests / runtime / browser
    ↓
Evidence ledger ── facts / assumptions / risks / changes / results
    ↓
Harness completion gate
    ↓
Independent Reviewer（按风险触发）
    ↓
Accept / Repair / Rollback / Learn
```

路径由 Owner 自主选择；允许的副作用、最低验证强度和最终完成资格由 Harness 决定。Reviewer 只负责反证，不模拟传统研发角色。

## 五个动作，不是五个阶段

- **Inspect**：建立真实入口、调用链、状态、schema、prompt、副作用、事实和未知。
- **Propose**：在需要时形成可证伪的最小变化，明确不改变什么以及如何证明。
- **Execute**：Agent 自主实现；Harness 只限制允许写入、授权和回滚边界。
- **Verify**：执行真实命令或接收带指纹的外部 artifact，保留 `PASS / FAIL / BLOCKED / PARTIAL`。
- **Learn**：只把真实重复失败沉淀为 fixture、rule、invariant、checker 或 failure signature。

动作可以反复调用。下一步由缺失事实、开放风险和缺失证据驱动，而不是由“当前阶段”驱动。

## 风险自适应完成策略

| Level | 典型任务 | 最低证据 |
|---|---|---|
| L0 Trivial | 文案、格式、无行为重排 | `diff_check`, `format_check` |
| L1 Local | 局部函数、单模块 bug | `scope_inspect`, `targeted_test`, `lightweight_review` |
| L2 Cross-module | 多模块、schema/prompt/state、并发/持久化边界 | `audit_ledger`, `proposal`, `integration_test`, `independent_review`, `proof` |
| L3 Critical | 安全、资金、删除、权限、迁移、核心状态机 | `full_audit`, `invariant_contract`, `live_validation`, `rollback_proof`, `independent_review`, `regression_fixture` |

风险只能上升。登记跨模块或关键执行路径的真实变更时，Harness 会自动升级要求。

## Task State

每个活动任务位于 `.codestable/work/active/<task-id>/`：

```text
state.json       目标、风险、边界、事实账本、完成资格
work.md          面向 Owner 的紧凑工作面
context.json     本次会话读取计划与哈希 receipt
evidence.jsonl   带哈希链的不可变证据账本
```

核心状态结构：

```yaml
goal:
proposal:
risk:
side_effects:
ledger:
  facts:
  assumptions:
  risks:
  changes:
blockers:
evidence:
completion:
```

Agent 可以解释证据，但不能自己制造“命令已执行”“测试已通过”或“独立 reviewer 已通过”。`verify` 由 Harness 实际运行命令并记录 command、cwd、exit code、duration、输出摘要和 artifact 指纹。

## Harness CLI（高级用法）

正常用户无需手工编排以下命令；`/cs` 会代为维护任务合同、账本和证据。下面的 L2 示例主要供 Host Adapter、控制平面开发和故障诊断使用，命令顺序只是一次证据收敛路径，不是固定流程。

创建任务：

```bash
python3 .codestable/tools/cs_context.py new feature \
  "limit concurrent AI turns" \
  --risk 2 \
  --allow-path 'src/**' \
  --allow-path 'tests/**'
```

建立合同和边界：

```bash
python3 .codestable/tools/cs_context.py contract \
  --work limit-concurrent-ai-turns \
  --objective 'Bound concurrently running complete AI turns' \
  --acceptance 'Configured cap is never exceeded' \
  --acceptance 'Cancellation releases the slot' \
  --invariant 'A single conversation remains serial' \
  --non-goal 'No general scheduler'

python3 .codestable/tools/cs_context.py boundary \
  --work limit-concurrent-ai-turns \
  --allow-path 'src/**' \
  --allow-path 'tests/**'
```

记录事实、提案和真实变更：

```bash
python3 .codestable/tools/cs_context.py ledger-add \
  --work limit-concurrent-ai-turns fact \
  'run_customer_turn is entered after the conversation lock' \
  --source src/handler.py

python3 .codestable/tools/cs_context.py proposal \
  --work limit-concurrent-ai-turns \
  --summary 'Acquire one global turn slot around the full turn execution' \
  --rationale 'The slot must cover all expensive turn work and release in finally' \
  --non-change 'Per-conversation serialization remains unchanged' \
  --evidence-required 'cap, cancellation and multi-conversation tests'

python3 .codestable/tools/cs_context.py ledger-add \
  --work limit-concurrent-ai-turns change \
  'Bound complete turn concurrency' \
  --path src/turn_runtime.py
```

采集证据并检查完成资格：

```bash
python3 .codestable/tools/cs_context.py snapshot \
  --work limit-concurrent-ai-turns --type audit_ledger

python3 .codestable/tools/cs_context.py snapshot \
  --work limit-concurrent-ai-turns --type proposal

python3 .codestable/tools/cs_context.py verify \
  --work limit-concurrent-ai-turns \
  --type integration_test -- \
  python3 -m unittest tests.test_turn_limits

# review.md 必须已由不同于 Owner 的 reviewer 生成。
python3 .codestable/tools/cs_context.py record \
  --work limit-concurrent-ai-turns \
  --type independent_review \
  --status PASS \
  --producer reviewer-1 \
  --artifact review.md \
  --verdict PASS

python3 .codestable/tools/cs_context.py proof --work limit-concurrent-ai-turns
python3 .codestable/tools/cs_context.py check --work limit-concurrent-ai-turns
python3 .codestable/tools/cs_context.py complete --work limit-concurrent-ai-turns --result done
python3 .codestable/tools/cs_context.py archive \
  --work limit-concurrent-ai-turns \
  --summary 'Concurrency is bounded with integration and independent-review evidence'
```

缺少来源匹配的证据、证据链损坏、开放 blocker、高风险未关闭、Owner 自签 reviewer，或未注册/越界的 Git 可见写入都会阻止 `done`。Reviewer producer 在便携运行时中是声明式身份；密码学身份保证需要 Host Adapter attestation。

## 六个公开 Skill

| Skill | 首个可独立验证结果 |
|---|---|
| `cs` | 初始化、路由、控制状态、证据完成与显式 Meta 入口 |
| `cs-feat` | 新的可观察能力 |
| `cs-issue` | 错误、回归或性能信号被关闭 |
| `cs-refactor` | 行为保持且结构属性改善 |
| `cs-roadmap` | 多任务合同与依赖可执行化 |
| `cs-model` | 有真实消费者的当前共享真相 |

不暴露 Requirement Agent、Architecture Agent、Developer Agent、Test Agent 等角色技能，也不暴露内部阶段技能。

## 正常生产与 Meta 维护隔离

正常 `/cs` 只做 Owner 执行、Harness 证据门和 best-effort 被动 observation 写入。它不会读取 observation 历史、反馈、候选、私有评测、拒绝方案或 Harness 版本历史。

显式 `/cs meta ...` 才能进入选择证据、诊断策略、生成候选、历史 fixture replay、独立评测、接受/回滚的外循环。硬规则仍然是：

```text
No fixture coverage, no evolution.
```

常用显式入口：

```text
/cs observe status
/cs feedback triage <run-id>
/cs meta status
/cs meta policy-audit
/cs meta trigger-scan
```

`trigger-scan` 默认只预览；`/cs evolve ...` 只是 `/cs meta ...` 的兼容别名。正常 `/cs` 不会因为 observation 或反馈信号自动进入 Meta。

## 文档

- [架构总览](docs/architecture.md)
- [设计决策](docs/design-decisions.md)
- [使用示例](docs/examples.md)
- [问题与方案映射](docs/problem-solution-map.md)
- [从旧版 CodeStable / Compact 迁移](docs/migration-from-codestable.md)
- [Meta 闭环](docs/meta-loop.md)
- [可自演进 Harness](docs/self-evolving-harness.md)
- [宿主与可信评测器契约](adapters/evolution-host-contract.md)
- [灵感来源审查](docs/inspiration-review.md)
- [验证报告与复现说明](validation/README.md)

## 发布验证

```bash
python3 scripts/validate_skills.py
python3 scripts/validate_control_plane.py
python3 scripts/validate_meta_effect.py
python3 -m unittest discover -s tests -v
```

`validate_control_plane.py` 会运行隔离的 L0/L2/L3 场景，验证真实命令证据、动态风险升级、独立 reviewer、proof、完成拒绝、归档和证据篡改检测，并生成机器可读报告。
