# CodeStable Compact

> 一个入口、五条软件生命周期、按需上下文，以及“始终可观测、按需才进化”的 Harness。

CodeStable Compact 是一套面向**软件本身生命周期**的 Agent Skills。用户日常只需要：

```text
/cs <真实开发诉求>
```

入口会恢复或自动路由到 feature、issue、refactor、roadmap、model，并在同一轮继续执行；设计审查、代码审查、QA 都是生命周期内部循环，只有真正需要工程授权的 Gate 才暂停。

CodeStable Compact 同时提供 Observable Harness 与可信 Evaluator 边界：

```text
正常 /cs：执行软件任务 + 被动写一份临时 observation
显式 /cs evolve：选择问题证据 + 诊断 + 候选 + 可信评测 + 人工提升 Gate
```

**正常工作不会自动诊断、自动反思、自动生成候选、自动跑 Harness 基准或自动修改 Skill。**

## 核心原则

### Always observable, selectively evolvable

```text
始终可观测，按需才进化。
```

每次 Skill 执行只留下低成本、结构化、临时的“飞行记录器”文件：

```text
.codestable/observations/pending/<run-id>/
├── meta.json
├── events.jsonl
└── outcome.json
```

它只记录：

- 使用的 Harness 版本、route、lane、stage；
- 少量阶段、工具失败/重试、Gate、用户纠正事件；
- 正常任务 Verifier 的结构化结果；
- 可选问题信号和聚合指标。

它默认不记录：

- 原始 Prompt 与完整模型回复；
- 源文件正文、diff、patch；
- 凭据、Secret、环境变量；
- 私有 held-out 任务；
- 完整工具 stdout/stderr 与逐任务 Evaluator 轨迹。

普通 `/cs` 不读取这些记录，也不做额外模型调用。它只可通过只读 `cs_harness.py` 查询少量已经评测并提升的 active playbook 规则；不会借道 evolution 控制面。Recorder 写入失败默认不阻塞软件交付。

## 用户可见技能

| Skill | 职责 |
|---|---|
| `cs` | 唯一日常入口；初始化、恢复、自动路由、继续执行、观察和显式 Harness 维护命令 |
| `cs-feat` | 新能力的完整交付生命周期 |
| `cs-issue` | 缺陷、回归、异常和性能退化的完整修复生命周期 |
| `cs-refactor` | 行为保持的结构改善与技术债治理 |
| `cs-roadmap` | 跨 feature 的计划、契约、依赖与切分 |
| `cs-model` | 维护 vision、domain、requirement、contract、decision 和可复用知识 |

普通用户不需要记住后五个。`/cs` 会自动选择并直接开始。

## Feature 流程

```text
cs-feat
  intake → evidence → design → implement → verify → accept → archive
```

设计审查、代码审查和 QA 保留为自动修复循环，不再制造用户心智负担。

## 按需上下文

每个 active work 只有三个核心文件：

```text
.codestable/work/active/<work-id>/
├── state.json
├── work.md
└── context.json
```

读取顺序：

```text
当前对话
→ state.json
→ work.md 当前阶段小节
→ attention.md（仅变化时）
→ state 显式链接的 model/knowledge（仅变化时）
→ 相关代码、测试和配置
```

不再在每个阶段 Glob 全部 requirements、ADR、compound 或历史 features。同一实时会话通过 SHA-256 receipt 复用未变化内容；新的冷会话会重新读取必要材料。

## 当前真相、复用知识与历史分层

```text
.codestable/
├── model/               # 软件现在是什么，哪些约束仍有效
├── knowledge/           # 经验证、跨任务可复用的工程知识
├── work/active/         # 当前任务
└── work/archive/        # 历史执行过程
```

默认全文检索只使用 `model + knowledge`。历史 archive 只有在回归追踪、历史冲突或用户明确要求时，先查轻量索引，再显式 deep search。

## Observation 生命周期

```text
pending  → 普通临时记录
flagged  → 存在明确问题信号，但尚未诊断
selected → 用户显式选入某个 evolution case
expired  → 由 retention 清理，不进入长期知识
```

目录：

```text
.codestable/observations/
├── pending/
├── flagged/
├── selected/
└── index.jsonl
```

问题信号只是索引，不是自动诊断，例如：

