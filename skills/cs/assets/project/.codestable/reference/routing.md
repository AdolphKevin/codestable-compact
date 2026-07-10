# Routing and continuation

## Resume before route

先读取 active work 的小型 `state.json` 元数据。如果请求明确匹配一个 active work，直接按其 `kind/stage` 继续。不要重新分类为新任务。

若用户只说“继续”：

- 只有一个 active work：继续它；
- 多个 active work：先按最近上下文、标题、scope 路径和关键词匹配；
- 仍有两个同等候选且选择会改变代码范围时，才问一个澄清问题。

## Route table

- 新可观察能力 → `feature`
- 现有预期行为错误、回归、异常、卡顿、性能退化 → `issue`
- 保持行为的结构改善 → `refactor`
- 多能力、跨系统、先后依赖或契约尚未收敛 → `roadmap`
- vision/domain/requirement/contract/decision/knowledge → `model`

用户提出的解法不是自动路由依据。例如“重写缓存解决超时”应先按 issue 复现超时，再由证据决定是否转 refactor。

## Route output

`compact`：一行 `→ <kind> · <lane> · <action>`，随后继续。

`debug`：可补充 reason / rejected route / escalation，但仍继续。

`route` 模式或 `/cs route`：只分析，不执行。
