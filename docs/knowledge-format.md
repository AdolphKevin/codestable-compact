# Knowledge format

## Learning payload

`learn` accepts one JSON object with `task` and `items`. One logical task is the
same user goal, primary deliverable and continuous debugging/acceptance chain;
it is not one Agent turn, error, patch or `learn` call.

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
| `id` | Existing `T-*` ID; only present when updating the same logical task |
| `update_existing` | Must be `true` together with `id` and `expected_revision` for an update |
| `expected_revision` | Optimistic-lock revision read from the current task-note |
| `title` | Stable task title |
| `kind` | Informational kind; no routing behavior |
| `status` | `completed`, `in-progress`, `partial`, `blocked`, or `cancelled` |
| `request` | Original user intent, compactly restated |
| `summary` | What was actually done |
| `result` | Final observable result |
| `paths` / `symbols` / `tags` | Scope used for future retrieval |
| `verification` | Commands or evidence actually obtained |
| `deliverable` | Optional stable name/path for the primary deliverable; also used for duplicate suggestions |
| `new_task_reason` | Why this is independent when a strong existing-task candidate exists |
| `knowledge_summary` | Cards created, reused or superseded, or the reason no durable card was needed |
| `knowledge_use` | Optional strong evidence that named historical cards changed a design, implementation, test, review or scope decision |
| `source` | Optional issue, commit, ticket or external artifact metadata |

Only `completed` tasks may normally contain `items`. An interrupted task may be
written as `in-progress`, `partial` or `blocked`, but its `items` must be empty.
The narrow exception is a `partial` `knowledge-migration`: it may capture only
individually evidenced accepted/verified facts while uncertain pages remain
pending. This keeps intermediate diagnoses and soon-replaced fixes out of
long-term cards without making a partial upgrade falsely complete.

On first apply, `learn` returns `task_id` and `task_revision: 1`. To continue
the same logical task, submit a complete latest snapshot with that ID,
`update_existing: true`, and the current `expected_revision`. The task-note ID,
path and creation time remain stable; the compact body is replaced, linked card
IDs and provenance are retained, and revision increments atomically. Repeating
an already-applied snapshot is idempotent even if it carries the preceding
revision. A different update from a stale revision is rejected.

Dry-run returns `task_candidates` for deterministic same-title,
same-deliverable or strong path-overlap matches and `card_candidates` for
same-category/same-title conclusions. These are review prompts, never automatic
fuzzy merges. A strong task candidate blocks a new-task token until the caller
uses `update_existing` or supplies a concrete `new_task_reason`.

`knowledge_use` is intentionally optional. Retrieval, reading, path similarity
and automatic card linkage are weak evidence and do not belong in this field.
Each entry names an existing card, a use kind (`adopted`, `changed-design`,
`implemented`, `tested`, `reviewed`, or `scope-adjusted`), the concrete effect,
and evidence for test/review claims. This records the chain from historical
knowledge to a design choice and observable verification without rewarding
mechanical citations.

## Duplicate task consolidation

`consolidate` never deletes task-note files. It merges card links into one
canonical note, rewrites duplicates as archived audit pointers retaining their
source, verification and original-body hash, and records symmetric
`consolidated_from` / `consolidated_into` relations. Archived notes remain in
`index.jsonl` for audit but have no excerpt and are excluded from default brief,
recent tasks and the root Markdown index.

```json
{
  "canonical_task_id": "T-20260807-120000-a1b2c3d4",
  "expected_revision": 2,
  "duplicates": [
    {"id": "T-20260807-121000-e5f6a7b8", "expected_revision": 1}
  ],
  "reason": "Same user goal, primary deliverable and continuous acceptance chain."
}
```

Run `consolidate --file ... --dry-run`, then apply the unchanged payload with
the returned `--plan-token`. The operation uses the Wiki lock and recovery
journal, is idempotent, and rejects stale revisions or changed Wiki/workspace
state.

Changed completed task-notes are checked by `drift`: they need a final result,
actual verification, basic path/symbol coverage of the semantic Git diff and a
non-empty knowledge disposition. This does not require creating a card.

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

`status` and `confidence` do not form one global truth ranking. Accepted
requirements, constraints and decisions normally describe intended behavior;
verified behavioral facts describe behavior confirmed by their evidence.
Proposed, inferred, deprecated and superseded cards remain context only when a
current conflict is resolved. No additional claim-kind field is required:
Agents determine the claim from its category, wording, evidence and rationale.

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

A card also needs a future consumer and final evidence. A one-off
`bigint=text` failure or a temporary test-table deletion order belongs in the
task summary. A project-relevant B-tree limit for arbitrary-length expressions,
or a stable migration rule to merge formal email identities by
`lower(trim(email))`, may become a card after final verification and a check
that no equivalent current card already exists.
