# 架构

## 1. 设计主张

CodeStable Compact 将软件系统而非 Agent 作为工作的持久中心。

运行时按信息的**语义半衰期**分层：

| 层 | 含义 | 生命周期 | 默认检索 |
|---|---|---:|---|
| `model/` | 软件当前是什么、必须保持哪些事实 | 长期 | 是，通过小型索引和显式链接 |
| `knowledge/` | 经具体任务验证的可复用工程知识 | 长期 | 是，仅定向搜索 |
| `work/active/` | 当前正在修改什么 | 短期 | 是，仅精确任务 |
| `work/archive/` | 旧任务如何完成 | 历史 | 否 |
| 源码/测试/配置 | 可执行证据 | 当前 | 是，仅限改动面 |

这种分层避免两类常见错误：把所有历史设计当作当前真相，以及仅因持久文档存在就反复全部加载。

## 2. 用户可见拓扑

```text
                        ┌───────────┐
真实诉求 ─────────────▶ │    cs     │
                        └─────┬─────┘
                    优先恢复 │ 否则分类
        ┌──────────────┬──────┼──────┬──────────────┐
        ▼              ▼      ▼      ▼              ▼
     cs-feat        cs-issue cs-refactor cs-roadmap cs-model
        │              │      │      │              │
        └──────────────┴──────┴──────┴──────────────┘
                         立即继续
```

`cs` 不是“推荐页面”。路由是实现细节，默认不能成为阻塞状态。直接生命周期 Skill 仍可供专家、确定性自动化和测试使用；普通用户只需要 `/cs`。

## 3. 先路由后提问，先取证后提问

入口按以下顺序执行：

1. 解析显式命令，如 `init`、`status`、`continue`、`route`、`doctor`。
2. 检查 active work 元数据，而非完整历史。
3. 存在精确匹配时恢复该任务。
4. 否则分类主要事件类型。
5. 提问前检查仓库证据。
6. 在同一次调用中启动所选生命周期。

只有仓库证据无法提供的事实才提问，例如产品意图、不可用凭据、不可逆权衡或两个实质不同但都有效的契约。路由决定本身不属于这类事实。

## 4. 事件分类

| 事件类型 | 正向信号 | 排除信号 |
|---|---|---|
| `feature` | 全新可观察能力、新支持行为、新集成 | 只是已有预期行为损坏 |
| `issue` | 缺陷、回归、错误输出、异常、卡死、性能退化 | 行为正确，仅需改善结构 |
| `refactor` | 保持行为，改变结构、依赖方向、命名或复杂度 | 用户要求新的外部可观察行为 |
| `roadmap` | 多项协同能力、顺序/契约不确定、跨系统计划 | 已有一个边界清晰的交付物 |
| `model` | vision、领域词汇、requirement、contract、ADR、持久知识 | 可执行代码修改是主要结果 |

混合诉求选择最先产生独立可验证结果的事件，记录次要工作，并在必要时自动转换。例如由架构腐化导致的 Bug 先作为 `issue`，获得复现和根因证据后可创建关联的 `refactor`。

## 5. 自适应通道

不需要独立的快速通道 Skill。复杂度属于任务，而不是单独的用户意图。

### `micro`

必须同时满足：仅涉及一个局部表面；小 diff 可回滚；不改变公共 API 或持久化 schema；不涉及安全、权限、支付或破坏性操作；可用现有测试或一个小测试验收。仍需检查证据并验证结果，只减少过程记录。

### `standard`

用于一般的有界工程工作，记录意图、证据、设计或根因、实现计划、改动文件和验证。

### `high-risk`

满足任一条件即可：持久数据迁移或破坏性操作；公共 API、协议、事件或 schema 兼容性；认证、授权、秘密或安全边界；支付、计费、配额或财务正确性；跨服务发布或可用性风险；不可逆供应商或架构承诺；没有可信回滚或验证路径。

该通道要求显式回滚/发布策略，并可能创建人工 Gate。证据触发风险时可随时升级；只有证据消除触发因素后才能降级。

## 6. 工作状态机

所有可执行工作使用同一信封：

```text
created → active → blocked? → active → done → archived
                 └─ cancelled ────────────────▶ archived
```

各 kind 使用自己的 `stage`：

