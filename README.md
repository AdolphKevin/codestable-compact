# CodeStable Compact 1.0.0

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
- 历史决策

每张知识卡片是一条可复用的当前事实、约束或决策，带有适用路径、符号、标签、验证依据、置信度、来源任务和取代关系。每个实际处理过的任务还会保留一条紧凑 `task-note`；即使本次没有值得长期复用的结论，也能留下“处理了什么、结果如何、怎样验证”的历史。

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

升级会：

- 备份被替换的 config、工具和已知退役工具；
- 安装新的 `cs_knowledge.py`；
- 保留项目自建 Wiki；
- 保留旧 `.codestable/model`、`.codestable/knowledge`、`.codestable/work`、observations、fixtures 等数据；
- 让旧 model/knowledge 继续作为只读检索来源；
- 删除项目副本中的已知旧控制面工具，但备份中仍可恢复。

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
$cs reindex
```

`$cs brief`、`status`、`doctor` 和 `reindex --dry-run` 是只读操作。用户明确要求“不写文件”时，Skill 不会执行 bootstrap、learn 或 reindex。

## 直接使用 CLI

### 任务前：生成知识简报

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '修复库存不足时订单仍被提交的问题' \
  --path src/orders/service.py \
  --symbol OrderService.create
```

输出是面向 Agent 的 Markdown 简报，包含：

- 项目级总览；
- 与当前任务匹配的知识卡片；
- 相关历史任务与最近决策；
- 11 类知识覆盖；
- 本任务可能相关但尚未沉淀的知识空白；
- 可能冲突的当前卡片。

机器消费可加：

```bash
--format json
```

### 任务后：沉淀知识

生成一个合法模板：

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

dry-run 返回完整写入计划和 `plan_token`。使用该 token 应用同一组 ID、路径、时间戳和前置知识状态：

```bash
python3 .codestable/tools/cs_knowledge.py learn \
  --file /tmp/cs-learning.json \
  --plan-token '<dry-run 返回的 plan_token>'

python3 .codestable/tools/cs_knowledge.py doctor
```

如果 dry-run 后知识状态发生变化，apply 会拒绝旧 token，要求重新 dry-run。完全相同的 payload 再次提交不会重复写入。新知识取代旧知识时，在新 item 中填写：

```json
{
  "supersedes": ["K-20260717-103000-01-ab12cd34"]
}
```

旧卡片会保留，但状态改为 `superseded`，默认简报不再返回它。

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

每个分类中的 `README.md` 是可人工维护的当前摘要，`INDEX.md` 由工具生成，其他 Markdown 文件是结构化知识卡片。

## 知识质量原则

沉淀当前、可验证、会影响未来实现的内容。不要沉淀原始聊天、完整日志、完整 diff、临时排查过程、泛化常识、未验证猜测、密钥或个人数据。

事实冲突时不静默覆盖：保留历史，用 supersession 表达变化。`verified` 卡片必须有验证依据；决策卡片必须记录 rationale。

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
- [升级与迁移](docs/migration.md)
- [完整示例](docs/examples.md)
