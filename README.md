# CodeStable Compact 2.0.0

CodeStable Compact 现在只做一件事：**把项目知识放到每次 Agent 工作的前后。**

它不再把任务拆成 feature、issue、refactor、roadmap、model 等 Skill，也不再维护交付阶段、风险等级、evidence gate、observability、Meta 或 evolution 控制面。发布包只保留一个 `$cs` Skill；所有项目复用 Skill 内的共享知识工具，项目自身只保存配置和知识数据。

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

卡片优先使用由仓库名、仓库内路径和符号组成的稳定范围。`paths` 和 `symbols` 可作为单仓库范围的简写。未配置的相关仓库只报告“无法验证”，不会误报为文件不存在。

## 安装

将 `skills/cs` 安装到 Agent 的 Skill 搜索目录。项目首次使用时：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project
```

已有知识库需要完全重建时，使用 `$cs rebuild`。重建会替换目标项目的整个
`.codestable`，不迁移旧配置、卡片、任务记录或旧目录；代码和其他项目文件不变。
先只读预览，再用相同计划执行：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project --rebuild --dry-run
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project --rebuild --plan-token '<预览返回的 plan_token>'
```

目录创建后，Agent 从当前代码、测试和已确认需求重新填写项目总览、分类摘要和知识卡片，
并写入一条重建任务记录。只有知识写入、引用检查和代表性查询都验证完成后，才报告
知识库重建完成。空目录不是完成结果。详情见 [完整重建](docs/rebuild.md)。

旧格式不再兼容，旧 `$cs upgrade` 和旧页面检索已移除。普通任务发现旧库只提示
需要重建，不自动清理。用户已授权重建时直接执行，不重复确认。

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
$cs rebuild
$cs brief <任务>
$cs status
$cs doctor
$cs audit
$cs topics list
$cs topics suggest
$cs drift --cached
$cs task-files --task-id T-...
$cs consolidate
$cs reindex
```

`$cs brief`、`status`、`doctor`、`audit`、`drift`、`task-files`、`topics list`、`topics suggest` 和 `reindex --dry-run` 是只读操作。用户明确要求“不写文件”时，Skill 不会执行 bootstrap 初始化或重建、learn、topics update 或 reindex apply。

在调用共享知识工具前，当前 Skill 会先执行只读数据格式预检：

```bash
python3 skills/cs/scripts/bootstrap.py --root /path/to/project --check
```

它验证项目的数据模式和结构能否由当前 Skill 读取，并检查共享工具是否实现命令表。
项目记录的发行版本或受管资产存在差异时只提供信息；旧格式要求重建，
而且不会自动修改项目。

## 直接使用 CLI

### 任务前：生成知识简报

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project brief \
  --task '修复库存不足时订单仍被提交的问题' \
  --path src/orders/service.py \
  --symbol OrderService.create \
  --scope 'shared-contracts:events/order.py#OrderCreated'
```

输出是面向 Agent 的 Markdown 简报，包含：

- 项目级总览；
- 单独限量展示、不占卡片配额的相关分类摘要；
- 与当前任务匹配的知识卡片；
- 相关历史任务与最近决策；
- 只基于 current Wiki 计算的 11 类知识覆盖；
- 本任务可能相关但尚未沉淀的知识空白；
- 可能冲突的当前卡片。

结果带机器可读 `match_reasons`。精确范围、路径和符号先于路径层级、主题和普通文本。`receipt` 绑定被展示卡片的 revision 与内容哈希，但只证明“展示过”，不证明卡片改变了工作。

主题只是辅助提示。Agent 不应猜测主题名：不确定时省略 `--topic`，或先运行 `topics list`。未知主题会被忽略并产生警告及近似名称建议，路径、符号、仓库范围和任务文本仍会继续参与检索；卡片写入与主题更新仍严格拒绝未知主题。

机器消费可加：

```bash
--format json
```

JSON 中 `knowledge` 只包含当前卡片，`proposed_knowledge` 和 `history` 独立
展示。查询只读取当前格式知识库，不扫描旧结构。

### 任务后：沉淀知识

生成一个必须替换所有 `__REPLACE__` 占位符的紧凑任务模板。默认 `items` 为空，
不会因为任务看起来复杂就预设它需要长期知识卡片：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project template \
  --title '库存不足时回滚订单创建' \
  --kind issue \
  --output /tmp/cs-learning.json
```

确认任务产生新的稳定结论后，再按知识分类添加卡片模板；参数可以重复：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project template \
  --title '库存不足时回滚订单创建' \
  --card-category transaction-boundaries \
  --card-category acceptance \
  --output /tmp/cs-learning.json
```

卡片会继承 task 的范围、主题和标签，只有边界更窄时才需要在 item 中重复填写。
默认值、空数组、编号、时间、哈希和索引由工具生成；请求、实际结果、验证、知识处置、
卡片证据和未来复用场景仍由 Agent 明确判断和填写。CodeStable 不按“小、中、大”
任务分级，所有任务保持相同的读取、校验、写入和漂移检查门槛。

