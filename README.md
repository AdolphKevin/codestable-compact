# CodeStable Compact 1.2.0

CodeStable Compact 现在只做一件事：**把项目知识放到每次 Agent 工作的前后。**

它不再把任务拆成 feature、issue、refactor、roadmap、model 等 Skill，也不再维护交付阶段、风险等级、evidence gate、observability、Meta 或 evolution 控制面。发布包只保留一个 `$cs` Skill 和一个项目内知识工具。

```text
任务开始
  → 按任务 / 路径 / 符号读取项目 Wiki
  → Agent 正常分析、实现、测试
  → 写入任务记录
  → 把长期结论沉淀为知识卡片
```

## 它沉淀什么

Wiki 固定包含 11 类项目知识：

- 需求
- 架构
- 接口
- 数据模型
- 异常处理
- 事务边界
- 兼容性
- 性能风险
- 安全边界
- 验收标准
- 决策

每张知识卡片是一条经最终验收、可供未来任务复用的事实、约束或决策。11 类仍用于覆盖检查；业务主题页只跨分类组织当前卡片的链接，不复制结论。`.codestable/wiki/INDEX.md` 是唯一当前入口，`TOPICS.md` 提供主题导航，`HISTORY.md` 保留被取代、弃用和归档记录。

卡片优先使用由仓库名、仓库内路径和符号组成的稳定范围。旧 `paths` 和 `symbols` 仍可读取。未配置的相关仓库只报告“无法验证”，不会误报为文件不存在。

## 安装

将 `skills/cs` 安装到 Agent 的 Skill 搜索目录。项目首次使用时：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project
```

从 CodeStable 0.x 控制面升级：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project \
  --upgrade
```

`bootstrap.py --upgrade` 是 `$cs upgrade` 的结构阶段。它会：

- 备份被替换的 config、工具和已知退役工具；
- 安装新的 `cs_knowledge.py`；
- 保留项目自建 Wiki；
- 逐页列出并备份旧 `.codestable/model`、`.codestable/knowledge` Markdown，但不自动转卡、删除或作为普通任务入口；
- 保留 `.codestable/work`、observations、fixtures 等其他项目数据；
- 删除项目副本中的已知旧控制面工具，但备份中仍可恢复。

升级结果通过 `layout` 区分当前运行结构、已审计历史入口，以及因兼容或项目所有权而保留但普通任务不应读取的数据。它还会检查 `AGENTS.md` 中缺失、退役或互相冲突的知识入口，只给出修复建议，不自动改写该文件。

完整的 `$cs upgrade` 随后必须逐页处理
`knowledge_migration.pages`：审计旧页，对照当前实现与测试，检查 current
Wiki 是否已覆盖，只为真正缺失且已确认的长期事实建卡；整个 upgrade
只维护一条 `knowledge-migration` task-note，其中保留逐页审计账本。learn、
doctor、源哈希和备份校验全部成功后，审计账本才可标记完成。兼容升级
仍保留原页；普通任务默认不会读取。证据不足的页标记为 `pending`，整个
升级报告为未完成。禁止把旧页批量照抄成新卡片。

## 日常使用

在支持 `$skill` 的宿主中：

```text
$cs 修复库存不足时订单仍被提交的问题
$cs 增加订单导出接口
$cs 在不改变行为的前提下拆分支付模块
```

默认语义是：同一次调用中先读取知识，随后由 Agent 正常完成任务，最后沉淀任务记录与长期知识。

显式命令：

```text
$cs init
$cs upgrade
$cs brief <任务>
$cs status
$cs doctor
$cs audit
$cs topics suggest
$cs drift --cached
$cs consolidate
$cs reindex
```

`$cs brief`、`status`、`doctor`、`audit`、`drift`、`topics suggest` 和 `reindex --dry-run` 是只读操作。用户明确要求“不写文件”时，Skill 不会执行 bootstrap、learn、topics update 或 reindex apply。

## 直接使用 CLI

### 任务前：生成知识简报

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '修复库存不足时订单仍被提交的问题' \
  --path src/orders/service.py \
  --symbol OrderService.create \
  --topic order-lifecycle \
  --scope 'shared-contracts:events/order.py#OrderCreated'