```text
feature:  intake → evidence → design → implement → verify → accept
issue:    intake → reproduce → analyze → fix → verify → accept
refactor: intake → characterize → design → implement → verify → accept
roadmap:  discover → frame → contracts → decompose → review → activate
model:    inspect → edit → validate → index
```

`state.json` 是 status 和 stage 的权威来源。文件是否存在只能作为辅助证据，不能代替状态机。

## 7. 最小工作聚合

每个 active work 目录只有三个必需文件。

### `state.json`

机器可读控制状态，包括身份、kind、lane、stage、status；作用域路径、符号和关键词；指向 model/knowledge 的显式链接；Gate 状态和原因；验证命令及最近结果；父子任务关系。文件保持很小，可始终安全读取。

### `work.md`

仅包含该 lane 和 kind 所需章节的人类可读聚合文档。设计审查、代码审查、QA 和验收结论追加在这里，而不是每阶段一个文件。通过的临时审查无需文字；只记录决策、失败、例外、证据和持久结论。

### `context.json`

读取回执映射，为每个已读路径保存规范化相对路径、SHA-256、大小、修改时间、读取阶段/原因和时间戳，不缓存正文。未变化的回执仅可在同一实时会话且理解仍在上下文时复用；冷会话必须使用新 key 并重读必要材料。

## 8. 上下文规划器

规划器是保守过滤器，不是自治语义预言机：

```bash
python3 .codestable/tools/cs_context.py plan \
  --work <id> --stage <stage> --session <live-conversation-key>
```

它返回 `always`（小型控制状态）、`read`（必需且新增/变化的路径）、`reuse`（已读且未变化）、`missing`（无法解析的显式链接）。规划器不递归扫描 archive，不自动打开所有 model 文档；尚无显式链接时只提供 `model/INDEX.md` 作为指针。

model 和 knowledge 顶层索引默认最多 160 行；超过时由 `cs-model` 按有界上下文或领域拆分，顶层只保留指针。

### 检索阶梯

```text
0. 当前对话
1. 精确 active work 状态和当前阶段章节
2. attention.md，仅在非空且变化时
3. 显式链接的 model/knowledge，仅在变化时
4. 作用域内源码、测试、配置和可执行契约
5. 定向搜索当前状态知识
6. 带书面原因搜索 archive-index；识别候选后才能深搜历史正文
```

不能仅因为下一层存在就继续下探。

## 9. 当前真相与历史

历史 feature 文档可能包含过时假设、废弃设计和后来已变化的约束，只能作为过去的证据。Archive 搜索先查轻量元数据索引；扫描归档正文需要显式 `--deep` 和理由。

归档前，验收生命周期执行一次**提升检查**：

| 发现 | 目标位置 |
|---|---|
| 当前用户可见能力 | `model/requirements/` |
| 稳定接口或事件形状 | `model/contracts/` |
| 约束未来工作的架构权衡 | `model/decisions/` |
| 领域术语 | `model/domain.md` |
| 可复用陷阱、诊断或实现约束 | `knowledge/notes/` |
| 任务特定讨论、被拒局部方案、临时日志 | 仅 archive |

只有提升后的材料会进入未来正常检索；完整任务仍可供显式考古。

## 10. Gate 模型

Gate 表示 Agent 缺少安全决策所需权限，而不是某个阶段结束。

### 自动内部检查

设计一致性与范围审查、最简方案审查、正确性/回归/复杂度 diff 审查、测试/lint/typecheck/验收，以及文档/model 提升审查都不暂停用户。失败时回到负责阶段并继续。

### 人工 Gate 触发条件

仅在以下至少一项成立时暂停：不可逆或破坏性操作；存在多个合理选项的公共兼容性决策；安全边界或权限策略；没有已批准策略的持久数据迁移；重大成本、可用性或运维风险；与已接受决策冲突且实现证据无法解决；现有权限无法观察验收；用户明确要求审批。

Gate 输出必须包含具体决策、证据、推荐选项、替代方案和后果。“批准路由到 cs-issue”不是有效 Gate。

## 11. 自动审查循环

### Feature

```text
design → self-review
  ├─ 阻塞性技术缺陷 → 修改设计
  ├─ 需要人工决策 → Gate
  └─ 清晰 → implement

implement → diff review → 修复至通过
          → QA/acceptance → 修复至通过
          → promote → archive
```

