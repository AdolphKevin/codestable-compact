"""CodeStable runtime section: 30 learning."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def knowledge_use_entry_key(value: dict[str, Any]) -> str:
    return stable_json(value)


def merge_task_knowledge_use(
    previous: Sequence[dict[str, Any]],
    current: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep historical use evidence immutable while allowing new evidence to append."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in [*previous, *current]:
        if not isinstance(value, dict):
            continue
        key = knowledge_use_entry_key(value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged


def _learn_locked(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    task, items = normalize_learning_payload(payload, config)
    wiki = wiki_root(root, config)
    categories = configured_categories(config)
    workspace_before_scan = workspace_state_fingerprint(root)
    state_before_scan = knowledge_state_fingerprint(root, config)
    cards, tasks = scan_existing_records(wiki, categories)
    evidence_reader = EvidenceReader(root, config)
    evidence_state = evidence_input_state(cards, items, evidence_reader)
    update_existing = bool(task["update_existing"])
    target_task_id = task["id"] if update_existing else ""
    target_record = tasks.get(target_task_id) if target_task_id else None
    if update_existing and target_record is None:
        raise KnowledgeError(f"task.update_existing references unknown task {target_task_id}")
    if target_record and normalize_space(target_record[1].get("visibility") or "active") == "archived":
        raise KnowledgeError(
            f"task {target_task_id} is archived into {normalize_space(target_record[1].get('consolidated_into'))}; "
            "update the canonical task instead"
        )
    previous_metadata = target_record[1] if target_record else {}
    previous_knowledge_use = [
        value
        for value in (previous_metadata.get("knowledge_use") or [])
        if isinstance(value, dict)
    ]
    previous_knowledge_use_keys = {
        knowledge_use_entry_key(value)
        for value in previous_knowledge_use
    }
    for value in task["knowledge_use"]:
        if value["card_id"] not in cards:
            raise KnowledgeError(f"task.knowledge_use references unknown card {value['card_id']}")
        current_revision = int(cards[value["card_id"]][1].get("revision", 1) or 1)
        historical_entry = knowledge_use_entry_key(value) in previous_knowledge_use_keys
        if value["card_revision"] != current_revision and not historical_entry:
            raise KnowledgeError(
                f"task.knowledge_use card {value['card_id']} revision changed: expected "
                f"{value['card_revision']}, current {current_revision}; run brief again and re-check the evidence"
            )
    if update_existing:
        task["knowledge_use"] = merge_task_knowledge_use(previous_knowledge_use, task["knowledge_use"])
    reference_check = learning_reference_check(root, config, task, items)
    task_fp = task_fingerprint(task, items)
    state_fp = knowledge_state_fingerprint(root, config)
    workspace_fp = workspace_state_fingerprint(root)
    if state_before_scan != state_fp:
        raise KnowledgeError("project knowledge changed while planning learn; retry the command")
    if workspace_before_scan != workspace_fp:
        raise KnowledgeError("project workspace changed while planning learn; retry the command")
    plan: dict[str, Any] | None = None
    if plan_token:
        plan = decode_plan_token(plan_token)
        if normalize_space(plan.get("task_fingerprint")) != task_fp:
            raise KnowledgeError("learn plan token does not match this payload")
        try:
            timestamp = datetime.fromisoformat(normalize_space(plan.get("timestamp")))
        except ValueError as exc:
            raise KnowledgeError("learn plan token has an invalid timestamp") from exc
    else:
        timestamp = now_local()
    if plan and normalize_space(plan.get("state_fingerprint")) != state_fp:
        raise KnowledgeError("project knowledge changed after dry-run; run learn --dry-run again")
    if plan and normalize_space(plan.get("workspace_fingerprint")) != workspace_fp:
        raise KnowledgeError("project workspace changed after dry-run; run learn --dry-run again")
    if plan and plan.get("evidence_state") != evidence_state:
        raise KnowledgeError("referenced evidence changed after dry-run; run learn --dry-run again")
    generated_plan_token = encode_plan_token(task_fp, state_fp, workspace_fp, timestamp)
    token_data = decode_plan_token(generated_plan_token)
    token_data["evidence_state"] = evidence_state
    generated_plan_token = base64.urlsafe_b64encode(stable_json(token_data).encode("utf-8")).decode("ascii")
    idempotency_scope = [(target_task_id, target_record)] if target_record else list(tasks.items())
    for existing_id, record in idempotency_scope:
        if record is None:
            continue
        path, metadata, _ = record
        existing_fingerprint = normalize_space(metadata.get("fingerprint"))
        if existing_fingerprint == task_fp:
            return {
                "ok": True,
                "idempotent": True,
                "dry_run": dry_run,
                "task_id": existing_id,
                "task_revision": int(metadata.get("revision", 1) or 1),
                "task_note": path.relative_to(root).as_posix(),
                "created_cards": [],
                "reused_cards": unique_strings(metadata.get("card_ids")),
                "superseded_cards": [],
                "task_candidates": [],
                "card_candidates": [],
                "index": rebuild_indexes(root, config, dry_run=dry_run),
                "plan_token": generated_plan_token if dry_run else None,
                "reference_check": reference_check,
                "review_queue": knowledge_review(root, config, cards, evidence_reader)["review_queue"],
            }
    current_revision = 0
    if target_record:
        current_revision = int(target_record[1].get("revision", 1) or 1)
        if task["expected_revision"] != current_revision:
            raise KnowledgeError(
                f"task {target_task_id} revision changed: expected {task['expected_revision']}, current {current_revision}; "
                "read the current task-note and run learn --dry-run again"
            )
    previous_source = previous_metadata.get("source") if isinstance(previous_metadata.get("source"), dict) else {}
    merged_source = {**previous_source, **task["source"]}
    merged_new_task_reason = task["new_task_reason"] or normalize_space(previous_metadata.get("new_task_reason"))
    rendered_task = {**task, "source": merged_source, "new_task_reason": merged_new_task_reason}
    fingerprint_to_id: dict[str, str] = {}
    for identifier, (_, metadata, _) in cards.items():
        fingerprint = normalize_space(metadata.get("fingerprint"))
        status = normalize_space(metadata.get("status") or "current")
        if fingerprint and status != "superseded":
            fingerprint_to_id[fingerprint] = identifier

    for item in items:
        if item["operation"] == "update":
            target = cards.get(item["card_id"])
            if target is None:
                raise KnowledgeError(f"item '{item['title']}' updates unknown card {item['card_id']}")
            _, metadata, body = target
            current_card_revision = int(metadata.get("revision", 1) or 1)
            if item["expected_revision"] != current_card_revision:
                raise KnowledgeError(
                    f"card {item['card_id']} revision changed: expected {item['expected_revision']}, "
                    f"current {current_card_revision}; read the card and run learn --dry-run again"
                )
            if normalize_space(metadata.get("status")) != "current":
                raise KnowledgeError(f"only a current card may be updated in place: {item['card_id']}")
            if normalize_space(metadata.get("category")) != item["category"]:
                raise KnowledgeError("card category cannot change during an in-place update")
            if normalize_space(metadata.get("title")) != item["title"]:
                raise KnowledgeError("card title cannot change during an in-place update")
            if normalize_space(extract_section(body, ("结论",))) != normalize_space(item["knowledge"]):
                raise KnowledgeError("card conclusion cannot change during an in-place update; create a replacement with supersedes")
        for superseded_id in item["supersedes"]:
            if superseded_id not in cards:
                raise KnowledgeError(f"item '{item['title']}' supersedes unknown card {superseded_id}")
            if normalize_space(cards[superseded_id][1].get("status")) == "superseded":
                raise KnowledgeError(f"item '{item['title']}' supersedes already-superseded card {superseded_id}")

    timestamp_text = timestamp.isoformat(timespec="seconds")
    task_id = target_task_id or make_id("T", task_fp, timestamp)
    created_plan: list[tuple[str, Path, dict[str, Any], str, dict[str, Any]]] = []
    updated_card_plan: list[tuple[str, Path, dict[str, Any], str, dict[str, Any]]] = []
    reused_cards: list[str] = []
    new_card_ids: list[str] = []
    supersession_plan: list[tuple[str, str]] = []

    deduplicate = bool((config.get("capture") or {}).get("deduplicate", True)) if isinstance(config.get("capture"), dict) else True
    for sequence, item in enumerate(items, start=1):
        fingerprint = item_fingerprint(item)
        if item["operation"] == "update":
            card_id = item["card_id"]
            path, existing_metadata, _ = cards[card_id]
            metadata = dict(existing_metadata)
            old_scope = {
                "revision": int(metadata.get("revision", 1) or 1),
                "updated_at": normalize_space(metadata.get("updated_at")),
                "task_id": normalize_space(metadata.get("task_id")),
                "scopes": metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [],
                "paths": unique_strings(metadata.get("paths")),
                "symbols": unique_strings(metadata.get("symbols")),
                "topics": unique_strings(metadata.get("topics")),
                "applies_to": metadata.get("applies_to") or [],
                "depends_on": metadata.get("depends_on") or [],
            }
            new_scope = {
                "scopes": item["scopes"],
                "paths": item["paths"],
                "symbols": item["symbols"],
                "topics": item["topics"],
                "applies_to": item["applies_to"],
                "depends_on": item["depends_on"],
            }
            scope_history = metadata.get("scope_history") if isinstance(metadata.get("scope_history"), list) else []
            if any(old_scope[key] != new_scope[key] for key in new_scope):
                scope_history = [*scope_history, old_scope]
            metadata.update(
                {
                    "updated_at": timestamp_text,
                    "revision": int(metadata.get("revision", 1) or 1) + 1,
                    "scope_history": scope_history,
                    "updated_by_task_id": task_id,
                    "fingerprint": fingerprint,
                    "confidence": item["confidence"],
                    "pinned": item["pinned"],
                    "tags": item["tags"],
                    "topics": item["topics"],
                    "scopes": item["scopes"],
                    "paths": item["paths"],
                    "symbols": item["symbols"],
                    "future_use": item["future_use"],
                    "evidence": item["evidence"],
                    "applies_to": item["applies_to"],
                    "depends_on": item["depends_on"],
                }
            )
            body = render_card_body(item, rendered_task, task_id)
            updated_card_plan.append((card_id, path, metadata, body, item))
            new_card_ids.append(card_id)
            continue
        if deduplicate and fingerprint in fingerprint_to_id:
            card_id = fingerprint_to_id[fingerprint]
            if card_id in cards and card_id not in reused_cards:
                reused_cards.append(card_id)
            if card_id not in new_card_ids:
                new_card_ids.append(card_id)
            continue
        card_id = make_id("K", fingerprint, timestamp, sequence)
        metadata = {
            "id": card_id,
            "type": "knowledge-card",
            "category": item["category"],
            "title": item["title"],
            "status": item["status"],
            "confidence": item["confidence"],
            "created_at": timestamp_text,
            "updated_at": timestamp_text,
            "revision": 1,
            "scope_history": [],
            "task_id": task_id,
            "fingerprint": fingerprint,
            "pinned": item["pinned"],
            "tags": item["tags"],
            "topics": item["topics"],
            "scopes": item["scopes"],
            "paths": item["paths"],
            "symbols": item["symbols"],
            "future_use": item["future_use"],
            "evidence": item["evidence"],
            "supersedes": item["supersedes"],
            "supersession_reason": item["supersession_reason"],
            "superseded_by": [],
            **{key: item[key] for key in ("applies_to", "depends_on") if item[key]},
        }
        relative = card_filename(item, card_id)
        body = render_card_body(item, rendered_task, task_id)
        created_plan.append((card_id, wiki / relative, metadata, body, item))
        new_card_ids.append(card_id)
        fingerprint_to_id[fingerprint] = card_id
        for old_id in item["supersedes"]:
            supersession_plan.append((old_id, card_id))

    previous_card_ids = unique_strings(previous_metadata.get("card_ids"))
    all_card_ids = unique_strings([*previous_card_ids, *new_card_ids])
    task_revision = current_revision + 1
    task_metadata = {
        "id": task_id,
        "type": "task-note",
        "title": task["title"],
        "kind": task["kind"],
        "task_status": task["status"],
        "created_at": normalize_space(previous_metadata.get("created_at")) or timestamp_text,
        "updated_at": timestamp_text,
        "revision": task_revision,
        "visibility": normalize_space(previous_metadata.get("visibility") or "active"),
        "fingerprint": task_fp,
        "tags": task["tags"],
        "topics": task["topics"],
        "scopes": task["scopes"],
        "paths": task["paths"],
        "symbols": task["symbols"],
        "card_ids": all_card_ids,
        "deliverable": task["deliverable"],
        "new_task_reason": merged_new_task_reason,
        "knowledge_summary": task["knowledge_summary"],
        "knowledge_use": task["knowledge_use"],
        "consolidated_from": unique_strings(previous_metadata.get("consolidated_from")),
        "source": merged_source,
    }
    task_path = target_record[0] if target_record else wiki / task_note_filename(task, task_id, timestamp)
    task_body = render_task_body(rendered_task, task_id, all_card_ids)

    planned_new_paths = [path for _, path, _, _, _ in created_plan]
    if not target_record:
        planned_new_paths.append(task_path)
    collisions = [path.relative_to(root).as_posix() for path in planned_new_paths if source_exists(path)]
    if collisions:
        raise KnowledgeError("planned knowledge paths already exist: " + ", ".join(collisions))

    task_candidates = [] if update_existing else task_similarity_candidates(task, tasks, root)
    requires_new_task_reason = bool(task_candidates and not task["new_task_reason"])
    card_candidates = card_similarity_candidates(items, cards, root)
    requires_new_card_reason = any(value.get("blocking") for value in card_candidates)
    result = {
        "ok": True,
        "idempotent": False,
        "dry_run": dry_run,
        "task_id": task_id,
        "task_revision": task_revision,
        "updated_existing_task": update_existing,
        "task_note": task_path.relative_to(root).as_posix(),
        "created_cards": [
            {"id": card_id, "path": path.relative_to(root).as_posix(), "category": item["category"], "title": item["title"]}
            for card_id, path, _, _, item in created_plan
        ],
        "updated_cards": [
            {"id": card_id, "path": path.relative_to(root).as_posix(), "revision": metadata["revision"]}
            for card_id, path, metadata, _, _ in updated_card_plan
        ],
        "reused_cards": reused_cards,
        "superseded_cards": [{"id": old_id, "superseded_by": new_id} for old_id, new_id in supersession_plan],
        "task_candidates": task_candidates,
        "card_candidates": card_candidates,
        "requires_new_task_reason": requires_new_task_reason,
        "requires_new_card_reason": requires_new_card_reason,
        "apply_allowed": not requires_new_task_reason and not requires_new_card_reason,
        "plan_token": generated_plan_token if dry_run and not requires_new_task_reason and not requires_new_card_reason else None,
        "reference_check": reference_check,
    }
    projected_cards = dict(cards)
    for identifier, path, metadata, body, _ in [*created_plan, *updated_card_plan]:
        projected_cards[identifier] = (path, metadata, body)
    for old_id, new_id in supersession_plan:
        old_path, old_meta, old_body = projected_cards[old_id]
        projected_cards[old_id] = (old_path, {**old_meta, "status": "superseded",
            "updated_at": timestamp_text, "superseded_by": [*unique_strings(old_meta.get("superseded_by")), new_id]}, old_body)
    review = knowledge_review(root, config, projected_cards, evidence_reader)
    result["review_queue"] = review["review_queue"]
    result["evidence_validity"] = review["cards"]
    # The token covers referenced files even outside this repository and ignored reports.
    if evidence_input_state(cards, items, EvidenceReader(root, config)) != evidence_state:
        raise KnowledgeError("referenced evidence changed while planning learn; retry the command")
    if result["task_candidates"]:
        result["recommendation"] = "update-existing-task"
    if dry_run:
        result["index"] = projected_index_plan(
            root,
            config,
            cards,
            tasks,
            created_plan,
            updated_card_plan,
            task_path,
            task_metadata,
            task_body,
            supersession_plan,
            timestamp_text,
            replaced_task_id=target_task_id or None,
        )
        return result

    if requires_new_task_reason:
        raise KnowledgeError(
            "a likely continuation task already exists; update it by id/revision or provide task.new_task_reason "
            "explaining the independent goal before applying"
        )
    if requires_new_card_reason:
        raise KnowledgeError(
            "a likely equivalent current card already exists; reuse or update it, or provide item.new_card_reason "
            "explaining the orthogonal long-term conclusion before applying"
        )

    _, current_index_outputs = build_index_outputs(root, config)
    mutation_paths = set(planned_new_paths)
    mutation_paths.update(path for _, path, _, _, _ in updated_card_plan)
    mutation_paths.add(task_path)
    mutation_paths.update(cards[old_id][0] for old_id, _ in supersession_plan)
    mutation_paths.update(current_index_outputs)
    snapshot = {
        path: source_text(path, encoding="utf-8") if source_is_file(path) else None
        for path in mutation_paths
    }
    transaction = create_recovery_journal(root, wiki, task_id, snapshot)
    try:
        for _, path, metadata, body, _ in created_plan:
            atomic_write_text(path, render_front_matter(metadata, body))
        for _, path, metadata, body, _ in updated_card_plan:
            atomic_write_text(path, render_front_matter(metadata, body))
        atomic_write_text(task_path, render_front_matter(task_metadata, task_body))
        for old_id, new_id in supersession_plan:
            old_path = cards[old_id][0]
            update_card_supersession(old_path, new_id, timestamp_text, dry_run=False)
        result["index"] = rebuild_indexes(root, config, dry_run=False)
        atomic_write_text(transaction / "COMMITTED", "committed\n")
    except Exception:
        restore_snapshot(snapshot, wiki)
        remove_recovery_journal(transaction)
        raise
    remove_recovery_journal(transaction)
    return result


def learn(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if dry_run:
        if plan_token:
            raise KnowledgeError("plan_token is only valid when applying learn")
        return _learn_locked(root, config, payload, dry_run=True)
    wiki = wiki_root(root, config)
    lock = acquire_lock(root, wiki)
    try:
        return _learn_locked(root, config, payload, dry_run=False, plan_token=plan_token)
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def normalize_consolidation_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("consolidation payload must be a JSON object")
    unknown = set(raw) - {"canonical_task_id", "expected_revision", "duplicates", "reason"}
    if unknown:
        raise KnowledgeError("unknown consolidation fields: " + ", ".join(sorted(unknown)))
    canonical_id = normalize_space(raw.get("canonical_task_id"))
    expected_revision = raw.get("expected_revision")
    reason = normalize_space(raw.get("reason"))
    duplicates_raw = raw.get("duplicates")
    if not re.fullmatch(r"T-[A-Za-z0-9-]+", canonical_id):
        raise KnowledgeError("canonical_task_id must be a T-* identifier")
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
        raise KnowledgeError("expected_revision must be a positive integer")
    if not reason:
        raise KnowledgeError("reason is required")
    if not isinstance(duplicates_raw, list) or not duplicates_raw:
        raise KnowledgeError("duplicates must be a non-empty array")
    duplicates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in duplicates_raw:
        if not isinstance(value, dict) or set(value) - {"id", "expected_revision"}:
            raise KnowledgeError("each duplicate must contain only id and expected_revision")
        identifier = normalize_space(value.get("id"))
        revision = value.get("expected_revision")
        if not re.fullmatch(r"T-[A-Za-z0-9-]+", identifier):
            raise KnowledgeError("duplicate id must be a T-* identifier")
        if identifier == canonical_id:
            raise KnowledgeError("canonical task cannot also be a duplicate")
        if identifier in seen:
            raise KnowledgeError(f"duplicate task listed more than once: {identifier}")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise KnowledgeError(f"duplicate {identifier} expected_revision must be a positive integer")
        seen.add(identifier)
        duplicates.append({"id": identifier, "expected_revision": revision})
    payload = {
        "canonical_task_id": canonical_id,
        "expected_revision": expected_revision,
        "duplicates": duplicates,
        "reason": reason,
    }
    secret = detect_secret(payload)
    if secret:
        raise KnowledgeError(f"consolidation payload appears to contain a {secret}")
    return payload


def render_consolidated_task_body(body: str, duplicate_ids: Sequence[str], reason: str) -> str:
    retained = re.sub(r"\n## 已折叠的历史任务\n.*\Z", "", body.rstrip(), flags=re.DOTALL)
    lines = [retained, "", "## 已折叠的历史任务", "", f"整理理由：{reason}", ""]
    lines.extend(f"- `{identifier}`" for identifier in duplicate_ids)
    return "\n".join(lines) + "\n"


def render_archived_task_body(
    title: str,
    identifier: str,
    canonical_id: str,
    metadata: dict[str, Any],
    original_body: str,
    reason: str,
) -> str:
    verification = extract_section(original_body, ("验证",))
    request = extract_section(original_body, ("请求",))
    result = extract_section(original_body, ("最终结果",))
    source = metadata.get("source") if isinstance(metadata.get("source"), dict) else {}
    return f"""# {title}

