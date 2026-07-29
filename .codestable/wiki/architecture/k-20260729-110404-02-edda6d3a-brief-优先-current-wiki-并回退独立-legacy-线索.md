---
id: "K-20260729-110404-02-edda6d3a"
type: "knowledge-card"
category: "architecture"
title: "brief 优先 current Wiki 并回退独立 legacy 线索"
status: "current"
confidence: "verified"
created_at: "2026-07-29T11:04:04+08:00"
updated_at: "2026-07-29T11:04:04+08:00"
task_id: "T-20260729-110404-be3fbd04"
fingerprint: "edda6d3ad1a5a0871d607513b689ce8b9b4181905480771bad2785d225923731"
pinned: false
tags: ["brief", "retrieval", "legacy", "coverage"]
paths: ["skills/cs/assets/project/.codestable/tools/cs_knowledge.py", "tests/test_knowledge.py", "scripts/validate_release.py"]
symbols: ["score_document_details", "selected_brief_payload", "render_brief_markdown"]
supersedes: []
superseded_by: []
---

# brief 优先 current Wiki 并回退独立 legacy 线索

## 结论

brief 将 current Wiki、task-note 和 legacy 页面分池检索；knowledge 只返回 current Wiki 来源，只有没有合格 current 命中时才在 legacy_clues 中返回最多三条需复核的旧页线索，coverage 和 gaps 只依据 current 状态知识。

## 背景与理由

结构分层能防止低权威 legacy 页面凭词法分数污染当前知识，也避免旧页掩盖真实知识空白。

## 影响

- 分类提示只能参与排序，不能单独使文档入选。
- recent decision 必须相关或 pinned；implicit acceptance 只用于 gap 分析。
- JSON 消费方从 legacy_clues 读取旧页回退，不再从 knowledge 中读取 legacy-page。

## 适用范围

- 路径：skills/cs/assets/project/.codestable/tools/cs_knowledge.py, tests/test_knowledge.py, scripts/validate_release.py
- 符号：score_document_details, selected_brief_payload, render_brief_markdown
- 标签：brief, retrieval, legacy, coverage

## 验证与依据

- 29 unit tests passed
- release validation passed including fresh install and legacy upgrade brief contracts

## 来源任务

- 任务：修正 cs 知识冲突与检索分层
- 任务记录：`T-20260729-110404-be3fbd04`
- 状态：completed
- 结果：cs Skill 明确区分 accepted 目标与 verified 行为；brief 只在没有合格 current 命中时返回独立 legacy 线索，legacy、proposed 和 deprecated 不再填补 current coverage，完整回归与发布校验通过。

```json
{}
```
