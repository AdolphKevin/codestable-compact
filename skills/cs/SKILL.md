---
name: cs
description: CodeStable 的单一项目知识入口。每次需求、任务、问题修复或重构开始前，按任务、业务主题、仓库范围、路径和符号从 Markdown Wiki 提供 11 类当前知识；任务完成后写入可追溯任务记录，并只把有范围、有证据、未来可复用的稳定结论沉淀为知识卡片。
license: MIT
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
任务记录 + 原子知识卡片 + 主题链接视图 + 可追溯取代关系
```

## 1. 初始化或升级

定位项目根目录。调用知识命令前，先从**当前 Skill** 运行只读预检：

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <project-root> --check
```

它验证项目保存的数据结构能否由当前 Skill 的共享知识工具读取，并检查本文件命令表
声明的命令确实存在。发行版本或受管资产存在差异时只提供信息，不要求每个项目复制
一份工具。只有数据模式或结构不兼容时状态才是 `needs-upgrade`；不要自动修改项目，
应明确报告并要求执行 `$cs upgrade`。状态为 `not-installed` 时才执行初始化。预检
通过时已包含共享工具针对目标项目执行的 `doctor` 只读结构结果。

没有 `.codestable/config.json` 时：

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <project-root>
```

旧版 CodeStable 或项目数据结构需要迁移时，先执行结构升级：

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <project-root> --upgrade
```

结构升级只原位更新或退役 manifest 声明的发行版文件，不创建自动备份目录。旧版
项目内知识工具只会在这次显式升级中退役；初始化和只读预检都不会复制或删除它。
升级还会逐页列出 `.codestable/model`、`.codestable/knowledge` 中 Markdown 的路径、
SHA-256 和字节数，返回 `knowledge_migration.pages`。旧页必须原地保留，升级不得
自动把它转成卡片或删除。旧版本留下的 `.codestable/backups` 必须忽略且不得改动。

结构升级的返回值必须满足 `runtime_source: "skill"` 和
`runtime_contract.ok: true`。后者逐项验证当前 Skill 的共享工具是否实现命令表；
缺少 `audit`、`topics list`、`topics suggest` 等任一命令时，升级不得报告完成。

`$cs upgrade` 不能在结构升级后结束。只要 `knowledge_migration.required` 为 `true`，必须按返回清单逐页完成以下流程，不能批量照抄旧知识：

1. **审计旧页**：一次只读一页，识别其中可能长期有效的原子结论；目录页、工作日志、过程说明和重复正文也必须作出明确判定。
2. **对照当前实现与测试**：沿旧页涉及的路径、符号和契约检查当前源码与可执行测试。旧页只能作为线索，不能作为 `verified` 证据；无法确认当前真相时保留该页并把升级报告为未完成。
3. **检查 current Wiki 覆盖**：用 `brief`、相关分类 README 和当前卡片逐条核对。已经覆盖的结论不得重复建卡；发生冲突时以当前真相写新卡并通过 `supersedes` 保留卡片历史。
4. **聚合升级审计**：一次 upgrade 是一个逻辑任务，只创建或更新一条 `kind: knowledge-migration` task-note。把每页路径、清单 SHA-256、字节数、结论、紧凑 disposition 和当前证据写入 `task.source.knowledge_migration.pages` 的完整账本；不得为每页另建普通 task-note。只有经当前实现/测试确认、current Wiki 尚未覆盖且未来会复用的结论才进入 `items`。每批写入先 `learn --dry-run`，再用 `plan_token` apply；后续批次用原 task ID 和 revision 更新。
5. **保留并隔离旧页**：apply 和 `doctor` 成功后，重新确认原地旧页的 SHA-256 与字节数仍与清单一致。兼容升级不删除或复制原页；逐页审计账本记录其处置，普通任务默认不读取旧目录。只有用户另行明确授权的数据清理任务才能考虑删除，而且不得删除未知或项目拥有的数据。