> 本记录已折叠到逻辑任务 `{canonical_id}`；默认 brief、recent tasks 与根索引不再展示本记录。

## 整理依据

{reason}

## 保留的审计信息

- 原任务 ID：`{identifier}`
- canonical task：`{canonical_id}`
- 原正文 SHA-256：`{sha256_text(original_body)}`
- 关联知识卡片：{', '.join(f'`{value}`' for value in unique_strings(metadata.get('card_ids'))) or '无'}

### 原验证依据

{verification or '- 未记录'}

### 原请求与结果

- 请求：{request or '未记录'}
- 结果：{result or '未记录'}

### 原来源

```json
{json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True)}
```
"""


def _consolidate_locked(
    root: Path,
    config: dict[str, Any],
    raw: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    payload = normalize_consolidation_payload(raw)
    wiki = wiki_root(root, config)
    workspace_before = workspace_state_fingerprint(root)
    state_before = knowledge_state_fingerprint(root, config)
    cards, tasks = scan_existing_records(wiki, configured_categories(config))
    operation_fp = sha256_text(stable_json(payload))
    state_fp = knowledge_state_fingerprint(root, config)
    workspace_fp = workspace_state_fingerprint(root)
    if state_before != state_fp or workspace_before != workspace_fp:
        raise KnowledgeError("project state changed while planning consolidate; retry the command")
    plan: dict[str, Any] | None = None
    if plan_token:
        plan = decode_plan_token(plan_token)
        if normalize_space(plan.get("task_fingerprint")) != operation_fp:
            raise KnowledgeError("consolidate plan token does not match this payload")
        if normalize_space(plan.get("state_fingerprint")) != state_fp:
            raise KnowledgeError("project knowledge changed after consolidate --dry-run; run it again")
        if normalize_space(plan.get("workspace_fingerprint")) != workspace_fp:
            raise KnowledgeError("project workspace changed after consolidate --dry-run; run it again")
        try:
            timestamp = datetime.fromisoformat(normalize_space(plan.get("timestamp")))
        except ValueError as exc:
            raise KnowledgeError("consolidate plan token has an invalid timestamp") from exc
    else:
        timestamp = now_local()
    token = encode_plan_token(operation_fp, state_fp, workspace_fp, timestamp)
    canonical_id = payload["canonical_task_id"]
    canonical = tasks.get(canonical_id)
    if canonical is None:
        raise KnowledgeError(f"unknown canonical task {canonical_id}")
    if normalize_space(canonical[1].get("visibility") or "active") == "archived":
        raise KnowledgeError(f"canonical task {canonical_id} is archived")
    duplicate_ids = [value["id"] for value in payload["duplicates"]]
    duplicate_records: list[tuple[str, Path, dict[str, Any], str]] = []
    already_archived = True
    for value in payload["duplicates"]:
        record = tasks.get(value["id"])
        if record is None:
            raise KnowledgeError(f"unknown duplicate task {value['id']}")
        visibility = normalize_space(record[1].get("visibility") or "active")
        consolidated_into = normalize_space(record[1].get("consolidated_into"))
        if visibility == "archived" and consolidated_into != canonical_id:
            raise KnowledgeError(f"task {value['id']} is already archived into {consolidated_into}")
        if visibility != "archived":
            already_archived = False
        duplicate_records.append((value["id"], record[0], record[1], record[2]))
    consolidated_from = unique_strings(canonical[1].get("consolidated_from"))
    if already_archived and all(identifier in consolidated_from for identifier in duplicate_ids):
        return {
            "ok": True, "idempotent": True, "dry_run": dry_run,
            "canonical_task_id": canonical_id, "archived_task_ids": duplicate_ids,
            "plan_token": token if dry_run else None,
        }
    canonical_revision = int(canonical[1].get("revision", 1) or 1)
    if canonical_revision != payload["expected_revision"]:
        raise KnowledgeError(f"canonical task {canonical_id} revision changed: expected {payload['expected_revision']}, current {canonical_revision}")
    for expected, record in zip(payload["duplicates"], duplicate_records):
        revision = int(record[2].get("revision", 1) or 1)
        if normalize_space(record[2].get("visibility") or "active") != "archived" and revision != expected["expected_revision"]:
            raise KnowledgeError(f"duplicate task {expected['id']} revision changed: expected {expected['expected_revision']}, current {revision}")

    timestamp_text = timestamp.isoformat(timespec="seconds")
    canonical_metadata = dict(canonical[1])
    canonical_metadata["revision"] = canonical_revision + 1
    canonical_metadata["updated_at"] = timestamp_text
    canonical_metadata["visibility"] = "active"
    canonical_metadata["consolidated_from"] = unique_strings([*consolidated_from, *duplicate_ids])
    canonical_metadata["card_ids"] = unique_strings([
        *unique_strings(canonical_metadata.get("card_ids")),
        *(card_id for _, _, metadata, _ in duplicate_records for card_id in unique_strings(metadata.get("card_ids"))),
    ])
    canonical_metadata["consolidation_fingerprint"] = operation_fp
    canonical_body = render_consolidated_task_body(canonical[2], canonical_metadata["consolidated_from"], payload["reason"])
    mutations: list[tuple[Path, dict[str, Any], str]] = [(canonical[0], canonical_metadata, canonical_body)]
    for identifier, path, metadata, body in duplicate_records:
        archived_metadata = dict(metadata)
        archived_metadata["updated_at"] = timestamp_text
        archived_metadata["revision"] = int(metadata.get("revision", 1) or 1) + 1
        archived_metadata["visibility"] = "archived"
        archived_metadata["consolidated_into"] = canonical_id
        archived_metadata["consolidation_fingerprint"] = operation_fp
        archived_body = render_archived_task_body(
            normalize_space(metadata.get("title")) or identifier,
            identifier, canonical_id, metadata, body, payload["reason"],
        )
        mutations.append((path, archived_metadata, archived_body))

    projected_entries = []
    mutation_by_path = {path: (metadata, body) for path, metadata, body in mutations}
    for entry in collect_index_entries(root, config):
        path = root / entry["path"]
        if path in mutation_by_path:
            metadata, body = mutation_by_path[path]
            projected_entries.append(index_entry_for(path, root, metadata, body, render_front_matter(metadata, body)))
        else:
            projected_entries.append(entry)
    projected_entries.sort(key=lambda item: (0 if item["type"] == "knowledge-card" else 1, item.get("category") or "", item.get("created_at") or "", item.get("id") or ""))
    projected_outputs = render_index_outputs(root, config, projected_entries)
    changed_indexes = [
        path.relative_to(root).as_posix()
        for path, content in projected_outputs.items()
        if (source_text(path, encoding="utf-8") if source_is_file(path) else None) != content
    ]
    result = {
        "ok": True, "idempotent": False, "dry_run": dry_run,
        "canonical_task_id": canonical_id,
        "canonical_revision": canonical_metadata["revision"],
        "archived_task_ids": duplicate_ids,
        "changed_task_notes": [path.relative_to(root).as_posix() for path, _, _ in mutations],
        "index": {"entries": len(projected_entries), "changed": changed_indexes, "dry_run": dry_run},
        "plan_token": token if dry_run else None,
    }
    if dry_run:
        return result

    current_outputs = build_index_outputs(root, config)[1]
    mutation_paths = {path for path, _, _ in mutations} | set(current_outputs)
    snapshot = {path: source_text(path, encoding="utf-8") if source_is_file(path) else None for path in mutation_paths}
    transaction = create_recovery_journal(root, wiki, f"C-{operation_fp[:16]}", snapshot)
    try:
        for path, metadata, body in mutations:
            atomic_write_text(path, render_front_matter(metadata, body))
        result["index"] = rebuild_indexes(root, config, dry_run=False)
        atomic_write_text(transaction / "COMMITTED", "committed\n")
    except Exception:
        restore_snapshot(snapshot, wiki)
        remove_recovery_journal(transaction)
        raise
    remove_recovery_journal(transaction)
    return result


def consolidate(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if dry_run:
        if plan_token:
            raise KnowledgeError("plan_token is only valid when applying consolidate")
        return _consolidate_locked(root, config, payload, dry_run=True)
    wiki = wiki_root(root, config)
    lock = acquire_lock(root, wiki)
    try:
        return _consolidate_locked(root, config, payload, dry_run=False, plan_token=plan_token)
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
