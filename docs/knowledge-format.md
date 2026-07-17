# Knowledge format

## Learning payload

`learn` accepts one JSON object with `task` and `items`.

```json
{
  "task": {
    "title": "库存不足时回滚订单创建",
    "kind": "issue",
    "status": "completed",
    "request": "修复库存不足仍提交订单的问题",
    "summary": "将库存预留与订单写入放在同一事务内。",
    "result": "库存不足时不产生订单，也不扣减库存。",
    "paths": ["src/orders/service.py"],
    "symbols": ["OrderService.create"],
    "tags": ["orders", "inventory"],
    "verification": ["python3 -m unittest tests.test_orders"],
    "source": {"issue": "ORDER-17", "commit": "optional"}
  },
  "items": [
    {
      "category": "transaction-boundaries",
      "title": "订单创建与库存预留共享事务",
      "knowledge": "订单写入与库存预留必须在同一数据库事务中提交。",
      "rationale": "避免订单成功但库存未预留的部分成功状态。",
      "implications": ["库存不足必须在提交点前抛出"],
      "paths": ["src/orders/service.py"],
      "symbols": ["OrderService.create"],
      "tags": ["orders"],
      "evidence": ["rollback regression test passes"],
      "confidence": "verified",
      "status": "current",
      "supersedes": [],
      "pinned": false
    }
  ]
}
```

## Task fields

| Field | Meaning |
|---|---|
| `title` | Stable task title |
| `kind` | Informational kind; no routing behavior |
| `status` | `completed`, `partial`, `blocked`, or `cancelled` |
| `request` | Original user intent, compactly restated |
| `summary` | What was actually done |
| `result` | Final observable result |
| `paths` / `symbols` / `tags` | Scope used for future retrieval |
| `verification` | Commands or evidence actually obtained |
| `source` | Optional issue, commit, ticket or external artifact metadata |

## Card fields

| Field | Meaning |
|---|---|
| `category` | One of the 11 canonical category slugs |
| `title` | One durable conclusion per card |
| `knowledge` | Current-tense fact, constraint, risk, acceptance rule or decision |
| `rationale` | Why this is true or why the decision was made |
| `implications` | Concrete effects on future work |
| `paths` / `symbols` / `tags` | Applicability scope |
| `evidence` | Tests, code references, contracts or accepted authority |
| `confidence` | `verified`, `accepted`, or `inferred` |
| `status` | `current`, `proposed`, or `deprecated` at input time |
| `supersedes` | Existing current card IDs replaced by this card |
| `pinned` | Small number of high-priority facts to boost in retrieval |

`verified` requires evidence on the item or task. A decision card requires rationale.

## Generated card

Cards use JSON-valued Markdown front matter so no YAML dependency is required:

```markdown
---
id: "K-20260717-103000-01-ab12cd34"
type: "knowledge-card"
category: "transaction-boundaries"
status: "current"
confidence: "verified"
paths: ["src/orders/service.py"]
supersedes: []
---

# 订单创建与库存预留共享事务

## 结论
...
```

The body remains readable in GitHub, IDE previews and ordinary Wiki tooling.

## Granularity

Good cards are atomic and future-facing:

- “订单写入与库存预留必须在同一本地事务中提交。”
- “库存不足错误码 `INVENTORY_INSUFFICIENT` is a public compatibility contract.”
- “批量订单 creation can contend on the inventory row lock.”

Avoid cards such as:

- “Changed three files and fixed tests.”
- “Tried approach A, then B.”
- “Always write clean code.”
- raw logs, secrets or complete diffs.
