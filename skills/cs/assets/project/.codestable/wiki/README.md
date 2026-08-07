# CodeStable Project Wiki

这里是项目的长期知识层。它服务于任何 Agent（Codex、Claude、Gemini 或其他实现 Agent），但不替代源码、测试和当前用户要求。

## 工作方式

1. 任务开始前，运行只读 `brief`，按任务文本、路径和符号检索相关知识。
2. Agent 正常分析、实现和验证，不由 CodeStable 编排 feature / issue / refactor 流程。
3. 按逻辑任务运行 `learn`：同一用户目标、主要交付物和连续调试链只维护一条任务记录；只有最终验收完成后，才把具有未来复用价值且有证据的事实写成知识卡片。
4. 新事实取代旧事实时，通过 `supersedes` 保留历史并让默认检索只返回当前知识。
5. 提交前运行只读 `drift --cached`；Git 工具不会自动替代 CodeStable 回写。

## 知识分区

| 分区 | 内容 |
|---|---|
| [需求](requirements/INDEX.md) | 稳定目标、约束、业务规则和非目标 |
| [架构](architecture/INDEX.md) | 组件职责、依赖方向、关键数据流和系统边界 |
| [接口](interfaces/INDEX.md) | API、事件、协议、调用约定和失败语义 |
| [数据模型](data-model/INDEX.md) | 实体、字段、状态、约束、序列化和迁移语义 |
| [异常处理](error-handling/INDEX.md) | 错误分类、传播、重试、降级和可观测性 |
| [事务边界](transaction-boundaries/INDEX.md) | 原子性、提交点、补偿、一致性和并发边界 |
| [兼容性](compatibility/INDEX.md) | 公共/持久化兼容、版本、迁移和回滚约束 |
| [性能风险](performance-risks/INDEX.md) | 热点、复杂度、容量、延迟和资源风险 |
| [安全边界](security-boundaries/INDEX.md) | 信任边界、权限、敏感数据和滥用防护 |
| [验收标准](acceptance/INDEX.md) | 可观察的完成条件、测试矩阵和验证入口 |
| [历史决策](decisions/INDEX.md) | 已接受的技术/产品决策、理由、后果和替代方案 |

任务记录位于 `task-notes/`，机器索引位于 `index.jsonl`。分类 `INDEX.md` 由工具生成；分类 `README.md` 和 `PROJECT.md` 可人工维护。

连续调试期间默认延迟写入。必须交接时可以用空 `items` 创建
`in-progress`、`partial` 或 `blocked` task-note；继续处理时使用返回的
task ID、`update_existing: true` 和当前 revision 更新原记录，不按报错或
补丁新建记录。强候选会阻止误建，除非显式说明独立目标。只有
`completed` task 可以携带知识卡片；partial knowledge-migration 可沉淀
已经逐项验证的结论，但必须让 pending 页面和总升级状态保持未完成。

存量重复记录通过 `consolidate` 折叠到一条 canonical task-note。重复文件
不会删除，而是保留审计指针、来源、验证和卡片关系；默认 brief、recent
tasks 和根索引不再展示 archived 重复记录。

completed task 还应在 `knowledge_summary` 中说明新增、复用或 supersede
哪些卡片；没有长期卡片时写明原因。普通 `doctor` 只验证 Wiki 结构，
不代表 current 知识仍与源码一致。使用 `drift` 检查 current 引用、Git
删除/重命名和 task-note 覆盖；其结果只是需要人工审核的候选。
`knowledge_use` 只记录历史卡片确实改变设计、实现、测试或 review 的强
证据；被检索或读取本身不算使用。
