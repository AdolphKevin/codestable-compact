---
id: "K-20260807-151302-01-eaae81a6"
type: "knowledge-card"
category: "architecture"
title: "重复 task-note 通过 canonical 关系归档"
status: "current"
confidence: "verified"
created_at: "2026-08-07T15:13:02+08:00"
updated_at: "2026-08-19T14:50:05+08:00"
revision: 2
scope_history: [{"paths": ["skills/cs/assets/project/.codestable/tools/cs_knowledge.py", "docs/knowledge-format.md", "tests/test_knowledge.py"], "revision": 1, "scopes": [], "symbols": ["consolidate", "render_root_index", "collect_search_documents"], "task_id": "T-20260807-151302-09b85bf6", "topics": [], "updated_at": "2026-08-07T15:13:02+08:00"}]
task_id: "T-20260807-151302-09b85bf6"
fingerprint: "05887fb463a2bb6f317fb322264594bf5c10411c6df2a473f50a3e9cd6ac5135"
pinned: false
tags: ["task-note", "consolidation", "retrieval"]
topics: []
scopes: [{"path": "skills/cs/runtime_src/30_learning.py", "repository": "self", "symbol": "consolidate"}, {"path": "skills/cs/runtime_src/20_storage.py", "repository": "self", "symbol": "render_root_index"}, {"path": "skills/cs/runtime_src/40_retrieval.py", "repository": "self", "symbol": "collect_search_documents"}, {"path": "docs/knowledge-format.md", "repository": "self", "symbol": ""}, {"path": "tests/test_knowledge.py", "repository": "self", "symbol": ""}]
paths: []
symbols: []
supersedes: []
superseded_by: []
future_use: [{"actor": "维护知识写入运行时的开发者", "change": "调整重复任务记录的合并或归档行为", "constraint": "必须保留 canonical 与 archived 记录之间的双向审计关系"}, {"actor": "维护检索和索引的开发者", "change": "修改 brief、recent tasks 或根索引的可见性", "constraint": "默认视图只展示 canonical，机器索引仍保留 archived 记录"}]
evidence: [{"artifact": "skills/cs/runtime_src/30_learning.py", "kind": "implementation", "result": "共享运行时用事务、版本和计划令牌执行 consolidate", "supports": "重复 task-note 可归档到 canonical 且保留审计关系"}, {"artifact": "skills/cs/runtime_src/20_storage.py 与 skills/cs/runtime_src/40_retrieval.py", "kind": "implementation", "result": "根索引和默认检索折叠 archived 任务记录", "supports": "默认 brief、recent tasks 和根索引只展示 canonical"}, {"artifact": "tests/test_knowledge.py", "kind": "test", "result": "合并幂等、过期计划、回滚和默认折叠回归测试通过", "supports": "归档关系可恢复且不会污染默认检索结果"}]
updated_by_task_id: "T-20260819-144342-b2491cb9"
---

# 重复 task-note 通过 canonical 关系归档

## 结论

CodeStable 用显式事务化 consolidate 将重复 task-note 归档到一条 canonical 记录；归档文件保留审计关系，但默认 brief、recent tasks 和根索引只展示 canonical。

## 背景

未单独记录；参见来源任务。

## 理由

历史可追溯与默认检索整洁是两个不同维度，不能通过删除历史或继续展示重复正文来二选一。

## 影响

- 强任务候选必须 update 或说明独立目标
- 机器索引保留 archived 记录及双向关系
- consolidate 使用 revision、plan token、锁和恢复日志

## 主要替代方案

- 无

## 后果

- 无

## 未来复用场景

- 变更：调整重复任务记录的合并或归档行为；执行者：维护知识写入运行时的开发者；需复核约束：必须保留 canonical 与 archived 记录之间的双向审计关系
- 变更：修改 brief、recent tasks 或根索引的可见性；执行者：维护检索和索引的开发者；需复核约束：默认视图只展示 canonical，机器索引仍保留 archived 记录

## 适用范围

- 结构化范围：
- 仓库 `self` · 路径 `skills/cs/runtime_src/30_learning.py` · 符号 `consolidate`
- 仓库 `self` · 路径 `skills/cs/runtime_src/20_storage.py` · 符号 `render_root_index`
- 仓库 `self` · 路径 `skills/cs/runtime_src/40_retrieval.py` · 符号 `collect_search_documents`
- 仓库 `self` · 路径 `docs/knowledge-format.md` · 符号 `未限定`
- 仓库 `self` · 路径 `tests/test_knowledge.py` · 符号 `未限定`
- 标签：task-note, consolidation, retrieval
- 主题：无

## 取代说明

未取代其他长期结论。

## 验证与依据

- implementation `skills/cs/runtime_src/30_learning.py`：共享运行时用事务、版本和计划令牌执行 consolidate；支持：重复 task-note 可归档到 canonical 且保留审计关系
- implementation `skills/cs/runtime_src/20_storage.py 与 skills/cs/runtime_src/40_retrieval.py`：根索引和默认检索折叠 archived 任务记录；支持：默认 brief、recent tasks 和根索引只展示 canonical
- test `tests/test_knowledge.py`：合并幂等、过期计划、回滚和默认折叠回归测试通过；支持：归档关系可恢复且不会污染默认检索结果

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