每页的审计结论至少区分：`migrated`（补了缺失卡片）、`covered`（当前 Wiki 已覆盖）、`obsolete`（当前实现/测试否定或已无未来价值）、`pending`（证据不足）。这些状态不授权删除原页；`pending` 存在时，`knowledge_migration.complete` 必须为 `false`，task-note 保持 `partial`，升级必须报告未完成。partial knowledge-migration 可写入已逐项获得证据的 accepted/verified 卡片；这不表示整个 upgrade 已完成。

不得删除 `.codestable/work`、observations、fixtures 或其他非旧知识页的项目数据。不得把 raw prompt、模型响应、完整日志、完整 diff、秘密或个人数据迁入 Wiki。

随后执行只读检查：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> doctor
```

需要项目级常驻提醒时，可从本 Skill 的 `templates/AGENTS.codestable.md`
人工复制相关段落到项目规则中。bootstrap 不得自动创建、替换或合并项目
现有 `AGENTS.md`。bootstrap 和 `doctor` 会只读检查其中指向不存在旧入口、
退役结构或多个冲突入口的声明，并给出把入口统一到
`.codestable/wiki/INDEX.md` 的建议。

## 2. 任务开始前必须读取知识

每个新的开发逻辑任务都必须重新运行 `brief`。Skill 的使用状态不会自动跨用户任务、Agent turn、压缩上下文或新的 Git 提交流程持续生效；不能因为上一轮使用过 `$cs` 就跳过本轮知识读取。

用用户的原始要求生成第一次简报：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> brief \
  --task '<完整任务描述>'
```

已经知道相关路径或符号时一并传入；路径和符号可重复：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> brief \
  --task '<完整任务描述>' \
  --path src/orders/service.py \
  --path tests/test_orders.py \
  --symbol OrderService \
  --scope 'shared-contracts:events/order.py#OrderCreated'
```

`brief` 必须保持只读。它会：

- 单独读取人工维护的项目总览和最多三条相关分类摘要；摘要不占卡片总量和分类配额，也不计入卡片覆盖；
- 检索当前知识卡片；排序固定采用“精确结构化范围/路径/符号 → 路径层级 → 业务主题 → 标题/标签 → 正文”的优先级，词语堆叠不能压过精确范围；
- 将提议知识与历史知识分开；默认排除已弃用和已被取代的卡片；
- 展示相关历史任务和最近决策；
- 给出 11 个分类的覆盖与空白；
- 为每个结果给出机器可读 `match_reasons`，并生成绑定任务、范围、卡片状态、revision 和内容哈希的只读回执；回执只证明“展示过”，不能充当 `knowledge_use`；
- 默认不读取保留的旧版 `.codestable/model` 和 `.codestable/knowledge`。只有迁移、冲突或历史追踪任务才显式使用 `--include-legacy`，并把结果作为必须复核的线索。

若初步排查后真实路径或符号发生明显变化，带新 scope 再运行一次 `brief`。不要递归把整个 `.codestable` 塞进上下文。

### 2.1 业务主题治理

主题是当前卡片的第二种导航，不复制正文。项目必须在配置中明确选择：

- `disabled`：小项目明确不使用主题；
- `manual`：主题由人维护，可以部分覆盖；空配置会被报告为未完成配置，而不是“已启用且健康”；
- `required`：`audit` 按显式最小覆盖率验收。

Agent 不得根据业务自然语言猜主题名称。不确定时不要传 `--topic`，优先依赖完整
任务描述、路径、符号和仓库范围；需要主题筛选时先运行：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> topics list
```

只使用列表返回的规范名称或别名。`brief` 收到未知主题时会警告、给出确定性的
近似名称并忽略该主题，其他有效检索信号仍继续工作。这个容错只属于只读检索；
`learn` 和 `topics update` 仍必须拒绝未知主题，避免把拼写错误写入 Wiki。

候选只能来自可复现的结构化信号。先运行只读 `topics suggest`，人工修改候选后再执行：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> topics update \
  --file /tmp/cs-topics.json \
  --dry-run

