# 架构 · Index

组件职责、依赖方向、关键数据流与系统边界

## 当前知识

- [任务记录使用代表性范围并保留知识使用历史版本](k-20260828-121106-01-2efd8007-任务记录使用代表性范围并保留知识使用历史版本.md) · verified
  - task-note 是逻辑任务的追踪记录，不是 Git 变更清单。提交漂移检查只要求至少一个代表性 self scope、路径或变更符号与语义改动直接重合；Git 已确认的任务删除或重命名路径是有效任务范围，但 current 卡片引用这些路径时仍需审核。已经写入 task-note 的 knowledge_use 永久保留当时实际读取的卡片 revision，卡片后续升级不会迫使旧证据改写；新的影响必须用当前 revision 追加。
- [brief 优先 current Wiki 并回退独立 legacy 线索](k-20260729-110404-02-edda6d3a-brief-优先-current-wiki-并回退独立-legacy-线索.md) · verified
  - brief 将 current Wiki、task-note 和 legacy 页面分池检索；knowledge 只返回 current Wiki 来源，只有没有合格 current 命中时才在 legacy_clues 中返回最多三条需复核的旧页线索，coverage 和 gaps 只依据 current 状态知识。
- [重复 task-note 通过 canonical 关系归档](k-20260807-151302-01-eaae81a6-重复-task-note-通过-canonical-关系归档.md) · verified
  - CodeStable 用显式事务化 consolidate 将重复 task-note 归档到一条 canonical 记录；归档文件保留审计关系，但默认 brief、recent tasks 和根索引只展示 canonical。
- [升级采用原地结构更新与逐页知识核对](k-20260819-144342-01-706c2a67-升级采用原地结构更新与逐页知识核对.md) · verified
  - 升级程序只对发行清单拥有的文件执行原地更新或退役，不创建自动备份目录。旧知识页继续保留在原路径，迁移清单记录路径、SHA-256 摘要和字节数，随后由知识整理流程逐页对照代码、测试和当前 Wiki 更新结论。
- [外部项目复用 Skill 的共享知识工具](k-20260819-130200-01-ee57213d-外部项目复用-skill-的共享知识工具.md) · verified
  - 知识工具由 Skill 在 skills/cs/scripts/cs_knowledge.py 提供，外部项目只保存自身的数据、配置和 Wiki，并通过 --root 指向项目根目录调用共享工具。

## 提议知识

- 无

已弃用和被取代的卡片见 [历史索引](../HISTORY.md#架构)。

本页由 `cs_knowledge.py reindex` 或 `learn` 生成；人工摘要请维护在 [README.md](README.md)。