```

输出是面向 Agent 的 Markdown 简报，包含：

- 项目级总览；
- 单独限量展示、不占卡片配额的相关分类摘要；
- 与当前任务匹配的知识卡片；
- 明确要求 `--include-legacy` 时单独列出的旧结构线索；
- 相关历史任务与最近决策；
- 只基于 current Wiki 计算的 11 类知识覆盖；
- 本任务可能相关但尚未沉淀的知识空白；
- 可能冲突的当前卡片。

结果带机器可读 `match_reasons`。精确范围、路径和符号先于路径层级、主题和普通文本。`receipt` 绑定被展示卡片的 revision 与内容哈希，但只证明“展示过”，不证明卡片改变了工作。

机器消费可加：

```bash
--format json
```

JSON 中 `knowledge` 只包含当前卡片，`proposed_knowledge` 和 `history` 独立
展示。旧结构默认不读取；显式 `--include-legacy` 后只读结果位于
`legacy_clues`，不会增加当前覆盖或消除知识空白。

### 任务后：沉淀知识

生成一个必须替换所有 `__REPLACE__` 占位符的模板：

```bash
python3 .codestable/tools/cs_knowledge.py template \
  --title '库存不足时回滚订单创建' \
  --kind issue \
  --output /tmp/cs-learning.json
```

先只校验写入计划：

```bash
python3 .codestable/tools/cs_knowledge.py learn \
  --file /tmp/cs-learning.json \
  --dry-run
```

dry-run 返回完整写入计划和 `plan_token`。使用该 token 应用同一组 ID、路径、时间戳、前置知识状态和工作区状态：

```bash
python3 .codestable/tools/cs_knowledge.py learn \
  --file /tmp/cs-learning.json \
  --plan-token '<dry-run 返回的 plan_token>'

python3 .codestable/tools/cs_knowledge.py doctor
```

如果 dry-run 后工作区或知识状态发生变化，apply 会拒绝旧 token，要求重新 dry-run。完全相同的 payload 再次提交不会重复写入。新知识取代旧知识时，在新 item 中填写：

```json
{
  "supersedes": ["K-20260717-103000-01-ab12cd34"],
  "supersession_reason": "旧结论的事务保证已被新结论替换。"
}
```

旧卡片会保留，但状态改为 `superseded`，默认简报不再返回它。

连续任务应优先延迟到最终验收后一次性 `learn`。必须中断时，可先写
`in-progress`/`partial` task-note，但 `items` 必须为空。首次 apply 返回
`task_id` 与 `task_revision`；继续时提交完整最新快照，并设置：

```json
{"id": "T-...", "update_existing": true, "expected_revision": 1}
```

更新保留 task ID、路径、创建时间和关联 provenance，只替换紧凑正文并
递增 revision。dry-run 的 `task_candidates` 与 `card_candidates` 会提示可能
应更新或合并的既有记录，不会自动模糊合并。强 task candidate 会阻止
新建 token，除非改为 update 或明确填写独立目标理由。

存量重复 task-note 使用事务化 `consolidate` 整理：先提交 canonical ID、
重复 ID、各自 revision 和理由进行 dry-run，再用 token apply。工具不删除
历史；重复记录变为指向 canonical 的 archived 审计记录，仍保留来源、
验证、卡片关系和原正文哈希，但不再进入默认 brief、recent tasks 和根索引。

历史卡片只有在明确改变设计、范围、实现、测试或评审结论，并能指出可
核查产物及其与卡片结论的对应关系时，才应通过 `task.knowledge_use` 记录
使用证据；记录必须包含卡片 revision。仅被 brief 返回、读取、引用编号、与最终代码相似，或事后补写
引用都不代表知识实际发挥了作用。

统一只读验收：

```bash
python3 .codestable/tools/cs_knowledge.py audit --cached --format json
```

它分别报告结构、当前引用、内容治理和版本化交付，并始终声明业务结论真实性未自动判断。主题通过 `disabled / manual / required` 显式配置；候选先用 `topics suggest` 只读生成，人工调整后再经 `topics update --dry-run` 和计划令牌应用。

### 提交前：只读漂移检查

```bash
# 工作区（含未跟踪文件）
python3 .codestable/tools/cs_knowledge.py drift