python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> topics update \
  --file /tmp/cs-topics.json \
  --plan-token '<dry-run 返回的 plan_token>'
```

批量赋值必须绑定卡片 revision，并使用与 `learn` 相同的锁、状态绑定、恢复日志和回滚。主题重命名或合并通过 `aliases`、`replaces` 和配置中的 `topic_history` 保留导航历史；不得用自由文本聚类自动写卡或主题。

## 3. 使用知识，但不要盲信知识

不要把不同性质的结论压成一条事实优先级。先判断知识在回答“应该怎样”还是“现在怎样”，再处理冲突：

- 当前用户明确要求拥有最高权限。
- 当前、已接受且适用于本 scope 的需求、约束和决策表达目标状态。实现或测试与之不符时，先判断是否为实现偏离，不能仅因代码不同就宣布知识过期。
- 带验证依据的行为事实表达已经确认过的当前状态。与公共契约、可执行测试或当前支持行为不符时，必须判断是行为回归、证据适用范围变化，还是卡片已经失效。
- 源码实现细节用于解释当前实现，但不能单独推翻已接受的目标，也不能替代可执行验证。
- `proposed`、`inferred`、`deprecated`、`superseded`、历史任务和 legacy 文档只提供上下文或线索，不能独立解决当前冲突。

冲突时必须显式指出不一致，沿 scope、证据和来源查明“实现需要修正”还是“知识需要更新”。不要为了保持任一侧表面一致而静默选择。确认旧知识失效后，用新卡片的 `supersedes` 指向旧卡片并保留 provenance。

删除、重命名或用新架构替换实现时，必须检查引用相关范围、路径和符号的 current 卡。文件变化只是复核信号，不能自动证明知识错误；若长期结论仍适用，则用卡片 `operation: update`、原卡 ID 和 revision 更新范围并保留 `scope_history`；若已被新结论替换，则由新卡显式 `supersedes`。不得凭猜测迁移旧路径。

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

任务必须中断或交接时，可以创建或更新一条 `in-progress`、`partial` 或 `blocked` task-note，但 `items` 必须为空。只有 `completed` 任务可以创建或复用长期卡片；唯一例外是 `partial` knowledge-migration 可沉淀已逐项获得最终证据的 accepted/verified 结论，同时让证据不足页面保持 pending。不得把未通过最终验收的推断写成 `verified/current` 知识。

`cancelled` 任务同样只记录紧凑结果，不产生卡片。

### 4.3 写入前聚合检查

每次准备 `learn` 前必须能明确回答：

1. 这是新逻辑任务，还是已有任务的继续？
2. 当前任务是否已经达到最终验收状态？
3. 是否已经存在对应 task-note；它的 ID 和 revision 是什么？
4. 哪些内容只是调试过程，应留在会话而不进入 Wiki？
5. 每张拟建卡片至少会被哪两个具体未来场景复用，最终证据和适用范围是什么？
6. 能否复用或合并进已有卡片，而不是新建卡片？

无法明确回答时，不应立即 apply；先保留会话上下文，必要时只运行 `brief` 或 `learn --dry-run` 查看候选。

不要把任务预先划分为“小、中、大”来减少知识步骤。所有开发任务使用同一组读取、
知识处置、dry-run、apply 和检查约束；输入复杂度只由最终知识处置决定：没有新长期
结论时 `items` 为空，需要新卡时才为对应知识分类生成并填写完整卡片。

### 4.4 首次创建与继续更新

首次需要落盘时，生成紧凑的 task 快照。默认模板不假设任务产生新长期知识：

先生成模板：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> template \
  --title '<任务标题>' \
  --kind '<requirement|task|issue|refactor|other>' \
  --output /tmp/cs-learning.json
```

只有确认存在新的稳定结论时，才按知识分类增加卡片模板；可重复指定：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> template \
  --title '<任务标题>' \
  --card-category architecture \
  --card-category acceptance \
  --output /tmp/cs-learning.json
