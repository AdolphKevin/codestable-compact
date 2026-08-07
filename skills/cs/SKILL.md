---
name: cs
description: CodeStable 的单一项目知识入口。每次需求、任务、问题修复或重构开始前，按任务、路径和符号从 Markdown Wiki 提供需求、架构、接口、数据模型、异常处理、事务边界、兼容性、性能风险、安全边界、验收标准和历史决策；任务完成后写入可追溯任务记录，并把可复用结论沉淀为知识卡片。
license: MIT
compatibility: Requires Python 3.10+ and a readable project directory. Knowledge capture requires a writable project. Git is recommended but not required.
---

# `$cs` — 项目知识前置，任务知识回写

`$cs` 只有一个职责：让实现 Agent 在工作前获得项目知识，在工作后把新的长期知识写回项目 Wiki。

它**不是**开发流程控制器，不再路由 `feature / issue / refactor / roadmap / model`，不创建阶段，不决定实现路径，不用 evidence gate 代替真实测试，也不接管 Agent 的正常分析、编码和验证能力。

```text
用户任务
  ↓
只读知识简报（需求 / 架构 / 接口 / 数据 / 异常 / 事务 / 兼容 / 性能 / 安全 / 验收 / 决策）
  ↓
Agent 正常实现与验证
  ↓
任务记录 + 可复用知识卡片 + supersedes
```

## 1. 初始化或升级

定位项目根目录。没有 `.codestable/config.json` 时：

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <project-root>
```

旧版 CodeStable 或需要刷新工具时，先执行结构升级：

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <project-root> --upgrade
```

结构升级只替换 manifest 声明的发布文件，先备份被替换或退役的旧工具。它还会逐页列出并备份 `.codestable/model`、`.codestable/knowledge` 中的 Markdown，返回 `knowledge_migration.pages`。它不得自动把旧页转成卡片，也不得自动删除旧页。

`$cs upgrade` 不能在结构升级后结束。只要 `knowledge_migration.required` 为 `true`，必须按返回清单逐页完成以下流程，不能批量照抄旧知识：

1. **审计旧页**：一次只读一页，识别其中可能长期有效的原子结论；目录页、工作日志、过程说明和重复正文也必须作出明确判定。
2. **对照当前实现与测试**：沿旧页涉及的路径、符号和契约检查当前源码与可执行测试。旧页只能作为线索，不能作为 `verified` 证据；无法确认当前真相时保留该页并把升级报告为未完成。
3. **检查 current Wiki 覆盖**：用 `brief`、相关分类 README 和当前卡片逐条核对。已经覆盖的结论不得重复建卡；发生冲突时以当前真相写新卡并通过 `supersedes` 保留卡片历史。
4. **只补真正缺失的卡片**：为本页准备一个 `learn` payload。每页必须产生一个紧凑 task-note；只有经当前实现/测试确认、当前 Wiki 尚未覆盖且未来会复用的结论才进入 `items`。在 `task.source` 记录旧页路径、升级清单中的 SHA-256、备份路径和审计结论。先 `learn --dry-run`，再用 `plan_token` apply。
5. **移除已审计旧页**：apply 和 `doctor` 成功后，重新确认旧页 SHA-256 与清单一致、备份文件存在且同哈希，再从原 legacy 目录删除该页。历史内容保留在升级备份中，审计判定和新卡 provenance 保留在 task-note 中。

每页的审计结论至少区分：`migrated`（补了缺失卡片）、`covered`（current Wiki 已覆盖）、`obsolete`（当前实现/测试否定或已无未来价值）、`pending`（证据不足）。前三者可在满足第 5 步条件后移除旧页；`pending` 不得移除。旧页删除失败或仍有 `pending` 时，升级状态必须报告为未完成，不能宣称知识迁移成功。

不得删除 `.codestable/work`、observations、fixtures 或其他非旧知识页的项目数据。不得把 raw prompt、模型响应、完整日志、完整 diff、秘密或个人数据迁入 Wiki。

随后执行只读检查：

```bash
python3 .codestable/tools/cs_knowledge.py doctor
```

需要项目级常驻提醒时，可从本 Skill 的 `templates/AGENTS.codestable.md`
人工复制相关段落到项目规则中。bootstrap 不得自动创建、替换或合并项目
现有 `AGENTS.md`。

## 2. 任务开始前必须读取知识

每个新的开发逻辑任务都必须重新运行 `brief`。Skill 的使用状态不会自动跨用户任务、Agent turn、压缩上下文或新的 Git 提交流程持续生效；不能因为上一轮使用过 `$cs` 就跳过本轮知识读取。

用用户的原始要求生成第一次简报：

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '<完整任务描述>'
```

已经知道相关路径或符号时一并传入；路径和符号可重复：

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '<完整任务描述>' \
  --path src/orders/service.py \
  --path tests/test_orders.py \
  --symbol OrderService
```

