"""CodeStable runtime section: 60 governance."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def topics_list_payload(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """List configured canonical topic names without reading card conclusions."""
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, _ = scan_existing_records(wiki, configured_categories(config))
    aliases = topic_aliases(config)
    counts: dict[str, int] = {}
    categories: dict[str, set[str]] = {}
    for _, (_, metadata, _) in cards.items():
        if normalize_space(metadata.get("status")) != "current":
            continue
        category = normalize_space(metadata.get("category"))
        for raw_topic in unique_strings(metadata.get("topics")):
            topic = aliases.get(raw_topic.casefold())
            if not topic:
                continue
            counts[topic] = counts.get(topic, 0) + 1
            categories.setdefault(topic, set()).add(category)
    topics = []
    for name, definition in sorted(configured_topics(config).items()):
        topics.append(
            {
                "name": name,
                "label": definition["label"],
                "summary": definition["summary"],
                "aliases": list(definition.get("aliases") or []),
                "replaces": list(definition.get("replaces") or []),
                "current_cards": counts.get(name, 0),
                "categories": sorted(categories.get(name, set())),
            }
        )
    return {
        "ok": True,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "governance": topic_governance(config),
        "count": len(topics),
        "topics": topics,
        "usage": "pass a listed name or alias to brief --topic; omit --topic when uncertain",
    }


def render_topics_list_text(payload: dict[str, Any]) -> str:
    lines = ["# CodeStable business topics", ""]
    governance = payload.get("governance") or {}
    lines.append(f"Governance: {governance.get('mode', 'disabled')} · configured: {payload.get('count', 0)}")
    lines.append("")
    if not payload.get("topics"):
        lines.append("No business topics are configured. Omit --topic and rely on task, path, symbol, and repository scope.")
    for topic in payload.get("topics") or []:
        label = topic.get("label") or topic["name"]
        lines.append(f"- `{topic['name']}` — {label}")
        if topic.get("summary"):
            lines.append(f"  - {topic['summary']}")
        if topic.get("aliases"):
            lines.append("  - aliases: " + ", ".join(f"`{value}`" for value in topic["aliases"]))
        lines.append(
            f"  - current cards: {topic.get('current_cards', 0)}; categories: "
            + (", ".join(topic.get("categories") or []) or "none")
        )
    lines.extend(("", "Use only a listed name or alias. If uncertain, omit --topic; brief will still use its other query signals.", ""))
    return "\n".join(lines)


def topics_suggest_payload(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Suggest reproducible topic candidates from structured tags and scope prefixes."""
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, tasks = scan_existing_records(wiki, configured_categories(config))
    known = topic_aliases(config)
    signals: dict[tuple[str, str], set[str]] = {}
    categories: dict[tuple[str, str], set[str]] = {}
    for card_id, (_, metadata, _) in cards.items():
        if normalize_space(metadata.get("status")) != "current":
            continue
        category = normalize_space(metadata.get("category"))
        for tag in unique_strings(metadata.get("tags")):
            name = slugify(tag).casefold()
            if REPOSITORY_NAME_PATTERN.fullmatch(name):
                signals.setdefault(("shared-tag", name), set()).add(card_id)
                categories.setdefault(("shared-tag", name), set()).add(category)
        raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            scopes = normalize_scopes(raw_scopes)
        except KnowledgeError:
            scopes = []
        for scope in scopes or path_scopes(unique_strings(metadata.get("paths")), []):
            parts = [part for part in PurePosixPath(scope.get("path") or "").parts if part not in PATH_SIGNAL_STOPWORDS]
            if not parts:
                continue
            name = slugify(parts[0]).casefold()
            if REPOSITORY_NAME_PATTERN.fullmatch(name):
                signals.setdefault(("shared-scope-prefix", name), set()).add(card_id)
                categories.setdefault(("shared-scope-prefix", name), set()).add(category)
    for task_id, (_, metadata, _) in tasks.items():
        linked = [card_id for card_id in unique_strings(metadata.get("card_ids")) if card_id in cards]
        linked_current = [
            card_id for card_id in linked if normalize_space(cards[card_id][1].get("status")) == "current"
        ]
        linked_categories = {normalize_space(cards[card_id][1].get("category")) for card_id in linked_current}
        if len(linked_current) < 2 or len(linked_categories) < 2:
            continue
        stable_tags = unique_strings(metadata.get("tags"))
        name = slugify(stable_tags[0] if stable_tags else f"task-{task_id[-8:]}").casefold()
        if not REPOSITORY_NAME_PATTERN.fullmatch(name):
            continue
        signals.setdefault(("shared-task-link", name), set()).update(linked_current)
        categories.setdefault(("shared-task-link", name), set()).update(linked_categories)
    suggestions: list[dict[str, Any]] = []
    for (basis, name), card_ids in sorted(signals.items()):
        if name in known or len(card_ids) < 2 or len(categories[(basis, name)]) < 2:
            continue
        suggestions.append(
            {
                "name": name,
                "basis": basis,
                "card_ids": sorted(card_ids),
                "categories": sorted(categories[(basis, name)]),
                "proposal": {
                    "name": name,
                    "label": name.replace("-", " ").title(),
                    "summary": f"Review and replace: deterministic candidate from {basis} '{name}'.",
                    "aliases": [],
                    "replaces": [],
                },
            }
        )
    return {
        "ok": True,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "governance": topic_governance(config),
        "suggestions": suggestions,
        "method": "shared structured tags, repository-relative scope prefixes, or source-task links across at least two categories",
        "limits": [
            "suggestions are navigation candidates, not semantic conclusions",
            "no card or configuration is modified; a human must edit and dry-run an update payload",
        ],
    }


