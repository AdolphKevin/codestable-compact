# 共享约束、证据有效性与摘要复核

这些能力扩展当前格式 4，不要求清空知识库。新增信息均可选；没有版本绑定的
旧证据继续可读，查询明确标为证据不足。检查提示不能自动证明业务结论正确，
也不自动改卡片状态、删除历史或阻止知识写入。

## 共享约束检索

卡片的 `scopes`、`paths`、`symbols` 继续用于直接检索。共享约束另行声明消费者：

```json
{
  "applies_to": [{"repository": "self", "path": "src/orders"}],
  "depends_on": ["K-existing-authorization-rule"]
}
```

`applies_to` 复用仓库、路径和可选符号结构，但路径只向下匹配：上例覆盖
`src/orders/new.py`，即使该文件尚未创建，也不会覆盖 `src/orders_archive`。
路径 `.` 显式表示整个指定仓库；带符号时还要求符号命中。省略仓库默认为 `self`。
普通 `--path`、`--symbol` 只匹配本仓库，其他仓库使用 `--scope`。

`depends_on` 只引用本知识库的卡片编号。查询从直接命中的卡片和适用约束出发，
扩展一层当前依赖。依赖不存在、弃用或已被取代时，返回复核提示，不自动改指向。
环形依赖不会递归扩展。新增卡片需先取得编号，再通过正常更新引用它。

JSON 保留 `knowledge` 列表，增加 `match_group: direct|shared-constraint`；
`match_reasons` 解释适用范围或来源卡片。文本分组，卡片去重。总量仍由
`--limit` 或 `brief.max_items` 限制，`brief.max_shared_items` 默认是 5。
同时存在直接结果且总量至少为 2 时，保留至少一个直接结果；共享约束不受旧的
分类配额挤压。`truncation` 报告因数量限制省略的候选，文本也提示扩大上限。

## 验证时的证据

原有 `{kind, artifact, result, supports}` 表达作者提供的证据说明。可增加：

```json
{
  "verified_at": "2026-09-28T08:00:00+00:00",
  "source_snapshots": [
    {"repository": "self", "path": "src/auth.py", "sha256": "验证时文件的64位SHA-256", "revision": "可选提交版本"},
    {"repository": "self", "path": "tests/test_auth.py", "sha256": "验证时测试文件的64位SHA-256"}
  ],
  "case_ids": ["auth.denied"],
  "run_record": {"repository": "self", "path": "verification/auth-run.json"}
}
```

示例中的指纹说明文字需要替换为真实指纹。来源应包含实际验证涉及的实现、测试、
配置和契约文件；工具只核对声明的范围，不猜测未声明的依赖。`revision` 便于追溯，
有效性由文件内容指纹决定。不能在写入知识时对新代码计算指纹，然后声称旧测试
验证了这个版本。时间必须带时区，不设统一的证据过期天数。

测试或持续集成产生的本地运行摘要采用以下最小 JSON 结构：

```json
{
  "verified_at": "2026-09-28T08:00:00+00:00",
  "sources": [
    {"repository": "self", "path": "src/auth.py", "sha256": "验证时文件的64位SHA-256", "revision": "可选提交版本"},
    {"repository": "self", "path": "tests/test_auth.py", "sha256": "验证时测试文件的64位SHA-256"}
  ],
  "cases": [{"id": "auth.denied", "result": "passed"}]
}
```

摘要的来源集合和时间须与证据一致，每个指定用例均须记录为 `passed`。
`failed`、`skipped`、缺失用例和重复用例编号都不能证明通过。运行摘要可附加运行编号；
`run_record.sha256` 可进一步固定该记录自身的内容。工具不执行测试、不访问远程
链接，也不复制完整日志。单个关联文件的读取上限为 16 MiB。

`evidence_validity.status` 与作者的 `confidence` 分开：

| 状态 | 含义 |
|---|---|
| `current` | 声明的来源指纹一致；测试证据的运行摘要也一致 |
| `needs-review` | 来源内容变化、文件已删除、记录变化或用例未通过 |
| `unverifiable` | 版本、时间、运行记录等资料缺失或无法读取 |
| `not-applicable` | 没有行为版本绑定的明确权威决定，不属于行为测试 |

一张卡有多项证据时，任何一项需复核或无法核实都会显式保留该状态，不能被另一项
通过记录掩盖。文本继续提供正文，紧邻显示原因、验证时间和来源指纹摘要。
这些状态只说明声明的来源绑定，不能证明测试充分、运行记录真实或业务结论正确。

工作区查询可读取已配置仓库的文件；暂存区和提交检查使用本仓库对应 Git 内容。
外部仓库没有与被检查版本对应的快照时，显示无法核实，不借用其工作区内容。

## 人工摘要与总览

分类摘要默认依赖 `category:<分类名称>`，包含该分类当前卡片的成员变化。
项目总览默认依赖所有分类的当前卡片及分类摘要。`sources` 可显式缩小为卡片编号
或分类选择器；分类摘要的分类选择器只引用卡片，总览还引用该分类摘要。

实际复核后，在人工页面的正文标记之外保存：

```text
<!-- codestable:summary-review {"sources":["category:security-boundaries"],"knowledge_hash":"来源指纹","summary_hash":"摘要正文指纹","reviewed_at":"实际复核时间，带时区"} -->
```

`audit --format json` 的 `sections.content_review.summaries` 提供每页的 `sources`、
`expected_knowledge_hash`、`expected_summary_hash` 和原因。先对照来源复核正文，
再保存这些字段及实际时间。只更新分类摘要，不会替旧总览完成复核；总览仍须确认。
旧标记缺少正文指纹时明确提示信息不足。摘要继续沿用配置中的复核期限。

知识新增、更新、取代、证据失效和摘要正文变化都会影响复核状态。查询动态推导，
不会写状态文件；重建索引不会更新复核标记。健康且完整的主题导航仍可替代空分类摘要。

`brief` 返回展示内容相关的 `review_queue`；`learn --dry-run` 根据拟写入状态返回
完整待复核清单；`audit` 返回全库清单。清单包含对象、位置、原因、来源及建议动作。
`learn` 保持已有预览和原子写入流程，证据不足或摘要过期只是提示。输入结构错误、
已有版本冲突和其他既有写入约束仍正常报错。

计划令牌同时绑定人工页面与当前卡片及本次输入引用的证据文件，包括忽略文件和
已配置外部仓库中的来源。预览后关联内容变化须重新预览。查询回执也绑定本次
展示的有效性依据，仍然只证明展示过，不能作为知识贡献记录。

## CodeStable 自身回归

在仓库运行 `python3 scripts/check_knowledge_reliability.py` 可执行固定匿名回归集，
输出关键约束召回率、无关结果比例、过期知识漏检率、简报字符数与维护操作数。
前三项要求分别为 1、0、0；这是固定测试集的结果，不是实际项目的总体效果估计。
字符数用于比较上下文开销，不声称等于模型 token 数。该脚本不随公开技能发布，
不采集消费项目使用记录。知识实际产生作用的比例留待后续真实使用关联能力。