```

卡片默认继承 task 的范围、主题和标签，只有边界更窄时才在 item 中覆盖。默认值、空
数组、索引、编号、时间和哈希由工具处理；Agent 仍必须填写请求、实际结果、验证、
知识处置，以及每张卡片的结论、证据和未来复用场景。

根据**实际完成结果**填写 `/tmp/cs-learning.json`。`task.knowledge_summary` 必须说明新增、复用或 supersede 了哪些卡片；没有长期卡片时说明原因。先校验写入计划：

模板中的 `__REPLACE__` 都必须替换；原样模板、泛泛的“以后修改时复核”或自由文本证据会被 strict dry-run 拒绝。新卡证据使用 `{kind, artifact, result, supports}`；未来复用场景使用 `{change, actor, constraint}`，且至少两项内容不同。

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> learn \
  --file /tmp/cs-learning.json \
  --dry-run
```

保存返回的 `plan_token`。确认内容准确后，用该 token 应用刚才验证过的同一计划：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> learn \
  --file /tmp/cs-learning.json \
  --plan-token '<dry-run 返回的 plan_token>'

python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> doctor
```

`learn` 默认返回紧凑 JSON，保留计划令牌、写入计划、任务与卡片候选、冲突、警告、
需要处理和无法验证的引用及各类计数，只省略通常很长的“已验证引用”明细。需要逐项
诊断时显式添加 `--full`；旧 `--compact` 作为默认行为的兼容别名保留。plan token 同时绑定 payload、
Wiki 状态和工作区状态。dry-run 后只要工作区或 Wiki 发生变化，旧 token 就必须
失效；重新检查最终实现并运行 `learn --dry-run`，不得绕过已经失效的计划。

`learn` 会锁定 Wiki，以逐文件原子替换和恢复日志写入 Markdown 卡片、任务记录及索引。普通写入异常会立即回滚；进程意外终止后，下一次 `learn` 会先恢复未提交事务。它会复用完全相同的卡片，并在重复提交同一 payload 时保持幂等。

首次 apply 返回稳定的 `task_id` 和 `task_revision: 1`。后续继续同一任务时，不新增
note；先让工具从当前 task-note 生成更新模板，再修改实际变化的字段：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> template \
  --task-id 'T-...' \
  --output /tmp/cs-learning.json
```

模板已带当前 revision、正文、范围、来源和历史 `knowledge_use`，避免手工复制旧
task-note 或误改历史证据。最终仍以完整快照提交，其核心控制字段如下：

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

更新时必须同时提供 `id`、`update_existing: true` 和 `expected_revision`。先 dry-run，
再用返回的 plan token apply。工具保留原 ID、创建时间、路径、既有关联卡片和必要
provenance，只替换为最新紧凑正文并递增 revision；同一更新重复提交保持幂等。
历史 `knowledge_use` 记录的是当时实际读取的卡片 revision，后续卡片升级时原样保留；
只有本次产生新的使用影响时，才用最新 brief revision 追加一项证据。revision 或知识
状态变化时，必须重新生成模板并 dry-run，不能覆盖他人的更新。

dry-run 的 `task_candidates` 表示标题、交付物或多条路径高度相符的已有任务，应优先判断是否更新它；`card_candidates` 表示同分类同标题或高重合结论的卡片，应选择复用、更新，或在结论真正变化时显式 `supersedes`。只有正交结论才能用 `new_card_reason` 解释后另建卡；候选只是防膨胀提示，工具不得自动模糊合并。

新建 payload 命中强 task candidate 时，dry-run 不返回可应用 token；必须改用 `update_existing`，或用 `task.new_task_reason` 明确说明为什么这是独立目标。该理由只用于消除误建歧义，不能用路径扩大或新一轮报错冒充独立任务。

### 4.5 提交前只读漂移检查