```text
routing.user_corrected
tool.repeat_failure
gate.false_positive
context.constraint_missed
verification.false_pass
entry.extra_turn
```

查看和标记必须显式执行：

```bash
python3 .codestable/tools/cs_observe.py status
python3 .codestable/tools/cs_observe.py list --state flagged
python3 .codestable/tools/cs_observe.py flag \
  --run <run-id> --signal tool.repeat_failure
python3 .codestable/tools/cs_observe.py prune       # 仅预览
python3 .codestable/tools/cs_observe.py prune --apply
```

## 自进化只在显式维护模式运行

安装 Skill 并在目标代码库执行 `/cs init` 后，可以直接使用：

```text
/cs observe status
/cs observe list
/cs observe flag <run-id>
/cs evolve inspect flagged
/cs evolve select <run-id>
/cs evolve diagnose <case-id>
/cs evolve propose <case-id>
```

这些命令会操作当前项目的 `.codestable/`，不会修改宿主中全局安装的 Skill。

完整外环：

```text
Select
→ Diagnose
→ Propose
→ Trusted Evaluate
→ Deterministic Decide
→ Human Promotion Gate
→ Promote / Reject / Rollback
```

### 1. Select

只选择命名的 finished observations，或者在用户明确请求后按现有 signal 选择：

```bash
python3 .codestable/tools/cs_evolve.py case-new \
  --title "重复执行同一失败命令" \
  --run run-101 --run run-118
```

不会扫描所有任务历史，也没有“累计 N 次后自动进化”。

### 2. Diagnose

先判断问题属于：

```text
harness
project_knowledge
product_code
model_variance
environment
insufficient_evidence
```

只有 `harness` 才能创建候选，而且必须映射到 manifest 声明的可修改面。

### 3. Propose

候选是隔离 overlay，只能包含声明过的 surface 文件。提案时冻结 baseline version/content、每个文件的 base/candidate hash、candidate content hash 和不可变 candidate definition hash；不能修改 Gate、进化工具、Evaluator 协议、Observation、证据、registry 或版本快照。

### 4. Trusted Evaluate

仓库内置 challenge、签名结果导入和提升控制面，但不内置具体的外部 Evaluator Runner。完成可信评测还需要宿主提供隔离的 worktree、容器或 CI Runner，以及项目工作区之外的私有 held-out、safety suite 和 Evaluator 签名密钥。没有这个外部边界时，可以收集 Observation、诊断和创建候选，但不能将本地自报结果作为提升依据。

创建 challenge：

```bash
python3 .codestable/tools/cs_eval.py challenge \
  --case <case-id> --candidate <candidate-id> \
  --model-profile <profile> --adapter <adapter> \
  --evaluator <evaluator-id> --budget <budget-id>
```

外部 evaluator 在候选工作区之外运行 baseline/candidate，持有：

- 私有 held-out；
- safety suite；
- evaluator-only HMAC key；
- fresh sandbox / worktree / container。

项目只接收签名的聚合结果：

```bash
python3 .codestable/tools/cs_eval.py import \
  --case <case-id> --candidate <candidate-id> \
  --file <signed-aggregate-result.json>
```

导入会验证：

- challenge nonce；
- baseline version/content、candidate content/definition hash；
- protocol hash；
- model/adapter/evaluator/budget locks；
- `held_in / held_out / safety` 精确 split；
- 数值和 aggregate-only schema；
- evaluator-only HMAC 签名；
- 结果未被重复导入或事后修改。

因此不再支持候选或 Agent 用普通 `eval-record` 命令自行宣布通过。

### 5. Decide 与人工 Gate

```bash
python3 .codestable/tools/cs_evolve.py decide \
  --case <case-id> --candidate <candidate-id>
```

通过条件：

- 至少一个 split 有改善；
- held-in 与 held-out 不回归；
- safety 全过；
- token、时延、中断率、上下文字节不超过协议阈值；
- 签名评测结果仍完整。

即使通过，也只进入：

```text
accepted_pending_human_gate
```

所有 surface，包括低风险 routing/playbook，都必须人工批准：

```bash
python3 .codestable/tools/cs_evolve.py promote \
  --case <case-id> --candidate <candidate-id> \
  --human-approved --approved-by "maintainer" \
  --reason "评测改善且所有回归门通过"
```

