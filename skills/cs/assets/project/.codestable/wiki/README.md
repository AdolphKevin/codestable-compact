# CodeStable Project Wiki

这里是项目的长期知识层。它服务于任何 Agent（Codex、Claude、Gemini 或其他实现 Agent），但不替代源码、测试和当前用户要求。

## 工作方式

1. 任务开始前，先由当前 Skill 运行只读 bootstrap `--check`，确认项目内运行程序未落后；再运行只读 `brief`，按任务文本、业务主题、仓库范围、路径和符号检索相关知识。
2. Agent 正常分析、实现和验证，不由 CodeStable 编排 feature / issue / refactor 流程。
3. 按逻辑任务运行 `learn`：同一用户目标、主要交付物和连续调试链只维护一条任务记录；只有最终验收完成后，才把具有未来复用价值且有证据的事实写成知识卡片。
4. 新事实取代旧事实时，通过 `supersedes` 保留历史并让默认检索只返回当前知识；结论不变而范围变化时更新原卡。
5. 提交前运行只读 `drift --cached`；Git 工具不会自动替代 CodeStable 回写。
6. 需要一次性验收结构、当前引用、治理质量和 Git 回写时，运行只读 `audit`。它明确不验证业务需求是否真的实现。

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
| [决策](decisions/INDEX.md) | 已接受或提议的技术/产品决策、理由、后果和替代方案 |

`.codestable/wiki/INDEX.md` 是唯一当前入口。[业务主题](TOPICS.md) 只组织
当前卡片的链接，[历史索引](HISTORY.md) 展示被取代、弃用和归档记录；卡片
正文始终是结论的唯一来源。任务记录位于 `task-notes/`，机器索引位于
`index.jsonl`。分类 `INDEX.md` 由工具生成；分类 `README.md` 和 `PROJECT.md`
可人工维护。分类有当前卡片但摘要长期为空时，`doctor` 会给出非阻断提醒。

本文件是 CodeStable 管理的通用使用说明，升级时会原位同步新版且不创建自动备份。项目总览、
分类 `README.md`、知识卡片、任务记录和未知文件属于项目，升级只保留且不会猜测
改写。根索引、分类索引、主题索引、历史索引和 `index.jsonl` 是可由 `reindex`
重建的生成文件。升级不会自动修改 `AGENTS.md`。

业务主题策略在配置中显式选择 `disabled`、`manual` 或 `required`。`topics suggest`
只根据标签和仓库内范围前缀产生可复现候选；它不会写文件，也不会把自由文本聚类
当作事实。批量更新必须经过人工调整、`topics update --dry-run` 和计划令牌应用。
主题别名和替换关系保留导航演进，卡片正文仍是唯一事实来源。

不要根据业务描述猜主题名。需要主题筛选时先用只读 `topics list` 查看规范名称和
别名；不确定时直接省略 `--topic`，优先依赖完整任务、路径、符号和仓库范围。未知
主题在 `brief` 中只产生警告和近似名称建议，不会中止其他检索；写入仍严格拒绝。

连续调试期间默认延迟写入。必须交接时可以用空 `items` 创建
`in-progress`、`partial` 或 `blocked` task-note；继续处理时使用返回的
task ID、`update_existing: true` 和当前 revision 更新原记录，不按报错或
补丁新建记录。优先用 `template --task-id` 从当前记录生成带 revision、范围、
来源和历史证据的更新快照，避免手工复制。强候选会阻止误建，除非显式说明独立目标。只有
`completed` task 可以携带知识卡片；partial knowledge-migration 可沉淀
已经逐项验证的结论，但必须让 pending 页面和总升级状态保持未完成。

存量重复记录通过 `consolidate` 折叠到一条 canonical task-note。重复文件
不会删除，而是保留审计指针、来源、验证和卡片关系；默认 brief、recent
tasks 和根索引不再展示 archived 重复记录。

completed task 还应在 `knowledge_summary` 中说明新增、复用或 supersede
哪些卡片；没有长期卡片时写明原因。普通 `doctor` 只验证 Wiki 结构，
不代表 current 知识仍与源码一致。使用 `drift` 检查 current 引用、Git
删除/重命名和 task-note 覆盖；其结果只是需要人工审核的候选。
task-note 只需用至少一个直接命中的代表性路径、结构化 self scope 或变更符号证明
与本次改动相关，不需要枚举完整 diff；Git 已确认的任务删除/重命名路径也是有效范围，
但 current 卡片引用这些路径时仍需审核。

模板和检查不按“小、中、大”任务分级。`template` 默认只生成紧凑 task，只有确认
产生新的稳定结论时才用可重复的 `--card-category` 增加对应分类卡片；卡片默认继承
task 的范围、主题和标签。`learn` 默认输出紧凑 JSON，保留计划令牌、写入计划、
候选、冲突、警告、无法验证引用和计数；只有需要逐项诊断已验证引用时才加 `--full`。
这种收敛只自动处理默认值和空字段，不代替 Agent 判断结论、证据、适用范围和未来
复用场景。

`knowledge_use` 只记录历史卡片确实改变设计、范围、实现、测试或评审结论
的证据。每项证据必须指向可核查产物，并说明观察结果如何支持卡片结论；
还必须绑定实际读取的卡片 revision。卡片后续升级时，已有任务证据继续保留当时
revision；只有新的使用影响才重新 brief 并追加当前 revision。`brief` 回执只证明卡片被展示；被检索、
读取、引用编号或与最终代码相似都不算使用。

项目内 `doctor` 会报告本地版本文件是否彼此一致；判断它是否落后于当前 Skill
必须从当前 Skill 运行 bootstrap `--check`。显式升级会验证共享运行工具，
并逐项确认 Skill 命令表中声明的命令真实可用。

新 current 卡片使用结构化证据：证据类型、产物、可核查结果和它支持的结论。
`verified` 必须有实现、测试、契约或兼容证据；明确被接受但尚无实现验证的决定使用
`accepted-decision` 证据和 `accepted` 置信度。每张长期卡至少写两个不同的未来
复用场景，分别说明什么变更、由谁执行、届时必须复核哪条约束。旧自由文本格式继续
可读，但 `audit` 会把它列为待治理项，不会在升级时自动编造结构化证据。
