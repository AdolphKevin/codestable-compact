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
    "scopes": [
      {"repository": "self", "path": "src/orders/service.py", "symbol": "OrderService.create"}
    ],
    "topics": ["order-lifecycle"],
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
      "future_use": [
        {"change": "拆分库存存储", "actor": "库存维护者", "constraint": "重新评估原子提交边界"},
        {"change": "调整订单提交", "actor": "订单评审者", "constraint": "不允许部分成功状态"}
      ],
      "scopes": [
        {"repository": "self", "path": "src/orders/service.py", "symbol": "OrderService.create"}
      ],
      "topics": ["order-lifecycle"],
      "tags": ["orders"],
      "evidence": [
        {
          "kind": "test",
          "artifact": "OrderTests.test_inventory_rollback",
          "result": "库存不足回滚测试通过",
          "supports": "订单和库存预留共享一个提交结果"
        }
      ],
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
| `scopes` | Preferred stable scope: repository alias plus repository-relative path and/or symbol |
| `paths` / `symbols` | Single-repository path and symbol shorthand |
| `topics` | Configured, deterministic business-topic keys used as an additional retrieval view |
| `tags` | Stable technical or product labels |
| `verification` | Commands or evidence actually obtained |
| `deliverable` | Optional stable name/path for the primary deliverable; also used for duplicate suggestions |
| `new_task_reason` | Why this is independent when a strong existing-task candidate exists |
| `knowledge_summary` | Cards created, reused or superseded, or the reason no durable card was needed |
| `knowledge_use` | Optional strong evidence that named historical cards changed a design, implementation, test, review or scope decision |
| `source` | Optional issue, commit, ticket or external artifact metadata |

Only `completed` tasks may contain `items`. An interrupted task may be
written as `in-progress`, `partial` or `blocked`, but its `items` must be empty.
This also applies to a knowledge rebuild: complete the evidence checks before
creating durable cards. The old knowledge-migration payload is not supported.

On first apply, `learn` returns `task_id` and `task_revision: 1`. To continue
the same logical task, generate a prefilled snapshot with `template --task-id
T-...`, edit the current result, and submit it with `update_existing: true` and
the current `expected_revision`. The task-note ID, path and creation time remain
stable; the compact body is replaced, linked card IDs and provenance are
retained, and revision increments atomically. Historical `knowledge_use` keeps
the card revision that actually influenced that earlier work even when the card
later advances. Repeating an already-applied snapshot is idempotent even if it
carries the preceding revision. A different update from a stale task revision
is rejected.

Dry-run returns `task_candidates` for deterministic same-title,
same-deliverable or strong path-overlap matches and `card_candidates` for
same-category/same-title conclusions. These are review prompts, never automatic
fuzzy merges. A strong task candidate blocks a new-task token until the caller
uses `update_existing` or supplies a concrete `new_task_reason`.

The initial `template` is task-only by default. This is knowledge-disposition
driven, not a small/medium/large task classification: every task keeps the same
quality gates, while `--card-category <category>` adds a durable-card skeleton
only after the Agent concludes that a new reusable fact exists. Empty optional
metadata and default card controls are omitted; card scope, topics and tags
inherit from the task unless a narrower boundary is supplied. The semantic
fields remain explicit and placeholders are rejected by `learn` before a plan
token can be issued.

`learn` returns compact JSON by default. It keeps the plan token, write plan,
task/card candidates, conflicts, warnings, actionable findings, unverified
references and counts, while omitting the potentially large verified-reference
list. `--full` expands that diagnostic list. The legacy `--compact` flag remains
an alias for the default behavior.

`knowledge_use` is intentionally optional. Retrieval, reading, mentioning a card
ID, path similarity, coincidental agreement and automatic card linkage are not
usage evidence. Each entry names an existing card, a use kind (`adopted`,
`changed-design`, `implemented`, `tested`, `reviewed`, or `scope-adjusted`), and
the card revision shown by `brief`, and the concrete effect. A later task update
preserves existing entries unchanged; only a new effect requires a fresh brief
and a new entry bound to the current card revision. Every evidence item must include:

- `kind`: `implementation`, `test`, `design`, `review`, `scope`, or `contract`;
- `artifact`: a checkable implementation location, test ID, review result, or public design artifact;
- `result`: what was observed;
- `supports`: how that observation corresponds to the card's conclusion.

The evidence kind must match the claimed use. `changed-design` also requires
public `before` and `after` descriptions. `reviewed` must name what was checked
and the actual conclusion; `tested` must identify the invariant; `implemented`
must point to implementation or a public design artifact.