## Harness 版本与回滚

```text
.codestable/harness/
├── manifest.json
├── registry.json
├── playbook.jsonl
└── versions/<version>/
```

每次提升前后都创建不可变快照和谱系事件。回滚：

```bash
python3 .codestable/tools/cs_evolve.py rollback \
  --version <version-id> --approved-by "maintainer" \
  --reason "上线 observation 显示新的 Gate 回归"
```

回滚不会自动提出下一版；需要优化时再创建新的显式 case。

## Runtime 结构

```text
.codestable/
├── config.json
├── attention.md
├── model/
├── knowledge/
├── work/
│   ├── active/
│   ├── archive/
│   └── archive-index.jsonl
├── observations/            # 临时、被动、普通任务不读取
│   ├── pending/
│   ├── flagged/
│   ├── selected/
│   └── index.jsonl
├── harness/                 # 当前 Harness、可修改面、版本和 playbook
├── evolution/               # 只有显式 /cs evolve 才读取
│   ├── cases/
│   ├── rejected/
│   └── index.jsonl
├── evals/                   # 受保护协议；私有 held-out 在工作区之外
├── reference/
└── tools/
    ├── cs_context.py       # 正常任务状态与按需上下文
    ├── cs_harness.py       # 正常任务只读 active Harness/playbook
    ├── cs_observe.py       # 被动临时运行记忆
    ├── cs_evolve.py        # 仅显式维护模式
    └── cs_eval.py          # challenge 与签名聚合结果边界
```

## 默认配置

```json
{
  "observability": {
    "enabled": true,
    "mode": "passive",
    "best_effort": true,
    "read_during_normal_runs": false,
    "capture": {
      "raw_prompts": false,
      "raw_model_responses": false,
      "source_or_diffs": false,
      "full_tool_output": false
    }
  },
  "evolution": {
    "mode": "manual",
    "run_during_normal_work": false,
    "auto_diagnose": false,
    "auto_propose": false,
    "auto_evaluate": false,
    "auto_promote": false,
    "require_selected_cases": true,
    "require_human_promotion_gate": true,
    "require_private_holdout": true
  },
  "evaluator": {
    "mode": "external_signed_aggregate",
    "require_signed_results": true,
    "private_holdout_location": "outside_candidate_workspace"
  }
}
```

## 安装与项目初始化

使用 `skills` CLI 安装：

```bash
npx skills add https://github.com/AdolphKevin/codestable-compact
```

确保安装 `cs` 和五个生命周期 Skill。`cs` 包含初始化项目级 Harness 运行时所需的工具、参考规则、manifest 和评测协议。

然后进入需要使用 CodeStable 的目标代码库，执行：

```text
/cs init
/cs doctor
```

这会在目标代码库创建 `.codestable/`，Harness 状态、Observation、候选、快照和回滚记录都保留在该项目内。也可以直接提交开发诉求；尚未初始化时 `/cs` 会在同一轮完成初始化并继续执行。

需要刷新已安装的项目运行时时执行：

```text
/cs upgrade
```

刷新前会备份已有的工具和参考规则，并保留当前 model、work 与 observations。如果项目中存在旧 `.codestable/telemetry/runs/`，可先 dry-run 再显式迁移：

```bash
python3 scripts/migrate_alpha_observations.py /path/to/project
python3 scripts/migrate_alpha_observations.py /path/to/project --apply
```

## 文档

中文文档入口：[`docs/zh-CN/README.md`](docs/zh-CN/README.md)

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/problem-solution-map.md`](docs/problem-solution-map.md)
- [`docs/design-decisions.md`](docs/design-decisions.md)
- [`docs/self-evolving-harness.md`](docs/self-evolving-harness.md)
- [`docs/migration-from-codestable.md`](docs/migration-from-codestable.md)
- [`docs/examples.md`](docs/examples.md)
- [`adapters/evolution-host-contract.md`](adapters/evolution-host-contract.md)

## 校验

```bash
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -v
```

项目运行时仅依赖 Python 标准库。

## License

MIT。参考项目及许可证见 [`ACKNOWLEDGEMENTS.md`](ACKNOWLEDGEMENTS.md)。
