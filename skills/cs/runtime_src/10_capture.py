"""CodeStable runtime section: 10 capture."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def reject_task_template_placeholder(value: str, field: str) -> None:
    if "__REPLACE__" in value:
        raise KnowledgeError(f"{field} contains placeholder template text; replace it with the actual task value")


def normalize_task(raw: Any, config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("learning payload task must be an object")
    allowed = {
        "title", "kind", "id", "update_existing", "expected_revision", "status", "request", "summary",
        "result", "paths", "symbols", "scopes", "topics", "tags", "verification", "deliverable",
        "new_task_reason", "knowledge_summary", "knowledge_use", "source",
    }
    if set(raw) - allowed:
        raise KnowledgeError("unknown task fields: " + ", ".join(sorted(set(raw) - allowed)))
    title = normalize_space(raw.get("title"))
    kind = normalize_space(raw.get("kind") or "task")
    request = normalize_space(raw.get("request"))
    summary = normalize_space(raw.get("summary"))
    result = normalize_space(raw.get("result"))
    deliverable = normalize_space(raw.get("deliverable"))
    new_task_reason = normalize_space(raw.get("new_task_reason"))
    knowledge_summary = normalize_space(raw.get("knowledge_summary"))
    status = normalize_space(raw.get("status") or "completed").lower()
    if not title:
        raise KnowledgeError("task.title is required")
    if not summary:
        raise KnowledgeError("task.summary is required")
    if not result:
        raise KnowledgeError("task.result is required")
    if status not in TASK_STATUSES:
        raise KnowledgeError(f"task.status must be one of {sorted(TASK_STATUSES)}")
    source = raw.get("source") or {}
    if not isinstance(source, dict):
        raise KnowledgeError("task.source must be an object")
    task_id = normalize_space(raw.get("id"))
    raw_update_existing = raw.get("update_existing", False)
    if not isinstance(raw_update_existing, bool):
        raise KnowledgeError("task.update_existing must be a boolean")
    update_existing = raw_update_existing
    expected_revision = raw.get("expected_revision")
    if update_existing:
        if not re.fullmatch(r"T-[A-Za-z0-9-]+", task_id):
            raise KnowledgeError("task.id must be an existing T-* identifier when task.update_existing is true")
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
            raise KnowledgeError("task.expected_revision must be a positive integer when updating a task")
    elif task_id or expected_revision is not None:
        raise KnowledgeError("task.id and task.expected_revision require task.update_existing=true")
    raw_knowledge_use = raw.get("knowledge_use") or []
    if not isinstance(raw_knowledge_use, list):
        raise KnowledgeError("task.knowledge_use must be an array")
    knowledge_use: list[dict[str, Any]] = []
    for value in raw_knowledge_use:
        if not isinstance(value, dict):
            raise KnowledgeError("every task.knowledge_use entry must be an object")
        if set(value) - {"card_id", "card_revision", "use", "detail", "before", "after", "evidence"}:
            raise KnowledgeError("task.knowledge_use contains unknown fields")
        card_id = normalize_space(value.get("card_id"))
        card_revision = value.get("card_revision")
        use = normalize_space(value.get("use")).lower()
        detail = normalize_space(value.get("detail"))
        before = normalize_space(value.get("before"))
        after = normalize_space(value.get("after"))
        if not re.fullmatch(r"K-[A-Za-z0-9-]+", card_id):
            raise KnowledgeError("task.knowledge_use.card_id must be an existing K-* identifier")
        if not isinstance(card_revision, int) or isinstance(card_revision, bool) or card_revision < 1:
            raise KnowledgeError("task.knowledge_use.card_revision must be a positive integer from the brief receipt")
        if use not in KNOWLEDGE_USE_KINDS:
            raise KnowledgeError(f"task.knowledge_use.use must be one of {sorted(KNOWLEDGE_USE_KINDS)}")
        if not detail or GENERIC_KNOWLEDGE_USE.fullmatch(detail):
            raise KnowledgeError("task.knowledge_use.detail must state the concrete design or review effect")
        evidence = normalize_evidence_objects(value.get("evidence"), use)
        if use == "changed-design" and (not before or not after):
            raise KnowledgeError("task.knowledge_use 'changed-design' requires public before and after descriptions")
        knowledge_use.append(
            {
                "card_id": card_id,
                "card_revision": card_revision,
                "use": use,
                "detail": detail,
                "before": before,
                "after": after,
                "evidence": evidence,
            }
        )
    if "knowledge_migration" in source or kind == "knowledge-migration":
        raise KnowledgeError("old knowledge migration is not supported; rebuild from current source and tests")
    paths = unique_strings(raw.get("paths"))
    symbols = unique_strings(raw.get("symbols"))
    scopes = normalize_scopes(raw.get("scopes"))
    topics = normalize_topics(raw.get("topics"), config)
    tags = unique_strings(raw.get("tags"))
    verification = unique_strings(raw.get("verification"))
    for field, value in (
        ("title", title),
        ("kind", kind),
        ("request", request),
        ("summary", summary),
        ("result", result),
        ("deliverable", deliverable),
        ("new_task_reason", new_task_reason),
        ("knowledge_summary", knowledge_summary),
    ):
        if value:
            reject_task_template_placeholder(value, f"task.{field}")
    for field, values in (
        ("paths", paths),
        ("symbols", symbols),
        ("topics", topics),
        ("tags", tags),
        ("verification", verification),
    ):
        for value in values:
            reject_task_template_placeholder(value, f"task.{field}")
    for scope in scopes:
        for field in ("repository", "path", "symbol"):
            value = normalize_space(scope.get(field))
            if value:
                reject_task_template_placeholder(value, f"task.scopes.{field}")
    return {
        "id": task_id,
        "update_existing": update_existing,
        "expected_revision": expected_revision,
        "title": title,
        "kind": kind,
        "status": status,
        "request": request,
        "summary": summary,
        "result": result,
        "paths": paths,
        "symbols": symbols,
        "scopes": scopes,
        "topics": topics,
        "tags": tags,
        "verification": verification,
        "deliverable": deliverable,
        "new_task_reason": new_task_reason,
        "knowledge_summary": knowledge_summary,
        "knowledge_use": knowledge_use,
        "source": source,
    }


def normalize_item(raw: Any, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("every learning item must be an object")
    allowed = {
        "operation", "card_id", "expected_revision", "category", "title", "knowledge", "context",
        "rationale", "alternatives", "consequences", "future_use", "implications", "paths", "symbols",
        "scopes", "topics", "tags", "evidence", "confidence", "status", "supersedes",
        "supersession_reason", "new_card_reason", "pinned", "applies_to", "depends_on",
    }
    if set(raw) - allowed:
        raise KnowledgeError("unknown knowledge item fields: " + ", ".join(sorted(set(raw) - allowed)))
    category = normalize_space(raw.get("category"))
    if category not in CATEGORY_DEFS:
        raise KnowledgeError(f"item.category must be one of {sorted(CATEGORY_DEFS)}")
    title = normalize_space(raw.get("title"))
    knowledge = normalize_space(raw.get("knowledge"))
    if not title:
        raise KnowledgeError("item.title is required")
    if not knowledge:
        raise KnowledgeError("item.knowledge is required")
    confidence = normalize_space(raw.get("confidence") or "accepted").lower()
    if confidence not in CONFIDENCE_LEVELS:
        raise KnowledgeError(f"item.confidence must be one of {sorted(CONFIDENCE_LEVELS)}")
    status = normalize_space(raw.get("status") or "current").lower()
    if status not in INPUT_CARD_STATUSES:
        raise KnowledgeError(f"item.status must be one of {sorted(INPUT_CARD_STATUSES)}")
    capture = config.get("capture") if isinstance(config.get("capture"), dict) else {}
    strict = bool(capture.get("strict_durable_cards", True))
    evidence = normalize_card_evidence(raw.get("evidence"), strict)
    final_evidence = evidence or ([] if strict else list(task["verification"]))
    if confidence == "verified" and not final_evidence:
        raise KnowledgeError(f"verified item '{title}' requires item.evidence")
    if strict and confidence == "verified" and not any(
        isinstance(value, dict) and value.get("kind") in {"implementation", "test", "contract", "compatibility"}
        for value in final_evidence
    ):
        raise KnowledgeError(
            f"verified item '{title}' requires implementation, test, contract, or compatibility evidence; "
            "an accepted-decision record alone supports confidence=accepted"
        )
    rationale = normalize_space(raw.get("rationale"))
    implications = unique_strings(raw.get("implications"))
    context = normalize_space(raw.get("context"))
    alternatives = unique_strings(raw.get("alternatives"))
    consequences = unique_strings(raw.get("consequences"))
    future_use = normalize_future_use(raw.get("future_use"), strict)
    paths = unique_strings(raw.get("paths")) or list(task["paths"])
    symbols = unique_strings(raw.get("symbols")) or list(task["symbols"])
    scopes = normalize_scopes(raw.get("scopes")) or list(task["scopes"])
    topics = normalize_topics(raw.get("topics"), config) or list(task["topics"])
    supersedes = unique_strings(raw.get("supersedes"))
    supersession_reason = normalize_space(raw.get("supersession_reason"))
    operation = normalize_space(raw.get("operation") or "create").lower()
    card_id = normalize_space(raw.get("card_id"))
    expected_revision = raw.get("expected_revision")
    if operation not in {"create", "update"}:
        raise KnowledgeError("item.operation must be create or update")
    if operation == "update":
        if not re.fullmatch(r"K-[A-Za-z0-9-]+", card_id):
            raise KnowledgeError("item.card_id must be an existing K-* identifier for update")
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
            raise KnowledgeError("item.expected_revision must be a positive integer for update")
        if supersedes:
            raise KnowledgeError("updating an unchanged conclusion cannot add supersedes; create a replacement card instead")
    elif card_id or expected_revision is not None:
        raise KnowledgeError("item.card_id and expected_revision require item.operation=update")
    if strict and status == "current":
        for field, value in (("title", title), ("knowledge", knowledge), ("rationale", rationale)):
            if value:
                reject_placeholder(value, f"item.{field}")
        if not final_evidence:
            raise KnowledgeError(f"current item '{title}' requires implementation, test, compatibility, or accepted-decision evidence")
        if not scopes and not paths and not symbols:
            raise KnowledgeError(f"current item '{title}' requires an applicability scope")
        if len(future_use) < 2:
            raise KnowledgeError(f"current item '{title}' requires at least two concrete future-use scenarios")
        if len({stable_json(value) for value in future_use}) < 2:
            raise KnowledgeError(f"current item '{title}' requires two distinct future-use scenarios")
    if category == "decisions":
        if not rationale:
            raise KnowledgeError(f"decision item '{title}' requires rationale")
        if strict and (not context or not alternatives or not consequences):
            raise KnowledgeError(f"decision item '{title}' requires context, alternatives, and consequences")
    if strict and supersedes and not supersession_reason:
        raise KnowledgeError(f"item '{title}' requires supersession_reason because it replaces a long-term conclusion")
    return {
        "operation": operation,
        "card_id": card_id,
        "expected_revision": expected_revision,
        "category": category,
        "title": title,
        "knowledge": knowledge,
        "rationale": rationale,
        "implications": implications,
        "context": context,
        "alternatives": alternatives,
        "consequences": consequences,
        "future_use": future_use,
        "paths": paths,
        "symbols": symbols,
        "scopes": scopes,
        "topics": topics,
        "tags": unique_strings(raw.get("tags")) or list(task["tags"]),
        "evidence": final_evidence,
        "confidence": confidence,
        "status": status,
        "supersedes": supersedes,
        "supersession_reason": supersession_reason,
        "new_card_reason": normalize_space(raw.get("new_card_reason")),
        "pinned": bool(raw.get("pinned", False)),
        "applies_to": normalize_scopes(raw.get("applies_to")),
        "depends_on": normalize_card_dependencies(raw.get("depends_on")),
    }


def normalize_learning_payload(raw: Any, config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        raise KnowledgeError("learning payload must be a JSON object")
    if set(raw) - {"task", "items"}:
        unknown = ", ".join(sorted(set(raw) - {"task", "items"}))
        raise KnowledgeError(f"unknown top-level learning fields: {unknown}")
    task = normalize_task(raw.get("task"), config)
    raw_items = raw.get("items")
    if not isinstance(raw_items, list):
        raise KnowledgeError("learning payload items must be an array")
    items = [normalize_item(item, task, config) for item in raw_items]
    if task["status"] != "completed" and items:
        raise KnowledgeError("only completed tasks may create or reuse durable knowledge cards")
    capture = config.get("capture") if isinstance(config.get("capture"), dict) else {}
    if bool(capture.get("secret_scan", True)):
        secret = detect_secret({"task": task, "items": items})
        if secret:
            raise KnowledgeError(f"learning payload appears to contain a {secret}; remove secrets before capture")
    return task, items


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def item_fingerprint(item: dict[str, Any]) -> str:
    material = {
        "category": item["category"],
        "title": item["title"],
        "knowledge": item["knowledge"],
        "rationale": item["rationale"],
        "implications": item["implications"],
        "context": item["context"],
        "alternatives": item["alternatives"],
        "consequences": item["consequences"],
        "future_use": item["future_use"],
        "scopes": item["scopes"],
        "topics": item["topics"],
        "paths": item["paths"],
        "symbols": item["symbols"],
        "tags": item["tags"],
        "evidence": item["evidence"],
        "confidence": item["confidence"],
        "status": item["status"],
        "supersedes": item["supersedes"],
        "supersession_reason": item["supersession_reason"],
        "pinned": item["pinned"],
    }
    # Absent optional metadata must preserve fingerprints of format-4 records.
    for key in ("applies_to", "depends_on"):
        if item.get(key):
            material[key] = item[key]
    return sha256_text(stable_json(material))


def task_fingerprint(task: dict[str, Any], items: Sequence[dict[str, Any]]) -> str:
    task_content = {
        key: value
        for key, value in task.items()
        if key not in {"id", "update_existing", "expected_revision"}
    }
    material = {
        "task": task_content,
        "items": [
            {
                "fingerprint": item_fingerprint(item),
                "operation": item.get("operation") or "create",
                "card_id": item.get("card_id") or "",
                "expected_revision": item.get("expected_revision"),
            }
            for item in items
        ],
    }
    return sha256_text(stable_json(material))




def make_id(prefix: str, fingerprint: str, timestamp: datetime, sequence: int = 0) -> str:
    base = timestamp.strftime("%Y%m%d-%H%M%S")
    suffix = fingerprint[:8]
    return f"{prefix}-{base}-{sequence:02d}-{suffix}" if sequence else f"{prefix}-{base}-{suffix}"


def render_card_body(item: dict[str, Any], task: dict[str, Any], task_id: str) -> str:
    # Scope, evidence, reuse scenarios and provenance live once in front matter.
    lines = [f"# {item['title']}", "", "## 结论", "", item["knowledge"], ""]
    for heading, key in (("背景", "context"), ("理由", "rationale"), ("影响", "implications"),
                         ("主要替代方案", "alternatives"), ("后果", "consequences")):
        value = item[key]
        if value:
            lines.extend((f"## {heading}", "", markdown_bullets(value) if isinstance(value, list) else value, ""))
    return "\n".join(lines)


def render_task_body(task: dict[str, Any], task_id: str, card_ids: Sequence[str]) -> str:
    lines = [f"# {task['title']}", ""]
    for heading, key in (("请求", "request"), ("处理摘要", "summary"), ("最终结果", "result"), ("验证", "verification")):
        value = task[key]
        if value:
            lines.extend((f"## {heading}", "", markdown_bullets(value) if isinstance(value, list) else value, ""))
    return "\n".join(lines)