Git commit 工具通常只处理 staged changes，不会自动执行 CodeStable 的 brief、learn 或知识审核，也不能替代知识回写。完成 learn 并暂存任务记录、卡片和生成索引后，推荐运行：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> drift --cached
```

CI 比较目标分支时运行：

```bash
python3 <this-skill-directory>/scripts/cs_knowledge.py --root <project-root> drift \
  --base origin/main \
  --format json
```

`drift` 只读检查 current 卡的仓库范围、保守 symbol 文本信号、Git 删除/重命名、
语义变更对应 task-note 的完成状态、代表性范围、验证和知识处置。task-note 的范围用于
证明记录与本次改动直接相关，不是完整 diff 清单；至少一个结构化 self scope、路径或
变更符号命中即可，不要为了通过检查枚举所有文件。已配置相关仓库会按仓库内路径
检查；未配置外部仓库报告“无法验证”，不能报告为文件缺失。旧 `paths` / `symbols`
仍可检查。任务范围中的已删除或重命名路径若与当前 Git 变更一致，会被识别为任务
目标；current 知识卡引用的删除/重命名仍必须审核。退出码 `0` 表示没有检测到阻断
候选，`1` 表示需要处理，`2` 表示参数、Git 或读取失败。

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

一张卡片应表达一个稳定结论，并带上结构化仓库范围、证据、置信度和来源任务。旧 `paths` / `symbols` 可继续读取，新卡优先写 `scopes`。`verified` 必须有验证依据；决策必须有背景、理由、主要替代方案和后果。创建前还必须同时满足：

- `verified` 只接受实现、测试、契约或兼容证据；只有明确权威接受、尚未由行为验证的决定用 `accepted-decision` 证据和 `accepted` 置信度；

- 至少能写出两个具体的未来复用场景；
- 已由最终实现、测试、生产兼容证据或用户明确接受的权威约束确认；
- 表达稳定约束、边界、接口语义、事务保证、兼容规则或已接受决策；
- 不是单次报错的处理过程，也不是仅为当前测试库存在的偶发脏数据细节；
- 当前 Wiki 不存在含义相同的卡片；能更新或复用时不新建；
- 不会在同一连续调试链的下一轮立即被取代。

实现已有决策只复用原卡并在确有影响时记录使用证据，不能创建“已经实现该
决策”的同义卡。当前实现的逐文件摘要、临时库参数、单次测试夹具细节和
没有未来消费者的整理只进入任务记录。新增正交长期约束时新建卡，但不把
原决策列入 `supersedes`。

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

既有重复记录的整理必须采用显式 `consolidate`，不能删除历史或手改 Wiki：选择一条 canonical task-note，提供 canonical 与重复记录的 revision 和整理理由，先 dry-run 再用 token apply。工具把卡片关系汇总到 canonical，重复 note 保留来源、验证、原正文哈希与 canonical 指针，并标记为 archived；默认 brief、recent tasks 和根索引只展示 canonical，机器索引和文件仍保留完整关系。整理写入使用与 learn 相同的锁、状态绑定、恢复日志、回滚和幂等重试。卡片仅在结论确实变化时使用 `supersedes`；完全相同卡片复用原 ID。整理后运行 `doctor`。

历史卡片被 brief 返回、被读取、编号出现在回复中、最终代码碰巧一致或词语相似，都只是“看过”或自动关联，不得宣称知识发挥了作用。确有影响时，`task.knowledge_use` 的每一项必须记录：卡片 ID、实际读取的 `card_revision`、使用类型、对设计/范围/实现/测试/评审的具体影响，以及一项或多项结构化证据。每项证据包含 `kind`、可核查的 `artifact`、观察到的 `result` 和它与卡片结论的 `supports` 对应关系。新增或修改一项使用证据时，如果卡片 revision 已变化，必须重新运行 `brief` 并复核，不能沿用旧回执。已经写入 task-note 的历史使用证据必须保留其当时 revision；继续同一任务时不得把旧 revision 机械改成当前 revision。

`reviewed` 必须写明审查对象和具体结论；`changed-design` 必须保存可公开的
修改前方案与最终方案，不保存内部推理；`tested` 必须指向测试标识及所验证
不变量；`implemented` 必须指向实现位置或公开设计产物。证据类型必须与
声明的使用类型匹配。没有实际影响时 `knowledge_use` 必须为空，不能事后
根据 diff 编造影响。

## 8. 显式命令

| 请求 | 行为 |
|---|---|
| `$cs init` | 安装 Wiki runtime，运行 doctor |
| `$cs upgrade` | 结构升级后逐页审计旧知识，对照实现/测试与 current Wiki，只补缺失卡片；保留并隔离旧页，再运行 doctor |
| `$cs brief <任务>` | 只生成当前知识简报；可按主题和多仓库范围检索，不执行实现、不写文件 |
| `$cs status` | 运行 `cs_knowledge.py status` |
| `$cs doctor` | 先用当前 Skill 的 bootstrap `--check` 比较项目运行程序，再执行项目内只读完整性检查 |
| `$cs doctor --check-current-references` | 在结构检查之外，只读检查 current path/symbol 引用 |
| `$cs drift [--cached|--base <ref>|--references-only]` | 只读检查 current 引用、Git 变更与知识回写完整性 |
| `$cs audit [--cached|--base <ref>]` | 统一只读验收结构、当前引用、治理质量、生成资产和工作区/暂存/分支 Git 知识回写；明确不验证业务真相 |
| `$cs topics list` | 只读列出已配置的规范主题名、别名和当前覆盖，不读取卡片正文 |
| `$cs topics suggest` | 只读生成基于标签和范围前缀的可复现主题候选 |
| `$cs topics update` | 人工审核后的主题配置和卡片赋值批量更新；必须 dry-run + token apply |
| `$cs consolidate` | 事务化折叠重复 task-note，保留历史并从默认检索隐藏重复记录 |
| `$cs reindex` | 显式重建机器与 Markdown 索引 |
| `$cs template [--card-category <category>]` | 默认生成 task-only 紧凑模板；确认有长期结论时按分类添加卡片模板 |
| `$cs template --task-id <T-...>` | 从当前 task-note 生成带 revision 和历史 provenance 的更新快照；空的机械字段不输出 |
| `$cs <开发请求>` | 先 brief，同一次调用中正常完成任务，再 learn + doctor |

用户明确要求“只分析、不要写文件”时，遵守只读边界：可以运行 bootstrap `--check`、`brief / status / doctor / audit / drift / topics list / topics suggest / reindex --dry-run`，但不得运行 bootstrap 初始化或升级、`learn / consolidate / topics update / reindex apply`。可在回答中给出建议沉淀项，但不能暗示已经写入。

普通 `doctor` 只证明 Wiki 结构、链接、索引和事务记录一致，并非阻断地提醒旧 `AGENTS.md` 入口和空分类摘要；通过不代表 current 知识仍与源码一致，也不代表实现符合需求。完成 `learn` 后检查返回的 `reference_check`，需要全库引用检查时显式使用 `doctor --check-current-references` 或 `drift --references-only`，需要 Git/task-note 检查时使用 `drift`。

`audit` 汇总结构、current 引用、主题与证据治理、摘要新鲜度、生成 Markdown/发布资产和 Git 回写状态。每段使用 `pass / needs-attention / incomplete / not-applicable`，发现结构损坏、当前引用问题、治理未完成或交付检查缺失时退出码为 1。它始终输出 `business_truth: not-evaluated`：绿色结果也不能替代任务自己的需求验收和测试。

## 9. 最终回复

完成开发请求时，除了实现和验证结果，还应简短说明：

- 本次读取了哪些关键项目知识；
- 新建或复用了哪些知识卡片；
- 是否取代了旧知识；
- 若没有长期卡片，说明只写入了任务记录以及为什么没有可复用结论。
