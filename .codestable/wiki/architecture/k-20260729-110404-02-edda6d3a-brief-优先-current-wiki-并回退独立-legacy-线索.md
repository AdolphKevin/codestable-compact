---
id: "K-20260729-110404-02-edda6d3a"
type: "knowledge-card"
category: "architecture"
title: "brief 优先 current Wiki 并回退独立 legacy 线索"
status: "current"
confidence: "verified"
created_at: "2026-07-29T11:04:04+08:00"
updated_at: "2026-08-19T14:50:05+08:00"
revision: 2
scope_history: [{"paths": ["skills/cs/assets/project/.codestable/tools/cs_knowledge.py", "tests/test_knowledge.py", "scripts/validate_release.py"], "revision": 1, "scopes": [], "symbols": ["score_document_details", "selected_brief_payload", "render_brief_markdown"], "task_id": "T-20260729-110404-be3fbd04", "topics": [], "updated_at": "2026-07-29T11:04:04+08:00"}]
task_id: "T-20260729-110404-be3fbd04"
fingerprint: "6a6c367ee17524c9c239753e94f05f7b98e4333357368f56d717130eec2b1287"
pinned: false
tags: ["brief", "retrieval", "legacy", "coverage"]
topics: []
scopes: [{"path": "skills/cs/runtime_src/40_retrieval.py", "repository": "self", "symbol": "score_document_details"}, {"path": "skills/cs/runtime_src/40_retrieval.py", "repository": "self", "symbol": "selected_brief_payload"}, {"path": "skills/cs/runtime_src/40_retrieval.py", "repository": "self", "symbol": "render_brief_markdown"}, {"path": "tests/test_knowledge.py", "repository": "self", "symbol": ""}, {"path": "scripts/validate_release.py", "repository": "self", "symbol": ""}]
paths: []
symbols: []
supersedes: []
superseded_by: []
future_use: [{"actor": "维护检索运行时的开发者", "change": "调整 brief 的 current 与 legacy 检索分层", "constraint": "legacy 只能作为独立线索，并且不得计入 current coverage 或 gaps"}, {"actor": "维护调用方和回归测试的开发者", "change": "修改 brief JSON 输出或覆盖率计算", "constraint": "knowledge 只包含 current Wiki；无合格 current 命中时 legacy_clues 最多返回三条"}]
evidence: [{"artifact": "skills/cs/runtime_src/40_retrieval.py", "kind": "implementation", "result": "共享运行时按 current Wiki、task-note 和 legacy 页面分池选择 brief 内容", "supports": "legacy 只作为没有合格 current 命中时的独立回退线索"}, {"artifact": "tests/test_knowledge.py", "kind": "test", "result": "检索回退、覆盖率和知识状态回归测试通过", "supports": "coverage 和 gaps 不会由 legacy 或非 current 知识填充"}]
updated_by_task_id: "T-20260819-144342-b2491cb9"
---

# brief 优先 current Wiki 并回退独立 legacy 线索

## 结论

brief 将 current Wiki、task-note 和 legacy 页面分池检索；knowledge 只返回 current Wiki 来源，只有没有合格 current 命中时才在 legacy_clues 中返回最多三条需复核的旧页线索，coverage 和 gaps 只依据 current 状态知识。

## 背景

未单独记录；参见来源任务。

## 理由

结构分层能防止低权威 legacy 页面凭词法分数污染当前知识，也避免旧页掩盖真实知识空白。

## 影响

- 分类提示只能参与排序，不能单独使文档入选。
- recent decision 必须相关或 pinned；implicit acceptance 只用于 gap 分析。
- JSON 消费方从 legacy_clues 读取旧页回退，不再从 knowledge 中读取 legacy-page。

## 主要替代方案

- 无

## 后果

- 无

## 未来复用场景

- 变更：调整 brief 的 current 与 legacy 检索分层；执行者：维护检索运行时的开发者；需复核约束：legacy 只能作为独立线索，并且不得计入 current coverage 或 gaps
- 变更：修改 brief JSON 输出或覆盖率计算；执行者：维护调用方和回归测试的开发者；需复核约束：knowledge 只包含 current Wiki；无合格 current 命中时 legacy_clues 最多返回三条

## 适用范围

- 结构化范围：
- 仓库 `self` · 路径 `skills/cs/runtime_src/40_retrieval.py` · 符号 `score_document_details`
- 仓库 `self` · 路径 `skills/cs/runtime_src/40_retrieval.py` · 符号 `selected_brief_payload`
- 仓库 `self` · 路径 `skills/cs/runtime_src/40_retrieval.py` · 符号 `render_brief_markdown`
- 仓库 `self` · 路径 `tests/test_knowledge.py` · 符号 `未限定`
- 仓库 `self` · 路径 `scripts/validate_release.py` · 符号 `未限定`
- 标签：brief, retrieval, legacy, coverage
- 主题：无

## 取代说明

未取代其他长期结论。

## 验证与依据

- implementation `skills/cs/runtime_src/40_retrieval.py`：共享运行时按 current Wiki、task-note 和 legacy 页面分池选择 brief 内容；支持：legacy 只作为没有合格 current 命中时的独立回退线索
- test `tests/test_knowledge.py`：检索回退、覆盖率和知识状态回归测试通过；支持：coverage 和 gaps 不会由 legacy 或非 current 知识填充

## 来源任务

- 任务：取消升级自动备份并改为原地逐项核对
- 任务记录：`T-20260819-144342-b2491cb9`
- 状态：completed
- 结果：全新安装和升级都不再创建自动备份；旧知识仍在原路径，当前知识引用均指向共享 Skill 运行时，完整测试、知识审计和发行校验通过。

```json
{
  "date": "2026-08-19",
  "kind": "user-request"
}
```
