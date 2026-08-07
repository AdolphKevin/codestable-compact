---
id: "K-20260807-151302-01-eaae81a6"
type: "knowledge-card"
category: "architecture"
title: "重复 task-note 通过 canonical 关系归档"
status: "current"
confidence: "verified"
created_at: "2026-08-07T15:13:02+08:00"
updated_at: "2026-08-07T15:13:02+08:00"
task_id: "T-20260807-151302-09b85bf6"
fingerprint: "eaae81a6168ea883c81b72495807bfc2bef9c706f0aeb3ce50f5be9837943774"
pinned: false
tags: ["task-note", "consolidation", "retrieval"]
paths: ["skills/cs/assets/project/.codestable/tools/cs_knowledge.py", "docs/knowledge-format.md", "tests/test_knowledge.py"]
symbols: ["consolidate", "render_root_index", "collect_search_documents"]
supersedes: []
superseded_by: []
---

# 重复 task-note 通过 canonical 关系归档

## 结论

CodeStable 用显式事务化 consolidate 将重复 task-note 归档到一条 canonical 记录；归档文件保留审计关系，但默认 brief、recent tasks 和根索引只展示 canonical。

## 背景与理由

历史可追溯与默认检索整洁是两个不同维度，不能通过删除历史或继续展示重复正文来二选一。

## 影响

- 强任务候选必须 update 或说明独立目标
- 机器索引保留 archived 记录及双向关系
- consolidate 使用 revision、plan token、锁和恢复日志

## 适用范围

- 路径：skills/cs/assets/project/.codestable/tools/cs_knowledge.py, docs/knowledge-format.md, tests/test_knowledge.py
- 符号：consolidate, render_root_index, collect_search_documents
- 标签：task-note, consolidation, retrieval

## 验证与依据

- consolidation idempotency, stale-plan, rollback and default-folding regression tests pass
- release validation passes

## 来源任务

- 任务：改进 task-note 聚合与 upgrade 知识迁移
- 任务记录：`T-20260807-151302-09b85bf6`
- 状态：completed
- 结果：连续调试默认复用原任务；一次 upgrade 只维护一条审计 task-note；重复历史可安全归档且不污染默认 brief/recent/root index；pending 页面、卡片来源和历史关系保持可追溯。

```json
{
  "feedback": "sanitized-maintainer-fixture"
}
```