### Issue

```text
reproduce → root cause → 最小修复
          → regression review → 验证原始症状
          → 仅在可复用时提升诊断知识 → archive
```

### Refactor

```text
刻画行为 → 设计最小结构调整
         → 增量 diff review
         → 等价性验证 → archive
```

## 12. 最小化策略

所有生命周期在增加机制前依次检查：请求行为是否已存在；能否复用现有路径/模式/helper；标准库或原生平台是否可解决；已安装依赖是否足够；删除或简化是否能解决根因；能证明结果的最小改动是什么。

新增抽象、依赖、工件或兼容层必须有具体证据，“以后可能有用”不算证据。

## 13. 可移植边界

规范工作流位于 `skills/`，项目共享行为复制到 `.codestable/reference/`，宿主 manifest 和 alias 位于 `adapters/` 且不包含生命周期逻辑：

```text
可移植 Skills → 项目本地 runtime/reference → 可选宿主 adapter
```

宿主 schema 可以变化而不改变生命周期语义，一个宿主也不能暗中拥有不同工程规则。

## 14. 失败与恢复

- `state.json` 损坏时，`doctor` 报告问题；仅根据 `work.md` 和 Git 证据重建并记录修复。
- 链接文件移动时，规划器报告 `missing`；在当前 model/code 中寻找替代并更新链接。
- 回执过期时，hash 不匹配强制重读。
- Agent 已改代码但未推进状态时，以 Git 证据为准，先对齐状态。
- 旧归档设计与当前 model/code 冲突时，以当前已接受 model 和可执行行为为准，除非任务明确调查回归。
- `validation.last_result` 未记录非失败结果前不能归档已完成任务；取消任务可不验证直接归档。

## 15. 两种模式，两种权限

```text
正常模式（worker 权限）
request → route/resume → evidence → 修改产品 → task verify → accept
                         └── 尽力写入被动 observation

维护模式（maintainer + evaluator + human 权限）
显式 select → diagnose → candidate → trusted evaluate → decide
→ human promotion Gate → version/rollback
```

正常模式拥有 `model/`、`knowledge/`、`work/`，只追加 `observations/`；不得读取 observation/evolution 历史、创建候选、运行 Harness 基准或修改 active Harness。维护模式只能读取显式选中的 observation 和压缩 case 证据；外部 evaluator 拥有私有 held-out 和签名密钥，人类拥有提升权限。

## 16. 作为飞行记录器的被动 Observation

每次调用记录一个临时目录：

```text
.codestable/observations/<state>/<run-id>/
├── meta.json
├── events.jsonl
└── outcome.json
```

`meta.json` 绑定 work id、route、lane、起止 stage、active Harness version、model profile、adapter 和提交；`events.jsonl` 保存少量元数据事件；`outcome.json` 保存正常任务 verifier、signals 和聚合指标。

Recorder 尽力而为且不阻塞，不增加模型调用，不跨 run 分析，不记录原始 prompt、源码、diff、secret、私有 held-out 或逐任务 evaluator trace，并限制事件数、payload 大小和保留期。状态只有 `pending`、`flagged`、`selected`。Flag 只是索引，不能证明 Harness 缺陷或触发进化。

## 17. 上下文与数据隔离

```text
.codestable/model/                 当前软件真相
.codestable/knowledge/             已验证的项目复用知识
.codestable/work/                  当前和归档的软件工作
.codestable/observations/          临时运行证据；正常模式只写
.codestable/harness/               active Harness、manifest、playbook、versions
.codestable/evolution/cases/       显式维护 case
.codestable/evals/                 受保护评测协议和公开 fixture
```

`cs_context.py plan` 和正常搜索排除 observations、evolution、evals 与 Harness version 历史。正常生命周期只能通过只读 `cs_harness.py` 查询少量已提升 active playbook；该工具没有控制面依赖或修改命令。Evolution case 从命名的已完成 observations 开始，只写压缩 `evidence.json`，不递归加载历史 run。

## 18. 显式选择与诊断

不存在由调度器、阈值或 run 次数自动创建的 evolution case。Maintainer 必须显式选择 run id 或已有 signal；选择会把已完成 observation 移至 `selected/` 并冻结 baseline Harness version。

