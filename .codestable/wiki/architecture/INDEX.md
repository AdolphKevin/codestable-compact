# 架构 · Index

组件职责、依赖方向、关键数据流与系统边界

## 当前知识

- [重复 task-note 通过 canonical 关系归档](k-20260807-151302-01-eaae81a6-重复-task-note-通过-canonical-关系归档.md) · verified  
  CodeStable 用显式事务化 consolidate 将重复 task-note 归档到一条 canonical 记录；归档文件保留审计关系，但默认 brief、recent tasks 和根索引只展示 canonical。
- [brief 优先 current Wiki 并回退独立 legacy 线索](k-20260729-110404-02-edda6d3a-brief-优先-current-wiki-并回退独立-legacy-线索.md) · verified  
  brief 将 current Wiki、task-note 和 legacy 页面分池检索；knowledge 只返回 current Wiki 来源，只有没有合格 current 命中时才在 legacy_clues 中返回最多三条需复核的旧页线索，coverage 和 gaps 只依据 current 状态知识。
- [upgrade 分为结构阶段与逐页语义迁移](k-20260729-103956-01-1a0dad7b-upgrade-分为结构阶段与逐页语义迁移.md) · verified  
  CodeStable upgrade 包含两个不可合并的阶段：bootstrap 只负责 manifest 管理文件刷新、旧知识逐页清单和逐页备份；$cs Agent 随后逐页对照当前实现、可执行测试与 current Wiki 完成语义审计。

## 提议知识

- 无

## 已弃用

- 无

## 已被取代

- 无

本页由 `cs_knowledge.py reindex` 或 `learn` 生成；人工摘要请维护在 [README.md](README.md)。