`brief` 必须保持只读。它会：

- 读取人工维护的项目总览和分类摘要；
- 检索当前知识卡片；
- 默认排除已被取代的卡片；
- 展示相关历史任务和最近决策；
- 给出 11 个分类的覆盖与空白；
- 当前 Wiki 没有合格命中时，把旧版 `.codestable/model` 和 `.codestable/knowledge` 作为单独标注、必须复核的 legacy 线索返回。

若初步排查后真实路径或符号发生明显变化，带新 scope 再运行一次 `brief`。不要递归把整个 `.codestable` 塞进上下文。

## 3. 使用知识，但不要盲信知识

不要把不同性质的结论压成一条事实优先级。先判断知识在回答“应该怎样”还是“现在怎样”，再处理冲突：

- 当前用户明确要求拥有最高权限。
- 当前、已接受且适用于本 scope 的需求、约束和决策表达目标状态。实现或测试与之不符时，先判断是否为实现偏离，不能仅因代码不同就宣布知识过期。
- 带验证依据的行为事实表达已经确认过的当前状态。与公共契约、可执行测试或当前支持行为不符时，必须判断是行为回归、证据适用范围变化，还是卡片已经失效。
- 源码实现细节用于解释当前实现，但不能单独推翻已接受的目标，也不能替代可执行验证。
- `proposed`、`inferred`、`deprecated`、`superseded`、历史任务和 legacy 文档只提供上下文或线索，不能独立解决当前冲突。

冲突时必须显式指出不一致，沿 scope、证据和来源查明“实现需要修正”还是“知识需要更新”。不要为了保持任一侧表面一致而静默选择。确认旧知识失效后，用新卡片的 `supersedes` 指向旧卡片并保留 provenance。

删除、重命名或用新架构替换实现时，必须检查引用相关路径和符号的 current 卡。文件变化只是复核信号，不能自动证明知识错误；若长期结论仍适用则更新 scope，若已被新结论替换则由新卡显式 `supersedes`。

简报只提供上下文。Agent 仍应正常完成请求所需的代码阅读、设计、实现、测试、review 和风险检查。

## 4. 按逻辑任务延迟沉淀

### 4.1 逻辑任务边界

每个**逻辑任务**最终对应一条 `task-note`。逻辑任务由同一用户目标、同一主要交付物和同一连续调试/验收链共同界定：

- 用户补充错误日志、要求继续修复、调整同一实现或为同一验收目标追加补丁，默认都是原任务的继续；
- 只有用户明确开启独立目标，或主要交付物、验收标准、影响范围发生实质变化时，才创建新 task-note；
- 路径或涉及组件在排查中扩大只是参考信号，不能单独把任务拆开；
- 不得按一次 Agent turn、一次报错、一次补丁或一次 `learn` 调用划分任务。

例如，同一组匿名登录迁移 SQL 连续修复依赖遗漏、类型不匹配、分区表引用、索引限制、重复邮箱和孤儿引用，仍是一条迁移任务，不是多个 issue。

### 4.2 沉淀时机

默认等最终实现稳定并通过用户要求的最终验收后，再一次性以 `completed` 状态写入紧凑 task-note 和长期知识卡片。每个实际完成的开发任务必须在结束回复或提交前完成 `learn --dry-run`、使用 plan token apply 和 `doctor`。连续调试期间原则上不调用 `learn`；中间诊断、单次错误、失败方案、临时兼容和可能在下一轮被取代的推断留在会话中。

任务必须中断或交接时，可以创建或更新一条 `in-progress`、`partial` 或 `blocked` task-note，但 `items` 必须为空。只有 `completed` 任务可以创建或复用长期卡片；不得把未通过最终验收的推断写成 `verified/current` 知识。

`cancelled` 任务同样只记录紧凑结果，不产生卡片。

### 4.3 写入前聚合检查

每次准备 `learn` 前必须能明确回答：

1. 这是新逻辑任务，还是已有任务的继续？
2. 当前任务是否已经达到最终验收状态？
3. 是否已经存在对应 task-note；它的 ID 和 revision 是什么？
4. 哪些内容只是调试过程，应留在会话而不进入 Wiki？
5. 每张拟建卡片会被哪类未来任务复用，最终证据是什么？
6. 能否复用或合并进已有卡片，而不是新建卡片？

无法明确回答时，不应立即 apply；先保留会话上下文，必要时只运行 `brief` 或 `learn --dry-run` 查看候选。

### 4.4 首次创建与继续更新

首次需要落盘时，生成完整的 task 快照：

先生成模板：

```bash
python3 .codestable/tools/cs_knowledge.py template \
  --title '<任务标题>' \
  --kind '<requirement|task|issue|refactor|other>' \
  --output /tmp/cs-learning.json
```

