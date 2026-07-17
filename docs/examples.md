# Examples

## Bug fix

Request:

```text
$cs 修复库存不足时订单仍被提交的问题
```

At the start, the Agent runs:

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '修复库存不足时订单仍被提交的问题'
```

After identifying `src/orders/service.py` and `OrderService.create`, it refreshes the brief with that scope. The brief may reveal:

- an accepted local-transaction decision;
- a stable inventory error code;
- a rollback acceptance rule;
- a known row-lock performance risk.

The Agent then implements and tests normally. It records one task note and cards only for newly established or changed long-term truths.

## New interface

A task adding an export API may create cards in:

- `requirements`: export format and filtering rules;
- `interfaces`: endpoint, request, response and failure contract;
- `data-model`: snapshot fields or cursor state;
- `compatibility`: additive API/version behavior;
- `performance-risks`: maximum export size and streaming constraint;
- `security-boundaries`: tenant/auth scope;
- `acceptance`: matrix for empty, large, unauthorized and partial-failure cases;
- `decisions`: synchronous vs asynchronous export choice.

It should not create all categories mechanically. Empty categories remain explicit gaps in the next brief.

## Changed decision

Suppose an old card says:

```text
K-20260701-090000-01-a1b2c3d4
订单导出同步生成 CSV。
```

The system now adopts asynchronous object-storage exports. The new decision card includes:

```json
{
  "category": "decisions",
  "title": "大批量订单导出采用异步作业",
  "knowledge": "超过同步阈值的订单导出进入异步作业并返回 job id。",
  "rationale": "同步请求会超过网关超时并占用应用 worker。",
  "implications": [
    "接口需要 job status 查询",
    "对象下载链接必须有租户和时效边界"
  ],
  "confidence": "accepted",
  "status": "current",
  "supersedes": ["K-20260701-090000-01-a1b2c3d4"]
}
```

The old card remains in Git history and the Wiki, but normal briefs omit it.

## No durable learning

A task that only updates a one-off fixture may have:

```json
{
  "task": {
    "title": "更新一次性演示数据",
    "status": "completed",
    "summary": "替换了演示环境的过期样例。",
    "result": "演示页面恢复。",
    "verification": ["manual demo smoke check"]
  },
  "items": []
}
```

CodeStable still writes a task note. It does not manufacture a long-term card just to fill a category.