# staged / pre-commit
python3 .codestable/tools/cs_knowledge.py drift --cached

# CI
python3 .codestable/tools/cs_knowledge.py drift --base origin/main --format json

# 不读取 Git，只检查 current 引用
python3 .codestable/tools/cs_knowledge.py drift --references-only
```

退出码为 `0`（无候选）、`1`（需要处理）和 `2`（命令或输入错误）。
`drift` 检查当前卡的仓库范围、保守符号文本信号、删除/重命名，以及
语义变更是否有 completed task-note、最终结果、验证、范围覆盖和知识处置。
它不自动判断知识真假、不修改卡片，也不要求每次创建知识卡。

引用结果区分确认缺失、可能重命名、外部仓库未配置、符号文本扫描未命中
和历史卡片跳过。符号文本未命中始终只是待复核信号。

普通 `doctor` 仍只检查结构，并在 JSON 中声明
`current_knowledge_validated: false`。如需组合引用检查：

```bash
python3 .codestable/tools/cs_knowledge.py doctor --check-current-references
```

可选的最小项目规则位于 `skills/cs/templates/AGENTS.codestable.md`。它只供
人工选取；bootstrap 不会覆盖或自动合并项目已有 `AGENTS.md`。

## 项目内结构

```text
.codestable/
├── config.json
├── manifest.json
├── VERSION
├── tools/
│   └── cs_knowledge.py
└── wiki/
    ├── README.md
    ├── PROJECT.md
    ├── INDEX.md                 # 生成
    ├── TOPICS.md                # 生成，只链接当前卡片
    ├── HISTORY.md               # 生成，历史卡片与归档任务
    ├── index.jsonl              # 生成
    ├── learning.schema.json
    ├── task-notes/YYYY/*.md
    ├── requirements/
    ├── architecture/
    ├── interfaces/
    ├── data-model/
    ├── error-handling/
    ├── transaction-boundaries/
    ├── compatibility/
    ├── performance-risks/
    ├── security-boundaries/
    ├── acceptance/
    └── decisions/
```

每个分类中的 `README.md` 是可人工维护的当前摘要，`INDEX.md` 只突出当前和
提议知识。摘要长期为空时 `doctor` 给出非阻断提醒；`TOPICS.md` 可承担中层
导航，但知识卡片仍是结论正文的唯一来源。

## 知识质量原则

沉淀当前、可验证、会影响未来实现的内容。不要沉淀原始聊天、完整日志、完整 diff、临时排查过程、泛化常识、未验证猜测、密钥或个人数据。

新卡片必须没有等义的当前卡、预计影响多个未来任务、表达稳定边界或已接受
决策，并有明确范围和最终证据。决策还要记录背景、理由、主要替代方案和
后果。一次性报错、调试命令、逐文件实现摘要、临时调优值和已有结论的实现
记录只进入任务记录。

事实冲突时不静默覆盖：结论不变而范围变化时更新原卡并保留范围历史；
只有长期结论真正改变时才新建卡并用 `supersedes` 保留演进。正交约束新增
卡片但不取代原决策。

冲突判断必须区分目标与行为：accepted 的需求、约束和决策描述应该
实现的状态；verified 行为事实描述已经验证的状态。两者与当前实现不一致
时，应判断实现偏离、行为回归、scope 变化或知识过期，不能机械地选择
Wiki 或代码一方。

## 设计边界

CodeStable 不再：

- 路由开发任务类型；
- 创建工作阶段或 active work 状态机；
- 判定实现是否完成；
- 替代真实测试与代码 review；
- 记录 prompts、模型响应、diff 或 telemetry；
- 自动训练、评估或演化 Agent/Harness。

它只提供一个项目本地、版本可控、Agent 友好的 Markdown 知识层。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_release.py --source .
```

详见：

- [架构](docs/architecture.md)
- [知识格式](docs/knowledge-format.md)
- [漂移检查与 Git/CI 接入](docs/drift.md)
- [升级与迁移](docs/migration.md)
- [完整示例](docs/examples.md)