根据**实际完成结果**填写 `/tmp/cs-learning.json`。`task.knowledge_summary` 必须说明新增、复用或 supersede 了哪些卡片；没有长期卡片时说明原因。先校验写入计划：

```bash
python3 .codestable/tools/cs_knowledge.py learn \
  --file /tmp/cs-learning.json \
  --dry-run
```

保存返回的 `plan_token`。确认内容准确后，用该 token 应用刚才验证过的同一计划：

```bash
python3 .codestable/tools/cs_knowledge.py learn \
  --file /tmp/cs-learning.json \
  --plan-token '<dry-run 返回的 plan_token>'

python3 .codestable/tools/cs_knowledge.py doctor
```

plan token 同时绑定 payload、Wiki 状态和工作区状态。dry-run 后只要工作区或 Wiki 发生变化，旧 token 就必须失效；重新检查最终实现并运行 `learn --dry-run`，不得绕过已经失效的计划。

`learn` 会锁定 Wiki，以逐文件原子替换和恢复日志写入 Markdown 卡片、任务记录及索引。普通写入异常会立即回滚；进程意外终止后，下一次 `learn` 会先恢复未提交事务。它会复用完全相同的卡片，并在重复提交同一 payload 时保持幂等。

首次 apply 返回稳定的 `task_id` 和 `task_revision: 1`。后续继续同一任务时，不新增 note；读取当前 task-note，把最新聚合结果作为**完整快照**提交：

```json
{
  "task": {
    "id": "T-...",
    "update_existing": true,
    "expected_revision": 1,
    "title": "原逻辑任务标题",
    "status": "completed",
    "request": "原始用户目标",
    "summary": "截至当前的紧凑处理摘要",
    "result": "当前最终结果",
    "deliverable": "主要交付物",
    "paths": [],
    "symbols": [],
    "tags": [],
    "verification": [],
    "source": {}
  },
  "items": []
}
```

更新时必须同时提供 `id`、`update_existing: true` 和 `expected_revision`。先 dry-run，再用返回的 plan token apply。工具保留原 ID、创建时间、路径、既有关联卡片和必要 provenance，只替换为最新紧凑正文并递增 revision；同一更新重复提交保持幂等。revision 或知识状态变化时，必须重新读取并 dry-run，不能覆盖他人的更新。

dry-run 的 `task_candidates` 表示标题、交付物或多条路径高度相符的已有任务，应优先判断是否更新它；`card_candidates` 表示同分类同标题的卡片，应选择复用、合并或显式 `supersedes`。候选只是防膨胀提示，工具不得自动模糊合并。

### 4.5 提交前只读漂移检查

Git commit 工具通常只处理 staged changes，不会自动执行 CodeStable 的 brief、learn 或知识审核，也不能替代知识回写。完成 learn 并暂存任务记录、卡片和生成索引后，推荐运行：

```bash
python3 .codestable/tools/cs_knowledge.py drift --cached
```

CI 比较目标分支时运行：

```bash
python3 .codestable/tools/cs_knowledge.py drift \
  --base origin/main \
  --format json
```

`drift` 只读检查 current 卡的仓库 path、保守 symbol 文本信号、Git 删除/重命名、语义变更对应 task-note 的完成状态、范围、验证和知识处置。它还会把 external、legacy 和 generated 路径按明确策略跳过。退出码 `0` 表示没有检测到阻断候选，`1` 表示需要处理，`2` 表示参数、Git 或读取失败。

`drift` 不能判断业务结论真假，不能把“文件删除”自动解释为旧知识错误，也不能自动改状态或生成新卡。每个候选仍必须由 Agent 结合当前要求、实现和可执行测试审核。

`drift --cached` 检测到未暂存的 `.codestable/wiki` 变化时必须失败，避免工作区中的卡片或 supersede 让 staged 提交被误判为已经完成知识回写。

## 5. 11 类可沉淀知识

| category | 应记录的长期内容 |
|---|---|
| `requirements` | 稳定需求、业务规则、约束、优先级、非目标 |
| `architecture` | 组件职责、依赖方向、关键数据流、系统边界 |
| `interfaces` | API、事件、协议、输入输出、失败语义 |
| `data-model` | 实体、字段、状态、约束、序列化、索引、迁移语义 |
| `error-handling` | 错误分类、传播、重试、降级、恢复、可观测性 |
| `transaction-boundaries` | 原子性、提交点、补偿、一致性、幂等、并发边界 |
| `compatibility` | 公共/持久化兼容、版本、迁移、回滚、弃用 |
| `performance-risks` | 热点、复杂度、容量、延迟、吞吐、内存、外部资源 |
| `security-boundaries` | 信任边界、认证授权、敏感数据、输入验证、滥用防护 |
| `acceptance` | 可观察完成条件、测试矩阵、验证入口、不可接受行为 |
| `decisions` | 已接受或提议的决策、理由、后果、替代方案、取代关系 |

