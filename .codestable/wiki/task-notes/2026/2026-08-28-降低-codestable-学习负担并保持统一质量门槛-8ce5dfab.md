---
id: "T-20260828-162416-8ce5dfab"
type: "task-note"
title: "降低 CodeStable 学习负担并保持统一质量门槛"
created_at: "2026-08-28T16:24:16+08:00"
updated_at: "2026-08-28T16:24:16+08:00"
revision: 1
task_status: "completed"
fingerprint: "8ce5dfab8aef18f6d44828e6713df835305ce31cce94c3cad90b6c32c8c33936"
tags: []
topics: []
scopes: [{"path": "skills/cs/runtime_src/70_cli.py", "repository": "self", "symbol": "template_payload"}, {"path": "skills/cs/runtime_src/70_cli.py", "repository": "self", "symbol": "compact_learn_result"}, {"path": "skills/cs/runtime_src/10_capture.py", "repository": "self", "symbol": "normalize_task"}, {"path": ".codestable/wiki/learning.schema.json", "repository": "self", "symbol": ""}, {"path": "tests/test_governance_acceptance.py", "repository": "self", "symbol": "test_default_compact_output_stays_bounded_with_many_verified_references"}]
paths: []
symbols: []
card_ids: ["K-20260828-162416-01-fde24cad"]
deliverable: "CodeStable 学习模板、默认输出契约、严格校验及其文档和回归测试"
new_task_reason: "这是在原紧凑输出功能完成后，基于新的使用反馈独立改变默认输出和模板契约的后续任务，不是对原任务记录的补充验收。"
knowledge_summary: "既有卡片 K-20260828-121106-02-15986c2d 规定完整输出为默认，与本次新的稳定接口契约冲突，因此建立一张明确替代它的新卡片；没有拆出其他重复卡片。"
knowledge_use: [{"after": "learn 默认输出紧凑结果；需要完整已验证引用明细时显式传入 --full，--compact 仅作为兼容别名。", "before": "learn 默认输出全部已验证引用，交互式调用需要显式传入 --compact。", "card_id": "K-20260828-121106-02-15986c2d", "card_revision": 1, "detail": "沿用旧卡片关于紧凑结果必须保留计划令牌、可操作问题和计数的约束，同时根据本次反馈反转默认输出选择，并保留显式完整诊断入口。", "evidence": [{"artifact": "skills/cs/runtime_src/70_cli.py compact_learn_result, build_parser and command_main", "kind": "implementation", "result": "默认路径调用 compact_learn_result，--full 返回完整计划；紧凑结果仍复制除完整 verified 列表之外的全部计划数据。", "supports": "默认输出变化没有删除计划令牌、候选、未验证引用、可操作问题和计数。"}], "use": "changed-design"}]
source: {"kind": "user-feedback", "release_status": "implemented-not-released"}
visibility: "active"
consolidated_from: []
kind: "refactor"
---

# 降低 CodeStable 学习负担并保持统一质量门槛

## 请求

优化 CodeStable 的使用体验，不依赖小、中、大任务分类；减少模板字段和输出上下文占用，同时不得降低 Agent 使用知识库的质量、证据与可追溯要求。

## 处理摘要

将学习模板改为默认只生成九个语义任务字段，只有明确存在长期结论时才按类别生成卡片脚手架；让卡片继承任务的机械适用信息；把 learn 的紧凑结果设为默认并提供 --full 完整诊断；新增模板占位符、范围继承和输出压缩回归。

## 最终结果

所有任务继续经过同一套知识读取、处置、dry-run、计划令牌写入和检查门槛，不引入任务规模判断。默认模板由 2160 字节降至 591 字节，约减少 73%；80 条已验证引用场景下，默认输出小于完整输出的三分之一。

## 验证

- python3 -m unittest discover -s tests -v：99 项测试全部通过
- python3 scripts/validate_release.py --source .：发布校验通过，包含运行时同步、全新安装、升级保留、零写入读取和往返验证
- 默认任务模板从修改前的 2160 字节降至 591 字节，约减少 73%
- 80 条已验证引用回归证明默认紧凑输出小于 --full 完整输出的三分之一

## 变更范围

- 路径：未记录
- 符号：未记录
- 结构化范围：[{"repository": "self", "path": "skills/cs/runtime_src/70_cli.py", "symbol": "template_payload"}, {"repository": "self", "path": "skills/cs/runtime_src/70_cli.py", "symbol": "compact_learn_result"}, {"repository": "self", "path": "skills/cs/runtime_src/10_capture.py", "symbol": "normalize_task"}, {"repository": "self", "path": ".codestable/wiki/learning.schema.json", "symbol": ""}, {"repository": "self", "path": "tests/test_governance_acceptance.py", "symbol": "test_default_compact_output_stays_bounded_with_many_verified_references"}]
- 标签：无
- 主题：无
- 主要交付物：CodeStable 学习模板、默认输出契约、严格校验及其文档和回归测试
- 独立任务理由：这是在原紧凑输出功能完成后，基于新的使用反馈独立改变默认输出和模板契约的后续任务，不是对原任务记录的补充验收。

## 沉淀的知识卡片

- `K-20260828-162416-01-fde24cad`

## 知识处置

既有卡片 K-20260828-121106-02-15986c2d 规定完整输出为默认，与本次新的稳定接口契约冲突，因此建立一张明确替代它的新卡片；没有拆出其他重复卡片。

## 历史知识使用证据

- `K-20260828-121106-02-15986c2d` revision 1 · changed-design · 沿用旧卡片关于紧凑结果必须保留计划令牌、可操作问题和计数的约束，同时根据本次反馈反转默认输出选择，并保留显式完整诊断入口。 · 调整前：learn 默认输出全部已验证引用，交互式调用需要显式传入 --compact。 · 调整后：learn 默认输出紧凑结果；需要完整已验证引用明细时显式传入 --full，--compact 仅作为兼容别名。 · 依据：implementation `skills/cs/runtime_src/70_cli.py compact_learn_result, build_parser and command_main`：默认路径调用 compact_learn_result，--full 返回完整计划；紧凑结果仍复制除完整 verified 列表之外的全部计划数据。；对应约束：默认输出变化没有删除计划令牌、候选、未验证引用、可操作问题和计数。

## 来源

```json
{
  "kind": "user-feedback",
  "release_status": "implemented-not-released"
}
```