def normalize_topics_update_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("topics update payload must be an object")
    unknown = set(raw) - {"mode", "minimum_coverage", "review_max_age_days", "upsert_topics", "assignments"}
    if unknown:
        raise KnowledgeError("unknown topics update fields: " + ", ".join(sorted(unknown)))
    mode = normalize_space(raw.get("mode")).lower()
    if mode and mode not in {"disabled", "manual", "required"}:
        raise KnowledgeError("topics update mode must be disabled, manual, or required")
    minimum = raw.get("minimum_coverage")
    if minimum is not None:
        if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not 0 <= float(minimum) <= 1:
            raise KnowledgeError("topics update minimum_coverage must be between 0 and 1")
        minimum = float(minimum)
    review_age = raw.get("review_max_age_days")
    if review_age is not None and (
        not isinstance(review_age, int) or isinstance(review_age, bool) or review_age < 1 or review_age > 3650
    ):
        raise KnowledgeError("topics update review_max_age_days must be an integer from 1 to 3650")
    raw_topics = raw.get("upsert_topics") or []
    if not isinstance(raw_topics, list):
        raise KnowledgeError("topics update upsert_topics must be an array")
    upserts: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for value in raw_topics:
        if not isinstance(value, dict) or set(value) - {"name", "label", "summary", "aliases", "replaces"}:
            raise KnowledgeError("each topic upsert accepts name, label, summary, aliases, and replaces")
        name = normalize_space(value.get("name")).casefold()
        label = normalize_space(value.get("label"))
        summary = normalize_space(value.get("summary"))
        aliases = [item.casefold() for item in unique_strings(value.get("aliases"))]
        replaces = [item.casefold() for item in unique_strings(value.get("replaces"))]
        if not REPOSITORY_NAME_PATTERN.fullmatch(name) or name in seen_topics:
            raise KnowledgeError(f"invalid or duplicate topic name: {name!r}")
        if not label or not summary:
            raise KnowledgeError(f"topic {name} requires a human-readable label and navigation summary")
        reject_placeholder(summary, f"topic {name} summary")
        for alias in [*aliases, *replaces]:
            if not REPOSITORY_NAME_PATTERN.fullmatch(alias) or alias == name:
                raise KnowledgeError(f"topic {name} has invalid alias or replacement: {alias!r}")
        seen_topics.add(name)
        upserts.append(
            {"name": name, "label": label, "summary": summary, "aliases": aliases, "replaces": replaces}
        )
    raw_assignments = raw.get("assignments") or []
    if not isinstance(raw_assignments, list):
        raise KnowledgeError("topics update assignments must be an array")
    assignments: list[dict[str, Any]] = []
    seen_cards: set[str] = set()
    for value in raw_assignments:
        if not isinstance(value, dict) or set(value) - {"card_id", "expected_revision", "topics"}:
            raise KnowledgeError("each topic assignment accepts card_id, expected_revision, and topics")
        card_id = normalize_space(value.get("card_id"))
        revision = value.get("expected_revision")
        if not re.fullmatch(r"K-[A-Za-z0-9-]+", card_id) or card_id in seen_cards:
            raise KnowledgeError(f"invalid or duplicate topic assignment card_id: {card_id!r}")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise KnowledgeError(f"topic assignment {card_id} requires a positive expected_revision")
        seen_cards.add(card_id)
        assignments.append(
            {"card_id": card_id, "expected_revision": revision, "topics": [item.casefold() for item in unique_strings(value.get("topics"))]}
        )
    normalized = {
        "mode": mode,
        "minimum_coverage": minimum,
        "review_max_age_days": review_age,
        "upsert_topics": upserts,
        "assignments": assignments,
    }
    secret = detect_secret(normalized)
    if secret:
        raise KnowledgeError(f"topics update payload appears to contain a {secret}")
    return normalized