诊断分类为 Harness 行为、项目知识缺口、产品代码缺陷、模型方差、环境/工具问题或证据不足。只有 Harness 诊断可以继续，且必须指出 manifest 声明的可修改 surface 和可证伪机制；其他分类关闭 case，不创建 Harness candidate。

## 19. 可修改与受保护表面

初始可修改表面包括 routing、retrieval、minimality、结构化 playbook、lifecycle policy、artifact schema 和 context tool。每个表面有风险等级，但包括低风险改动在内的所有提升都需要人工 Gate。

受保护表面包括 config 与 Gate policy；只读 Harness reader 和 observation/evolution/evaluator 工具；评测协议与私有 held-out；observations 和 case evidence；manifest、registry、version snapshots；签名密钥、sandbox 和资源策略。

Candidate 是只包含声明路径的隔离 overlay。提案记录 base/candidate hash，candidate 无法修改自身白名单或评测规则。

## 20. 可信 Evaluator 边界

`cs_eval.py challenge` 冻结 baseline Harness version 与 active content hash、candidate content/definition hash、评测协议 hash、model profile、adapter、evaluator、budget、精确 splits/repeats 和随机 nonce。

宿主在全新隔离环境中用 `held_in`、仅 evaluator 可见的 `held_out` 和 `safety` 运行 baseline/candidate。Candidate 和正常 worker 永远拿不到私有任务或 evaluator-only HMAC key。

项目只接受聚合结果。`cs_eval.py import` 验证 challenge digest、签名、nonce、baseline content、candidate overlay/definition、protocol lock、精确 split schema、分数范围、aggregate-only 字段和每个 challenge 仅一个结果。故意不提供直接无签名的 `eval-record`。

进程内 evaluator 不会因此自动可信；信任依赖 adapter 隔离以及密钥与 candidate/worker 的隔离。控制面只让边界可审计并拒绝未认证结果。

## 21. 确定性决策与人工 Gate

验证结果只有在至少一个必需 split 改善、held-in/held-out 通过率不回归、配置时 safety 全部通过、token/时长/中断/上下文指标不超过协议限制，且导入结果保持不变时才通过。

通过只产生 `accepted_pending_human_gate`，不会直接成为 active version。Gate 展示选定证据、诊断、精确 diff surface、各 split 结果、资源指标、风险、替代方案和回滚目标。

提升会再次验证 baseline 仍 active、被评测的 candidate definition 字节不变、所有 challenge/result/overlay hash 匹配；随后原子化地快照 baseline、应用 overlay、快照新版本并记录 actor/reason 谱系。

## 22. 版本谱系与回滚

```text
.codestable/harness/
├── manifest.json
├── registry.json
├── playbook.jsonl
└── versions/<version>/
```

快照包含所有声明的可修改表面、hash 和元数据。回滚恢复命名的已验证快照并记录 actor/reason。回滚或之后的 flagged observation 不会自动提出替代版本，必须建立新的显式 case。

## 23. 结构化 Playbook

`harness/playbook.jsonl` 是 active、已评测规则的增量列表，包含 id、scope、evidence 和 confidence；它不是单体 prompt，也不会在每个任务后重写。Playbook 修改是普通有界 candidate，必须经过可信评测和人工提升 Gate。

正常生命周期只通过 `cs_harness.py` 按 kind、stage 和已有 scope keyword 读取少量适用规则，绝不通过 `cs_evolve.py`。未验证的任务反思不能进入持久 playbook。

## 24. 宿主 Adapter 责任

可移植包不内置模型 API、私有基准或容器服务。合规 adapter 必须：

1. 在正常/直接 Skill 调用外围调用被动 recorder，且不把记录暴露给模型上下文；
2. 在嵌套生命周期间传递同一个 observation id，避免重复 trace；
3. 使用相同锁定条件，在全新 worktree/container 中运行 baseline/candidate；
4. 将私有 held-out、evaluator 实现和 HMAC key 隔离在 candidate/worker mount 与环境之外；
5. 仅输出签名的聚合结果；
6. 仅在显式人工 Gate 后调用提升；
7. 强制执行 sandbox、时间、网络、secret 和清理边界。

没有隔离 adapter 时，包仍提供 observation、selection、有界 candidate、versioning 和确定性 guard，但不得宣称本地自报评测可信。