一张卡片应表达一个稳定结论，并带上适用路径/符号、证据、置信度和来源任务。`verified` 必须有验证依据；决策必须有 rationale。创建前还必须同时满足：

- 对未来多个任务确实可复用；
- 已由最终实现、测试、生产兼容证据或用户明确接受的权威约束确认；
- 不是单次报错的处理过程，也不是仅为当前测试库存在的偶发脏数据细节；
- 当前 Wiki 不存在含义相同的卡片；能更新或复用时不新建；
- 不会在同一连续调试链的下一轮立即被取代。

## 6. 不应沉淀的内容

不要把以下内容写成长期卡片：

- 原始聊天、完整命令输出、完整 diff 或逐步操作日志；
- 仅本次有用的临时排查过程；
- 没有未来消费者的泛化建议；
- 未验证却写成当前事实的猜测；
- 密钥、token、个人数据或其他敏感信息；
- 与项目无关的通用编程常识。

反例与正例：

- “某次 SQL 执行遇到 bigint=text”通常只是本任务过程，不单独建卡；
- “某张测试表本次需要加入删除顺序”通常合并进 task-note 的最终摘要；
- “PostgreSQL 任意长正文不能建立普通 `LOWER(text)` B-tree”只有在它与本项目长期查询和索引设计相关并经最终证据确认时，才可建卡；
- “历史正式邮箱必须按 `lower(trim(email))` 合并而不能删除”若是稳定迁移决策并经最终验收确认，可以建卡。

这些内容必要时留在会话中。任务记录也应保持紧凑，只保留结果与可追溯依据。

## 7. 状态与取代

知识卡片状态：

- `current`：当前采用的事实、约束或决策；
- `proposed`：尚未被项目接受的提议，不能当作当前契约；
- `deprecated`：仍可能被看到，但不应继续用于新实现；
- `superseded`：由工具在新卡片声明 `supersedes` 后设置，默认检索不返回。

不要删除历史来制造“干净”。用 supersession 保留为什么发生变化以及新旧知识的可追溯关系。

`supersedes` 用于真正的长期结论演进，不用于记录同一任务内被后续修复淘汰的临时方案；后者不应成为卡片。

既有重复记录的整理必须采用显式 consolidate，而不能靠删除历史：选择一条 canonical task-note，汇总必要 provenance，重复 note 只保留指向 canonical 的关系，默认检索和索引展示折叠重复正文。卡片仅在结论确实变化时使用 `supersedes`；完全相同卡片复用原 ID。整理后运行 `reindex` 和 `doctor`，索引必须可确定性重建。当前 `learn` 更新协议只处理一个稳定 task ID，不得假装已经自动整理旧重复记录；在专用 consolidate 写入能力发布前，只能给出只读候选和整理计划，不能手工删除或直接改 Wiki 绕过事务保护。

## 8. 显式命令

| 请求 | 行为 |
|---|---|
| `$cs init` | 安装 Wiki runtime，运行 doctor |
| `$cs upgrade` | 结构升级后逐页审计旧知识，对照实现/测试与 current Wiki，只补缺失卡片，备份后移除已审计旧页，再运行 doctor |
| `$cs brief <任务>` | 只生成知识简报，不执行实现、不写文件 |
| `$cs status` | 运行 `cs_knowledge.py status` |
| `$cs doctor` | 只读完整性检查 |
| `$cs doctor --check-current-references` | 在结构检查之外，只读检查 current path/symbol 引用 |
| `$cs drift [--cached|--base <ref>|--references-only]` | 只读检查 current 引用、Git 变更与知识回写完整性 |
| `$cs reindex` | 显式重建机器与 Markdown 索引 |
| `$cs <开发请求>` | 先 brief，同一次调用中正常完成任务，再 learn + doctor |

用户明确要求“只分析、不要写文件”时，遵守只读边界：可以运行 `brief / status / doctor`，但不得运行 `learn / reindex / bootstrap`。可在回答中给出建议沉淀项，但不能暗示已经写入。

普通 `doctor` 只证明 Wiki 结构、链接、索引和事务记录一致；通过不代表 current 知识仍与源码一致，也不代表实现符合需求。需要引用检查时显式使用 `doctor --check-current-references`，需要 Git/task-note 检查时使用 `drift`。

## 9. 最终回复

完成开发请求时，除了实现和验证结果，还应简短说明：

- 本次读取了哪些关键项目知识；
- 新建或复用了哪些知识卡片；
- 是否取代了旧知识；
- 若没有长期卡片，说明只写入了任务记录以及为什么没有可复用结论。