def _topics_update_locked(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool,
    plan_token: str | None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    normalized = normalize_topics_update_payload(payload)
    operation_fp = sha256_text(stable_json(normalized))
    state_fp = knowledge_state_fingerprint(root, config)
    workspace_fp = workspace_state_fingerprint(root)
    plan = decode_plan_token(plan_token) if plan_token else None
    if plan and normalize_space(plan.get("task_fingerprint")) != f"topics:{operation_fp}":
        raise KnowledgeError("topics plan token does not match this payload")
    if plan and normalize_space(plan.get("state_fingerprint")) != state_fp:
        raise KnowledgeError("project knowledge changed after topics dry-run; run it again")
    if plan and normalize_space(plan.get("workspace_fingerprint")) != workspace_fp:
        raise KnowledgeError("project workspace changed after topics dry-run; run it again")
    if plan:
        try:
            timestamp = datetime.fromisoformat(normalize_space(plan.get("timestamp")))
        except ValueError as exc:
            raise KnowledgeError("topics plan token has an invalid timestamp") from exc
    else:
        timestamp = now_local()
    token = encode_plan_token(f"topics:{operation_fp}", state_fp, workspace_fp, timestamp)
    projected_config = json.loads(json.dumps(config))
    wiki_config = projected_config.setdefault("wiki", {})
    definitions = wiki_config.setdefault("topics", {})
    if not isinstance(definitions, dict):
        definitions = {}
        wiki_config["topics"] = definitions
    topic_history = wiki_config.setdefault("topic_history", [])
    if not isinstance(topic_history, list):
        topic_history = []
        wiki_config["topic_history"] = topic_history
    existing_names = set(configured_topics(projected_config))
    for topic in normalized["upsert_topics"]:
        missing_replacements = [value for value in topic["replaces"] if value not in existing_names]
        if missing_replacements:
            raise KnowledgeError(
                f"topic {topic['name']} replaces unknown topics: {', '.join(missing_replacements)}"
            )
        aliases = unique_strings([*topic["aliases"], *topic["replaces"]])
        for replaced in topic["replaces"]:
            previous = definitions.pop(replaced)
            topic_history.append(
                {
                    "name": replaced,
                    "definition": previous,
                    "replaced_by": topic["name"],
                    "changed_at": timestamp.isoformat(timespec="seconds"),
                }
            )
        definitions[topic["name"]] = {
            "label": topic["label"],
            "summary": topic["summary"],
            "aliases": aliases,
            "replaces": topic["replaces"],
        }
        existing_names.add(topic["name"])
    alias_owners: dict[str, str] = {}
    for name, definition in configured_topics(projected_config).items():
        for alias in [name, *(definition.get("aliases") or [])]:
            owner = alias_owners.get(alias)
            if owner and owner != name:
                raise KnowledgeError(f"topic alias {alias!r} is claimed by both {owner} and {name}")
            alias_owners[alias] = name
    governance = wiki_config.setdefault("topic_governance", {})
    if not isinstance(governance, dict):
        governance = {}
        wiki_config["topic_governance"] = governance
    if normalized["mode"]:
        governance["mode"] = normalized["mode"]
    if normalized["minimum_coverage"] is not None:
        governance["minimum_coverage"] = normalized["minimum_coverage"]
    if normalized["review_max_age_days"] is not None:
        governance["review_max_age_days"] = normalized["review_max_age_days"]

    aliases = topic_aliases(projected_config)
    cards, _ = scan_existing_records(wiki_root(root, config), configured_categories(config))
    timestamp_text = timestamp.isoformat(timespec="seconds")
    updates: list[tuple[str, Path, dict[str, Any], str]] = []
    for assignment in normalized["assignments"]:
        record = cards.get(assignment["card_id"])
        if record is None:
            raise KnowledgeError(f"topics assignment references unknown card {assignment['card_id']}")
        path, metadata, body = record
        revision = int(metadata.get("revision", 1) or 1)
        if revision != assignment["expected_revision"]:
            raise KnowledgeError(
                f"card {assignment['card_id']} revision changed: expected {assignment['expected_revision']}, current {revision}"
            )
        if normalize_space(metadata.get("status")) != "current":
            raise KnowledgeError(f"topics bulk assignment only updates current cards: {assignment['card_id']}")
        unknown_topics = [value for value in assignment["topics"] if value not in aliases]
        if unknown_topics:
            raise KnowledgeError("topic assignment uses unknown topics: " + ", ".join(unknown_topics))
        assigned_topics = unique_strings([aliases[value] for value in assignment["topics"]])
        old_topics = unique_strings(metadata.get("topics"))
        if old_topics == assigned_topics:
            continue
        updated = dict(metadata)
        history = updated.get("topic_history") if isinstance(updated.get("topic_history"), list) else []
        updated["topic_history"] = [
            *history,
            {"revision": revision, "updated_at": normalize_space(metadata.get("updated_at")), "topics": old_topics},
        ]
        updated["topics"] = assigned_topics
        updated["updated_at"] = timestamp_text
        updated["revision"] = revision + 1
        updated["fingerprint"] = sha256_text(
            stable_json({"previous": normalize_space(metadata.get("fingerprint")), "topics": assigned_topics})
        )
        updates.append((assignment["card_id"], path, updated, body))

    config_path = root / ".codestable" / "config.json"
    config_changed = json_dump(projected_config) != source_text(config_path, encoding="utf-8")
    projected_entries = collect_index_entries(root, config)
    updates_by_id = {card_id: (path, metadata, body) for card_id, path, metadata, body in updates}
    for index, entry in enumerate(projected_entries):
        replacement = updates_by_id.get(entry.get("id"))
        if replacement:
            path, metadata, body = replacement
            projected_entries[index] = index_entry_for(path, root, metadata, body, render_front_matter(metadata, body))
    outputs = render_index_outputs(root, projected_config, projected_entries)
    index_changed = [
        path.relative_to(root).as_posix()
        for path, content in outputs.items()
        if not source_is_file(path) or source_text(path, encoding="utf-8") != content
    ]
    result = {
        "ok": True,
        "dry_run": dry_run,
        "read_only": dry_run,
        "tool_version": TOOL_VERSION,
        "plan_token": token if dry_run else None,
        "configuration_changed": config_changed,
        "updated_cards": [
            {"id": card_id, "path": path.relative_to(root).as_posix(), "revision": metadata["revision"]}
            for card_id, path, metadata, _ in updates
        ],
        "index": {"changed": index_changed, "dry_run": dry_run},
        "idempotent": not config_changed and not updates and not index_changed,
    }
    if dry_run:
        return result
    mutation_paths = {path for _, path, _, _ in updates}
    mutation_paths.update(outputs)
    if config_changed:
        mutation_paths.add(config_path)
    snapshot = {path: source_text(path, encoding="utf-8") if source_is_file(path) else None for path in mutation_paths}
    transaction = create_recovery_journal(root, wiki_root(root, config), f"TOPICS-{operation_fp[:16]}", snapshot)
    try:
        if config_changed:
            atomic_write_text(config_path, json_dump(projected_config))
        for _, path, metadata, body in updates:
            atomic_write_text(path, render_front_matter(metadata, body))
        for path, content in outputs.items():
            atomic_write_text(path, content)
        atomic_write_text(transaction / "COMMITTED", "committed\n")
    except Exception:
        restore_snapshot(snapshot, wiki_root(root, config))
        remove_recovery_journal(transaction)
        raise
    remove_recovery_journal(transaction)
    return result


def topics_update(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    if dry_run:
        if plan_token:
            raise KnowledgeError("plan_token is only valid when applying a topics update")
        return _topics_update_locked(root, config, payload, dry_run=True, plan_token=None)
    if not plan_token:
        raise KnowledgeError("topics update apply requires the plan_token returned by --dry-run")
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    lock = acquire_lock(root, wiki)
    try:
        return _topics_update_locked(root, config, payload, dry_run=False, plan_token=plan_token)
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def local_runtime_alignment(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Report project-data compatibility separately from release provenance."""
    manifest_path = root / ".codestable" / "manifest.json"
    manifest_error: str | None = None
    try:
        manifest = read_json(manifest_path) if source_is_file(manifest_path) else {}
    except KnowledgeError as exc:
        manifest = {}
        manifest_error = str(exc)
    raw_schema = config.get("schema_version")
    try:
        actual_schema: Any = int(raw_schema)
    except (TypeError, ValueError):
        actual_schema = raw_schema
    mode = config.get("mode")
    compatible = mode == RUNTIME_MODE and actual_schema == SCHEMA_VERSION
    versions = {
        "runtime": TOOL_VERSION,
        "config": normalize_space(config.get("version")),
        "version_file": normalize_space(safe_read_text(root / ".codestable" / "VERSION")),
        "manifest": normalize_space(manifest.get("version")) if isinstance(manifest, dict) else "",
    }
    versions_aligned = all(value == TOOL_VERSION for value in versions.values())
    version_status = (
        "aligned"
        if versions_aligned
        else "compatible-release-drift"
        if compatible
        else "incompatible"
    )
    version_action = (
        "none"
        if versions_aligned
        else "optional: run bootstrap.py --check and explicitly rebuild only when a new knowledge base is intended"
        if compatible
        else "required: run bootstrap.py --check and follow its compatibility action"
    )
    return {
        "ok": compatible,
        "runtime_source": "skill",
        "runtime_path": str(Path(__file__).resolve()),
        "mode": {"expected": RUNTIME_MODE, "actual": mode},
        "schema": {"expected": SCHEMA_VERSION, "actual": actual_schema},
        "versions": versions,
        "versions_aligned": versions_aligned,
        "version_status": version_status,
        "version_action": version_action,
        "manifest_error": manifest_error,
        "detail": (
            "project data is compatible with the shared Skill runtime; release metadata drift is informational"
            if compatible and not versions_aligned
            else "project data is compatible with the shared Skill runtime"
            if compatible
            else "project data is incompatible with the shared Skill runtime"
        ),
        "distribution_reference_checked": False,
        "distribution_check": "run bootstrap.py --check from the installed CodeStable Skill for a read-only compatibility report",
    }


def doctor(root: Path, config: dict[str, Any], check_current_references: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    categories = configured_categories(config)
    runtime_alignment = local_runtime_alignment(root, config)
    if not runtime_alignment["ok"]:
        warnings.append(
            {
                "code": "runtime.data.incompatible",
                "detail": runtime_alignment["detail"],
                "action": "run the installed CodeStable Skill bootstrap.py --check, use --rebuild only after explicit authorization if it reports needs-rebuild",
            }
        )
    if not source_is_dir(wiki):
        errors.append({"code": "wiki.missing", "detail": f"missing wiki directory: {wiki}"})
        return {
            "ok": False,
            "scope": "structure-only",
            "current_knowledge_validated": False,
            "current_references_checked": False,
            "next_check": "run drift to compare current references and Git changes",
            "errors": errors,
            "warnings": warnings,
            "stats": {},
        }
    wiki_config = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    configured_entry = normalize_space(wiki_config.get("current_entry") or CURRENT_ENTRY)
    if configured_entry != CURRENT_ENTRY:
        errors.append(
            {
                "code": "wiki.entry.invalid",
                "detail": f"the only supported current entry is {CURRENT_ENTRY}, configured {configured_entry}",
            }
        )
    required_files = ["README.md", "INDEX.md", "HISTORY.md", "TOPICS.md", "PROJECT.md", "learning.schema.json"]
    for required in required_files:
        if not source_is_file(wiki / required):
            errors.append({"code": "wiki.file.missing", "detail": f"missing {wiki / required}"})
    for category in categories:
        directory = wiki / category
        if not source_is_dir(directory):
            errors.append({"code": "wiki.category.missing", "detail": f"missing category directory {directory}"})
            continue
        for required in ("README.md", "INDEX.md"):
            if not source_is_file(directory / required):
                errors.append({"code": "wiki.category.file.missing", "detail": f"missing {directory / required}"})

    identifiers: dict[str, Path] = {}
    cards: dict[str, tuple[Path, dict[str, Any], str]] = {}
    tasks: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for kind, paths in (("knowledge-card", card_paths(wiki, categories)), ("task-note", task_note_paths(wiki))):
        for path in paths:
            relative = path.relative_to(root).as_posix()
            try:
                metadata, body, _ = read_markdown(path)
            except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
                errors.append({"code": "markdown.invalid", "detail": f"{relative}: {exc}"})
                continue
            identifier = normalize_space(metadata.get("id"))
            if not identifier:
                errors.append({"code": "record.id.missing", "detail": f"{relative} has no id"})
                continue
            if identifier in identifiers:
                errors.append({"code": "record.id.duplicate", "detail": f"{identifier} appears in {identifiers[identifier]} and {path}"})
            identifiers[identifier] = path
            if normalize_space(metadata.get("type")) != kind:
                errors.append({"code": "record.type", "detail": f"{relative} must have type {kind}"})
            if kind == "knowledge-card":
                category = normalize_space(metadata.get("category"))
                if category not in CATEGORY_DEFS:
                    errors.append({"code": "card.category", "detail": f"{relative} has invalid category {category!r}"})
                elif path.parent.name != category:
                    errors.append({"code": "card.category.path", "detail": f"{relative} is not stored under category {category}"})
                status = normalize_space(metadata.get("status"))
                confidence = normalize_space(metadata.get("confidence"))
                if status not in CARD_STATUSES:
                    errors.append({"code": "card.status", "detail": f"{relative} has invalid status {status!r}"})
                if confidence not in CONFIDENCE_LEVELS:
                    errors.append({"code": "card.confidence", "detail": f"{relative} has invalid confidence {confidence!r}"})
                if not extract_section(body, ("结论",)):
                    errors.append({"code": "card.knowledge.missing", "detail": f"{relative} has no 结论 section"})
                try:
                    normalize_scopes(metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [])
                    normalize_scopes(metadata.get("applies_to"))
                    normalize_card_dependencies(metadata.get("depends_on"))
                except KnowledgeError as exc:
                    errors.append({"code": "card.scopes", "detail": f"{relative}: {exc}"})
                known_topic_names = topic_aliases(config)
                unknown_topics = [value for value in unique_strings(metadata.get("topics")) if value not in known_topic_names]
                if unknown_topics:
                    warnings.append(
                        {
                            "code": "card.topic.unconfigured",
                            "detail": f"{relative} uses unconfigured topics: {', '.join(unknown_topics)}",
                        }
                    )
                cards[identifier] = (path, metadata, body)
            else:
                status = normalize_space(metadata.get("task_status"))
                if status not in TASK_STATUSES:
                    errors.append({"code": "task.status", "detail": f"{relative} has invalid task_status {status!r}"})
                visibility = normalize_space(metadata.get("visibility") or "active")
                if visibility not in TASK_VISIBILITIES:
                    errors.append({"code": "task.visibility", "detail": f"{relative} has invalid visibility {visibility!r}"})
                tasks[identifier] = (path, metadata, body)

    for identifier, (path, metadata, _) in cards.items():
        for old_id in unique_strings(metadata.get("supersedes")):
            if old_id not in cards:
                errors.append({"code": "card.supersedes.missing", "detail": f"{identifier} supersedes missing card {old_id}"})
            elif identifier not in unique_strings(cards[old_id][1].get("superseded_by")):
                errors.append({"code": "card.supersedes.asymmetric", "detail": f"{old_id} does not point back to {identifier}"})
        for new_id in unique_strings(metadata.get("superseded_by")):
            if new_id not in cards:
                errors.append({"code": "card.superseded_by.missing", "detail": f"{identifier} points to missing card {new_id}"})
        if normalize_space(metadata.get("status")) == "superseded" and not unique_strings(metadata.get("superseded_by")):
            warnings.append({"code": "card.superseded.unlinked", "detail": f"{identifier} is superseded without superseded_by"})

    for identifier, (_, metadata, _) in tasks.items():
        for card_id in unique_strings(metadata.get("card_ids")):
            if card_id not in cards:
                errors.append({"code": "task.card.missing", "detail": f"task {identifier} references missing card {card_id}"})
        for value in metadata.get("knowledge_use") or []:
            if not isinstance(value, dict) or normalize_space(value.get("card_id")) not in cards:
                errors.append({"code": "task.knowledge_use.missing", "detail": f"task {identifier} has invalid knowledge-use card reference"})
        visibility = normalize_space(metadata.get("visibility") or "active")
        consolidated_into = normalize_space(metadata.get("consolidated_into"))
        if visibility == "archived":
            if not consolidated_into or consolidated_into not in tasks:
                errors.append({"code": "task.consolidated_into.missing", "detail": f"archived task {identifier} has no valid canonical task"})
            elif identifier not in unique_strings(tasks[consolidated_into][1].get("consolidated_from")):
                errors.append({"code": "task.consolidation.asymmetric", "detail": f"canonical task {consolidated_into} does not point back to {identifier}"})
        for duplicate_id in unique_strings(metadata.get("consolidated_from")):
            if duplicate_id not in tasks:
                errors.append({"code": "task.consolidated_from.missing", "detail": f"task {identifier} references missing duplicate {duplicate_id}"})
            elif normalize_space(tasks[duplicate_id][1].get("consolidated_into")) != identifier:
                errors.append({"code": "task.consolidation.asymmetric", "detail": f"duplicate task {duplicate_id} does not point to {identifier}"})

    cache_changes: list[str] = []
    try:
        _, outputs = build_index_outputs(root, config)
        for path, expected in outputs.items():
            if READ_VIEW.get() is not None:
                continue  # Validate source records above; derive indexes from this exact Git view.
            actual = source_text(path, encoding="utf-8") if source_is_file(path) else None
            if actual != expected:
                if path.is_relative_to(index_root(root, config)):
                    cache_changes.append(path.relative_to(root).as_posix())
                else:
                    errors.append({"code": "index.stale", "detail": f"{path.relative_to(root).as_posix()} is stale; run reindex"})
    except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
        errors.append({"code": "index.invalid", "detail": str(exc)})

    lock = wiki / ".write.lock"
    if source_exists(lock):
        warnings.append({"code": "write.lock.present", "detail": f"write lock exists: {lock}"})
    transactions = wiki / ".transactions"
    pending_transactions = sorted(path.name for path in source_children(transactions)) if source_is_dir(transactions) else []
    if pending_transactions:
        errors.append(
            {
                "code": "write.transaction.pending",
                "detail": "pending recovery transactions: " + ", ".join(pending_transactions),
            }
        )

    entry_check = agents_entry_check(root, config)
    warnings.extend(
        {"code": value["code"], "detail": value["detail"], "action": value.get("action", "")}
        for value in entry_check["findings"]
    )
    for category in categories:
        has_current = any(
            normalize_space(metadata.get("category")) == category and normalize_space(metadata.get("status")) == "current"
            for _, metadata, _ in cards.values()
        )
        readme = wiki / category / "README.md"
        if has_current and source_is_file(readme) and not extract_canonical(safe_read_text(readme)):
            warnings.append(
                {
                    "code": "wiki.category.summary.empty",
                    "detail": f"{readme.relative_to(root).as_posix()} has current cards but no maintained summary; use TOPICS.md for navigation or add a concise summary",
                }
            )

    governance = topic_governance(config)
    configured_topic_count = len(configured_topics(config))
    current_card_count = sum(
        normalize_space(metadata.get("status")) == "current" for _, metadata, _ in cards.values()
    )
    themed_current_count = sum(
        normalize_space(metadata.get("status")) == "current" and bool(unique_strings(metadata.get("topics")))
        for _, metadata, _ in cards.values()
    )
    topic_coverage = themed_current_count / current_card_count if current_card_count else 1.0
    if governance["mode"] == "manual" and not configured_topic_count:
        warnings.append(
            {
                "code": "topic.manual.unconfigured",
                "detail": "topic governance is manual but no business topics are configured; this is not a healthy enabled topic view",
                "action": "run topics suggest, review the proposal, then apply it with a dry-run token; or set mode=disabled",
            }
        )
    if governance["mode"] == "required" and topic_coverage < governance["minimum_coverage"]:
        warnings.append(
            {
                "code": "topic.required.coverage",
                "detail": (
                    f"current topic coverage {topic_coverage:.1%} is below required "
                    f"{governance['minimum_coverage']:.1%}"
                ),
                "action": "assign reviewed topics to current cards or lower the explicit threshold",
            }
        )

    stats = {
        "cards": len(cards),
        "current_cards": sum(normalize_space(metadata.get("status")) == "current" for _, metadata, _ in cards.values()),
        "proposed_cards": sum(normalize_space(metadata.get("status")) == "proposed" for _, metadata, _ in cards.values()),
        "task_notes": len(tasks),
        "active_task_notes": sum(normalize_space(metadata.get("visibility") or "active") != "archived" for _, metadata, _ in tasks.values()),
        "archived_task_notes": sum(normalize_space(metadata.get("visibility") or "active") == "archived" for _, metadata, _ in tasks.values()),
        "categories": len(categories),
    }
    result: dict[str, Any] = {
        "ok": not errors,
        "tool_version": TOOL_VERSION,
        "scope": "structure+current-references" if check_current_references else "structure-only",
        "current_knowledge_validated": False,
        "current_references_checked": check_current_references,
        "evidence_validity_checked": False,
        "content_review_checked": False,
        "next_check": "run drift to compare current references and Git changes",
        "errors": errors,
        "warnings": warnings,
        "generated_cache": {"status": "rebuild-available" if cache_changes else "current", "changed": cache_changes, "blocking": False},
        "runtime_alignment": runtime_alignment,
        "entry_check": entry_check,
        "topic_governance": {
            **governance,
            "configured_topics": configured_topic_count,
            "current_cards": current_card_count,
            "themed_current_cards": themed_current_count,
            "coverage": round(topic_coverage, 4),
        },
        "stats": stats,
    }
    if check_current_references:
        reference_check = current_reference_drift(root, config)
        result["current_references"] = reference_check
        result["ok"] = result["ok"] and not reference_check["findings"]
        result["next_check"] = "reference candidates checked; run drift with a Git scope for task-note coverage"
    return result


def summary_review_metadata(text: str) -> dict[str, Any]:
    match = re.search(r"<!--\s*codestable:summary-review\s+(\{.*?\})\s*-->", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        "knowledge_hash": normalize_space(value.get("knowledge_hash")),
        "reviewed_at": normalize_space(value.get("reviewed_at")),
        "summary_hash": normalize_space(value.get("summary_hash")),
        **({"sources": value["sources"]} if "sources" in value else {}),
    }


def governance_audit(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, _ = scan_existing_records(wiki, configured_categories(config))
    current = [
        (identifier, path, metadata, body)
        for identifier, (path, metadata, body) in cards.items()
        if normalize_space(metadata.get("status")) == "current"
    ]
    review_days = topic_governance(config)["review_max_age_days"]
    now = now_local()
    findings: list[dict[str, Any]] = []
    for identifier, path, metadata, body in current:
        relative = path.relative_to(root).as_posix()
        evidence = metadata.get("evidence")
        future_use = metadata.get("future_use")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(value, dict) for value in evidence):
            findings.append(
                {
                    "issue_type": "card-evidence-unstructured",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "review the current card and update it with structured evidence; do not infer evidence during upgrade",
                }
            )
        elif any(PLACEHOLDER_PATTERN.search(text) or text in GENERIC_DURABLE_TEXT for text in recursive_strings(evidence)):
            findings.append(
                {
                    "issue_type": "card-evidence-generic",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "replace generic evidence with a specific artifact, observed result, and supported conclusion",
                }
            )
        if not isinstance(future_use, list) or len(future_use) < 2 or any(not isinstance(value, dict) for value in future_use):
            findings.append(
                {
                    "issue_type": "future-use-unstructured",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "record two distinct future changes with actor and constraint; rebuild unsupported old records from current source and tests",
                }
            )
        elif any(PLACEHOLDER_PATTERN.search(text) or text in GENERIC_DURABLE_TEXT for text in recursive_strings(future_use)):
            findings.append(
                {
                    "issue_type": "future-use-generic",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "replace template language with concrete future review scenarios",
                }
            )
        updated_at = normalize_space(metadata.get("updated_at") or metadata.get("created_at"))
        if updated_at:
            try:
                age_days = (now - datetime.fromisoformat(updated_at).astimezone()).days
            except ValueError:
                age_days = review_days + 1
            if age_days > review_days:
                findings.append(
                    {
                        "issue_type": "card-review-old",
                        "card_id": identifier,
                        "path": relative,
                        "age_days": age_days,
                        "suggested_action": "review the card against current implementation, tests, contracts, and accepted decisions",
                    }
                )

    by_category: dict[str, list[tuple[str, Path, dict[str, Any], str]]] = {}
    for value in current:
        by_category.setdefault(normalize_space(value[2].get("category")), []).append(value)
    for category, values in sorted(by_category.items()):
        for left_index, left in enumerate(values):
            for right in values[left_index + 1 :]:
                same_title = normalize_space(left[2].get("title")).casefold() == normalize_space(right[2].get("title")).casefold()
                similarity = conclusion_similarity(
                    extract_section(left[3], ("结论",)), extract_section(right[3], ("结论",))
                )
                if same_title or similarity >= 0.82:
                    findings.append(
                        {
                            "issue_type": "possible-equivalent-current-cards",
                            "card_ids": [left[0], right[0]],
                            "category": category,
                            "similarity": round(similarity, 3),
                            "suggested_action": "review for semantic equivalence; reuse/update one card or preserve both with a documented orthogonal scope",
                        }
                    )

    policy = topic_governance(config)
    topics = configured_topics(config)
    themed = sum(bool(unique_strings(metadata.get("topics"))) for _, _, metadata, _ in current)
    coverage = themed / len(current) if current else 1.0
    # Human-page freshness is reported by the shared content-review section.
    topic_status = "not-applicable" if policy["mode"] == "disabled" else "pass"
    if policy["mode"] == "manual" and not topics:
        topic_status = "incomplete"
        findings.append(
            {
                "issue_type": "topic-governance-not-configured",
                "suggested_action": "run topics suggest and review an update, or explicitly choose disabled mode",
            }
        )
    if policy["mode"] == "required" and coverage < policy["minimum_coverage"]:
        topic_status = "incomplete"
        findings.append(
            {
                "issue_type": "topic-coverage-below-policy",
                "coverage": round(coverage, 4),
                "required": policy["minimum_coverage"],
                "suggested_action": "assign reviewed topics to current cards before treating the topic view as healthy",
            }
        )
    return {
        "status": "needs-attention" if findings else topic_status,
        "topic_status": topic_status,
        "topic_policy": policy,
        "topic_coverage": round(coverage, 4),
        "current_cards": len(current),
        "themed_current_cards": themed,
        "unthemed_current_cards": len(current) - themed,
        "findings": findings,
    }


def snapshot_runtime_asset(root: Path, build_script: Path) -> dict[str, Any]:
    import ast
    try:
        parsed = ast.parse(source_text(build_script))
        sections = next(ast.literal_eval(node.value) for node in parsed.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "SECTIONS" for target in node.targets))
        digest = hashlib.sha256()
        chunks = []
        for index, name in enumerate(sections):
            text = source_text(root / "skills/cs/runtime_src" / name).replace("\r\n", "\n")
            digest.update(name.encode() + b"\0" + text.encode() + b"\0")
            chunks.append(text.rstrip() if index == 0 else text.split("# CODESTABLE-RUNTIME-SECTION", 1)[1].strip())
        lines = ("\n\n".join(chunks).rstrip() + "\n").splitlines()
        lines.insert(1, f"# Generated from skills/cs/runtime_src; source-sha256: {digest.hexdigest()}")
        expected = "\n".join(lines) + "\n"
        actual = source_text(root / "skills/cs/scripts/cs_knowledge.py")
        return {"status": "pass" if actual == expected else "needs-attention", "detail": "compared runtime and maintenance sources from the same Git snapshot"}
    except (OSError, SyntaxError, ValueError, TypeError, StopIteration, IndexError, KnowledgeError) as exc:
        return {"status": "incomplete", "detail": str(exc)}


def delivery_audit(
    root: Path,
    config: dict[str, Any],
    cached: bool = False,
    base: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    findings: list[dict[str, Any]] = []
    version_path = root / ".codestable" / "VERSION"
    manifest_path = root / ".codestable" / "manifest.json"
    try:
        manifest = read_json(manifest_path) if source_is_file(manifest_path) else {}
    except KnowledgeError as exc:
        manifest = {}
        findings.append(
            {
                "issue_type": "release-manifest-invalid",
                "detail": str(exc),
                "suggested_action": "restore or upgrade the managed CodeStable manifest",
            }
        )
    versions = {
        "runtime": TOOL_VERSION,
        "config": normalize_space(config.get("version")),
        "version_file": normalize_space(safe_read_text(version_path)),
        "manifest": normalize_space(manifest.get("version")) if isinstance(manifest, dict) else "",
    }
    versions_aligned = all(value == TOOL_VERSION for value in versions.values())
    _, outputs = build_index_outputs(root, config)
    for path, content in outputs.items():
        bad_lines = [number for number, line in enumerate(content.splitlines(), start=1) if line.rstrip() != line]
        if bad_lines:
            findings.append(
                {
                    "issue_type": "generated-markdown-trailing-whitespace",
                    "path": path.relative_to(root).as_posix(),
                    "lines": bad_lines[:20],
                    "suggested_action": "fix the renderer and run reindex; do not hand-edit generated indexes",
                }
            )
    git_probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=str(root), text=True, capture_output=True, check=False
    )
    git_result: dict[str, Any]
    if git_probe.returncode == 0:
        try:
            drift = drift_payload(root, config, cached=cached, base=base)
        except KnowledgeError as exc:
            git_result = {"status": "incomplete", "detail": str(exc)}
            findings.append(
                {
                    "issue_type": "git-writeback-check-incomplete",
                    "detail": str(exc),
                    "suggested_action": "provide a valid Git baseline or run the narrower reference check",
                }
            )
        else:
            git_result = {"status": "pass" if drift["ok"] else "needs-attention", "detail": drift}
            findings.extend({"source": "drift", **value} for value in drift["findings"])
    else:
        git_result = {"status": "not-applicable", "detail": "not a Git worktree"}
    build_script = root / "scripts" / "build_runtime.py"
    build_result: dict[str, Any]
    if source_is_file(build_script) and READ_VIEW.get() is not None:
        build_result = snapshot_runtime_asset(root, build_script)
        if build_result["status"] != "pass":
            findings.append({"issue_type": "generated-runtime-out-of-sync", "suggested_action": "build and stage the runtime with its maintenance sources"})
    elif source_is_file(build_script):
        process = subprocess.run(
            [sys.executable, str(build_script), "--check"], cwd=str(root), text=True, capture_output=True, check=False
        )
        build_result = {
            "status": "pass" if process.returncode == 0 else "needs-attention",
            "detail": normalize_space(process.stdout or process.stderr),
        }
        if process.returncode != 0:
            findings.append(
                {
                    "issue_type": "generated-runtime-out-of-sync",
                    "suggested_action": "run scripts/build_runtime.py and review the generated shared runtime",
                }
            )
    else:
        build_result = {"status": "not-applicable", "detail": "maintenance build script not present in installed project"}
    return {
        "status": "needs-attention" if findings else "pass",
        "findings": findings,
        "git_writeback": git_result,
        "runtime_asset": build_result,
        "versions": versions,
        "versions_aligned": versions_aligned,
    }


def audit_payload(
    root: Path,
    config: dict[str, Any],
    cached: bool = False,
    base: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if (cached or base) and READ_VIEW.get() is None:
        with git_read_view(root, ":" if cached else "HEAD"):
            return audit_payload(root, load_config(root), cached=cached, base=base)
    structure = doctor(root, config)
    references = current_reference_drift(root, config)
    governance = governance_audit(root, config)
    review = knowledge_review(root, config)
    delivery = delivery_audit(root, config, cached=cached, base=base)
    structural_warnings = [
        value
        for value in structure.get("warnings", [])
        if not normalize_space(value.get("code")).startswith(("wiki.category.summary.", "topic."))
    ]
    structural_findings = [*structure.get("errors", []), *structural_warnings]
    sections = {
        "structure": {
            "status": "pass" if not structural_findings else "needs-attention",
            "findings": structural_findings,
            "detail": structure,
        },
        "current_references": {
            "status": "needs-attention" if references["findings"] else "incomplete" if references["unverified"] else "pass",
            "detail": references,
        },
        "governance": governance,
        "evidence_validity": {
            "status": ("needs-attention" if any(value["status"] == "needs-review" for value in review["cards"].values())
                       else "incomplete" if any(value["status"] == "unverifiable" for value in review["cards"].values()) else "pass"),
            "findings": [value for value in review["review_queue"] if value["issue_type"].startswith("evidence-")],
        },
        "content_review": {
            "status": "needs-attention" if any(not value["issue_type"].startswith("evidence-") for value in review["review_queue"]) else "pass",
            "findings": [value for value in review["review_queue"] if not value["issue_type"].startswith("evidence-")],
            "summaries": review["summaries"],
        },
        "delivery": delivery,
    }
    comparison: dict[str, Any] = {}
    if cached or base:
        baseline = "HEAD" if cached else run_git(root, ["merge-base", base, "HEAD"]).stdout.strip()
        # Preserve policy outcomes while distinguishing existing debt from this change.
        try:
            with git_read_view(root, baseline):
                baseline_config = load_config(root)
                prior_structure = doctor(root, baseline_config)
                prior_references = current_reference_drift(root, baseline_config)
                prior_governance = governance_audit(root, baseline_config)
                prior_review = knowledge_review(root, baseline_config)
            previous = [*prior_structure["errors"], *prior_structure["warnings"],
                        *prior_references["findings"], *prior_governance["findings"], *prior_review["review_queue"]]
            def signature(value: dict[str, Any]) -> str:
                return stable_json({key: item for key, item in value.items() if key not in {"age_days", "origin"}})
            known = {signature(value) for value in previous}
            counts = {"existing": 0, "introduced_or_changed": 0}
            for values in (structural_findings, references["findings"], governance["findings"], review["review_queue"]):
                for value in values:
                    origin = "existing" if signature(value) in known else "introduced_or_changed"
                    value["origin"] = origin
                    counts[origin] += 1
            comparison = {"baseline": baseline, **counts}
        except KnowledgeError as exc:
            comparison = {"baseline": baseline, "status": "unavailable", "detail": str(exc)}
    blocking_statuses = {"needs-attention", "incomplete"}
    ok = all(section.get("status") not in blocking_statuses for section in sections.values())
    return {
        "ok": ok,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "exit_code": 0 if ok else 1,
        "business_truth": "not-evaluated",
        "knowledge_source": "git-index" if cached else "HEAD" if base else "working-tree",
        "comparison": comparison,
        "sections": sections,
        "review_queue": review["review_queue"],
        "limits": [
            "audit verifies structure, current references, governance evidence, generated outputs, and Git knowledge writeback",
            "audit does not prove that implementation satisfies business requirements",
        ],
    }


def render_audit_text(payload: dict[str, Any]) -> str:
    lines = [
        "CodeStable 知识检查",
        "各检查维度分别报告；业务结论真实性未自动判断。",
        "",
    ]
    names = {"structure": "结构", "current_references": "引用", "evidence_validity": "证据有效性",
             "content_review": "内容复核", "governance": "知识组织", "delivery": "版本与交付记录"}
    statuses = {"pass": "本项检查通过", "needs-attention": "需要处理", "incomplete": "依据不完整", "not-applicable": "不适用"}
    for name, section in payload["sections"].items():
        findings = section.get("findings")
        if findings is None and isinstance(section.get("detail"), dict):
            detail = section["detail"]
            findings = detail.get("findings") or detail.get("errors") or []
        lines.append(f"- {names.get(name, name)}：{statuses.get(section.get('status'), '尚未检查')} · 问题 {len(findings or [])} 项")
        for finding in findings or []:
            location = finding.get("path") or finding.get("target") or finding.get("card_id") or "项目配置"
            reason = finding.get("reason") or finding.get("detail") or finding.get("issue_type") or finding.get("code") or "请复核本项"
            action = finding.get("suggested_action") or finding.get("action") or "查看 JSON 中的对应诊断并复核来源。"
            lines.append(f"  {location}：{review_reason_text(str(reason))}；{action}")
    reviews = payload["sections"]["current_references"]["detail"].get("review_candidates", {})
    if reviews.get("items"):
        lines.extend(("", f"同范围知识并读候选：{len(reviews['items'])} 组，仅供复核；JSON 可查看详情。"))
    lines.extend(("", "本命令只读；结构正确和引用存在均不能替代业务验收。", ""))
    return "\n".join(lines)


def status_payload(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    root = root.expanduser().resolve()
    entries = collect_index_entries(root, config)
    cards = [entry for entry in entries if entry["type"] == "knowledge-card"]
    tasks = [entry for entry in entries if entry["type"] == "task-note"]
    category_counts: dict[str, dict[str, int]] = {}
    for category in configured_categories(config):
        values = [entry for entry in cards if entry.get("category") == category]
        category_counts[category] = {
            "current": sum(entry["status"] == "current" for entry in values),
            "proposed": sum(entry["status"] == "proposed" for entry in values),
            "deprecated": sum(entry["status"] == "deprecated" for entry in values),
            "superseded": sum(entry["status"] == "superseded" for entry in values),
        }
    active_tasks = [entry for entry in tasks if entry.get("visibility") != "archived"]
    archived_tasks = [entry for entry in tasks if entry.get("visibility") == "archived"]
    recent = sorted(active_tasks, key=lambda item: item.get("created_at") or "", reverse=True)[:10]
    return {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "categories": category_counts,
        "cards": len(cards),
        "task_notes": len(tasks),
        "active_task_notes": len(active_tasks),
        "archived_task_notes": len(archived_tasks),
        "recent_tasks": recent,
    }