```json
{
  "card_id": "K-...",
  "card_revision": 1,
  "use": "changed-design",
  "detail": "Kept direct publishing out of the business transaction and limited the change to the adapter and dispatcher.",
  "before": "The task allowed the domain service to invoke the new message client.",
  "after": "Only the publishing adapter and dispatcher changed.",
  "evidence": [
    {
      "kind": "test",
      "artifact": "ShipmentTests.test_outbox_retry",
      "result": "A failed publish remains retryable without recreating the shipment.",
      "supports": "The business record and outbox entry share a commit point."
    }
  ]
}
```

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
actual verification, at least one representative path/structured self scope or
changed symbol overlapping the semantic Git diff, and a non-empty knowledge
disposition. A task note is traceability, not an exhaustive changed-file
manifest. Git-confirmed deleted or renamed task targets are valid task scope;
current cards that reference them still require semantic review. This does not
require creating a card.

## Card fields

| Field | Meaning |
|---|---|
| `category` | One of the 11 canonical category slugs |
| `title` | One durable conclusion per card |
| `knowledge` | Current-tense fact, constraint, risk, acceptance rule or decision |
| `context` | Background and failure mode for a decision |
| `rationale` | Why this is true or why the decision was made |
| `alternatives` / `consequences` | Main alternatives and accepted consequences for a decision |
| `future_use` | At least two distinct `{change, actor, constraint}` situations that should re-check the card |
| `implications` | Concrete effects on future work |
| `scopes` | Preferred repository/path/symbol applicability scope |
| `paths` / `symbols` | Legacy scope, still readable and verifiable |
| `topics` / `tags` | Deterministic topic navigation and stable labels |
| `evidence` | Structured `{kind, artifact, result, supports}` implementation, test, contract, compatibility or accepted-decision evidence |
| `applies_to` | Optional consumer scopes for shared constraints; repository-specific downward path matching |
| `depends_on` | Optional card IDs from this Wiki; retrieval expands one hop of current dependencies |
| `confidence` | `verified`, `accepted`, or `inferred` |
| `status` | `current`, `proposed`, or `deprecated` at input time |
| `supersedes` | Existing current card IDs replaced by this card |
| `supersession_reason` | Why a prior long-term conclusion is no longer current |
| `operation` / `card_id` / `expected_revision` | Safely update unchanged knowledge metadata or scope without creating a duplicate |
| `new_card_reason` | Why a similarity candidate is genuinely orthogonal rather than duplicate |
| `pinned` | Small number of high-priority facts to boost in retrieval |

Current cards require structured evidence, scope and at least two future-use
scenarios. `verified` requires implementation, test, contract or compatibility
evidence on the item. An explicitly accepted decision without behavioral proof
uses `accepted-decision` evidence and `confidence: accepted`. A decision card
additionally requires context, rationale, alternatives and consequences.

Structured scope is configured in `.codestable/config.json`:

```json
{
  "wiki": {
    "repositories": {
      "shared-contracts": {"root": "../shared-contracts"}
    },
    "topics": {
      "order-lifecycle": {"label": "Order lifecycle", "summary": "Cross-category current knowledge."}
    },
    "topic_governance": {"mode": "manual", "minimum_coverage": 0.8}
  }
}
```

`repository: self` means the current repository. A configured alias resolves to
its local repository root. An unconfigured alias remains usable for retrieval
but reference checks report it as unverified, never as a missing file.

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
scopes: [{"repository": "self", "path": "src/orders/service.py", "symbol": "OrderService.create"}]
topics: ["order-lifecycle"]
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

A new card is valid only when no semantically equivalent current card exists,
the conclusion is expected to affect multiple future tasks, it expresses a
stable constraint/boundary/contract/guarantee/compatibility rule/accepted
decision, final evidence supports it, and its applicability is clear. Decisions
also preserve background, alternatives and consequences.

Implementing an existing decision reuses that card and may record real
`knowledge_use`; it does not create a synonym card. An orthogonal durable
constraint can create a new card without superseding the existing decision.
Only a changed long-term conclusion uses `supersedes`; an unchanged conclusion
with a renamed path uses an in-place card update and retains `scope_history`.

A one-off
`bigint=text` failure or a temporary test-table deletion order belongs in the
task summary. A project-relevant B-tree limit for arbitrary-length expressions,
or a stable migration rule to merge formal email identities by
`lower(trim(email))`, may become a card after final verification and a check
that no equivalent current card already exists.

## Compact rendering (2.0)

New records store scopes, evidence, future-use scenarios, source provenance and
knowledge-use history once in front matter. Body sections retain conclusions,
reasons, task outcomes and verification. Empty optional metadata and empty
sections are omitted; consumers treat missing optional fields as their defaults.
Old databases must be rebuilt from current evidence; their documents are not imported.

Current schema-4 evidence may additionally carry `verified_at`, `source_snapshots`,
`case_ids`, and `run_record`. These are optional extensions, not a new database format.
`confidence` preserves the author's declaration; `evidence_validity` independently
reports current bindings, review needs, or unavailable evidence. Missing bindings do
not block learning and are never filled from the current code on behalf of an old run.
Human-page source and body bindings, local run-summary format, and exact retrieval
limits are specified in [Knowledge reliability](knowledge-reliability.md).
Card IDs, task IDs, paths and supersession relations remain stable. Machine
indexes are derived local cache by default; see [storage](storage.md).