先只校验写入计划：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project learn \
  --file /tmp/cs-learning.json \
  --dry-run
```

dry-run 返回完整写入计划和 `plan_token`。使用该 token 应用同一组 ID、路径、时间戳、前置知识状态和工作区状态：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project learn \
  --file /tmp/cs-learning.json \
  --plan-token '<dry-run 返回的 plan_token>'

python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project doctor
```

`learn` 默认返回紧凑 JSON，仍完整返回计划令牌、写入计划、任务与卡片候选、冲突、
警告、需要处理和无法验证的引用及计数，只省略完整的已验证引用列表。需要逐项查看
全部诊断时显式添加 `--full`；旧 `--compact` 作为默认行为的兼容别名保留。如果 dry-run 后工作区或知识状态发生变化，apply 会拒绝
旧 token，要求重新 dry-run。完全相同的 payload 再次提交不会重复写入。新知识取代
旧知识时，在新 item 中填写：

```json
{
  "supersedes": ["K-20260717-103000-01-ab12cd34"],
  "supersession_reason": "旧结论的事务保证已被新结论替换。"
}
```

旧卡片会保留，但状态改为 `superseded`，默认简报不再返回它。

连续任务应优先延迟到最终验收后一次性 `learn`。必须中断时，可先写
`in-progress`/`partial` task-note，但 `items` 必须为空。首次 apply 返回
`task_id` 与 `task_revision`；继续时先从当前记录生成完整更新快照：

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project template \
  --task-id 'T-...' \
  --output /tmp/cs-learning.json
```

模板会预填当前 revision、正文、范围、来源和历史知识使用证据。修改实际变化字段后，
保持以下更新控制字段：

```json
{"id": "T-...", "update_existing": true, "expected_revision": 1}
```

更新保留 task ID、路径、创建时间、关联 provenance 及其当时读取的卡片 revision，
只替换紧凑正文并递增 revision。卡片后来升级不会迫使旧使用证据改写；新的使用影响
必须重新 brief 后追加。dry-run 的 `task_candidates` 与 `card_candidates` 会提示可能
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
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project audit --cached --format json
```

它分别报告结构、当前引用、内容治理和版本化交付，并始终声明业务结论真实性未自动判断。主题通过 `disabled / manual / required` 显式配置；候选先用 `topics suggest` 只读生成，人工调整后再经 `topics update --dry-run` 和计划令牌应用。

### 提交前：只读漂移检查

```bash
# 工作区（含未跟踪文件）
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project drift

# staged / pre-commit
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project drift --cached

# CI
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project drift --base origin/main --format json

# 不读取 Git，只检查 current 引用
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project drift --references-only
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
python3 /path/to/codestable-compact/skills/cs/scripts/cs_knowledge.py \
  --root /path/to/project doctor --check-current-references
```

可选的最小项目规则位于 `skills/cs/templates/AGENTS.codestable.md`。它只供
人工选取；bootstrap 不会覆盖或自动合并项目已有 `AGENTS.md`。

## 项目内结构

```text
.codestable/
├── README.md                   # 目录用途与共享工具入口
├── config.json
├── manifest.json
├── VERSION
├── cache/
│   ├── .gitignore              # 排除派生文件
│   └── wiki/                   # 本地动态目录与 index.jsonl，可重建
└── wiki/
    ├── README.md
    ├── PROJECT.md              # 项目总览
    ├── INDEX.md                # 稳定入口
    ├── TOPICS.md               # 稳定主题入口
    ├── HISTORY.md              # 稳定历史入口
    ├── learning.schema.json
    ├── task-notes/YYYY/*.md     # 一项逻辑任务一条记录
    └── <11 个知识分类>/
        ├── README.md           # 人工摘要
        ├── INDEX.md            # 稳定分类入口
        └── k-*.md              # 一条结论一张卡片，包含状态和来源
```

当前格式使用 `wiki.index_storage: local`。卡片和任务记录进入 Git；
动态目录与机器索引保存在本地缓存。缓存缺失时 `brief`、`doctor` 和提交检查仍可用，
`reindex` 显式重建缓存。旧格式必须完整重建，不再提供版本化索引模式。

`drift --cached`、`audit --cached` 从 Git 暂存区读取配置、正文和源码，在内存中
构建检查视图。`--base` 读取 HEAD，其他工作区修改不会混入。检查不创建临时检出、
不改 Git 状态；未提交的完成记录不能掩盖待提交内容的问题。审计区分已有治理问题与新增问题。

提供路径、符号、仓库范围或有效主题时，`brief` 默认聚焦这些范围；没有命中会明确
留下空白。需要跨范围文本探索时使用 `--broad`。新卡片只在文件头保存一次结构化
范围、证据和来源，正文省略空章节；重建从当前代码和测试生成知识，不导入旧记录。

目录存储和验证细节见 [存储与提交隔离](docs/storage.md)。

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
- [完整重建](docs/rebuild.md)
- [完整示例](docs/examples.md)
