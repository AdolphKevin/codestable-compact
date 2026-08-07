---
id: "T-20260807-151302-09b85bf6"
type: "task-note"
title: "改进 task-note 聚合与 upgrade 知识迁移"
created_at: "2026-08-07T15:13:02+08:00"
updated_at: "2026-08-07T15:13:02+08:00"
task_status: "completed"
fingerprint: "09b85bf62b0f477432fb36a0b5c78e67ccb61e5166a2a0d81cc84c3ef57f24d4"
tags: ["task-note", "upgrade", "consolidation", "knowledge-lifecycle"]
paths: ["skills/cs/assets/project/.codestable/tools/cs_knowledge.py", "skills/cs/SKILL.md", "docs/migration.md", "docs/knowledge-format.md", "tests/test_knowledge.py"]
symbols: ["learn", "consolidate", "selected_brief_payload", "status_payload", "validate_knowledge_migration_source"]
card_ids: ["K-20260807-151302-01-eaae81a6", "K-20260807-151302-02-2608ee7f"]
---

# 改进 task-note 聚合与 upgrade 知识迁移

## 请求

定位并修复逻辑任务重复记录、upgrade 逐页 task-note 噪音、存量重复记录无法整理和知识使用证据误判。

## 处理摘要

确认规则、runtime 与发布文档存在能力断层；实现强候选新建保护、事务化 consolidate、聚合 upgrade 审计账本、默认历史折叠和可选强知识使用证据，并补齐脱敏回归。

## 最终结果

连续调试默认复用原任务；一次 upgrade 只维护一条审计 task-note；重复历史可安全归档且不污染默认 brief/recent/root index；pending 页面、卡片来源和历史关系保持可追溯。

## 验证

- python3 -m unittest discover -s tests -v (54 tests passed)
- python3 scripts/validate_release.py --source . (11 checks passed)
- python3 -m py_compile runtime/bootstrap/release validator
- git diff --check

## 变更范围

- 路径：skills/cs/assets/project/.codestable/tools/cs_knowledge.py, skills/cs/SKILL.md, docs/migration.md, docs/knowledge-format.md, tests/test_knowledge.py
- 符号：learn, consolidate, selected_brief_payload, status_payload, validate_knowledge_migration_source
- 标签：task-note, upgrade, consolidation, knowledge-lifecycle

## 沉淀的知识卡片

- `K-20260807-151302-01-eaae81a6`
- `K-20260807-151302-02-2608ee7f`

## 来源

```json
{
  "feedback": "sanitized-maintainer-fixture"
}
```
