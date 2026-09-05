"""CodeStable runtime section: 20 storage."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def card_paths(wiki: Path, categories: Sequence[str]) -> Iterator[Path]:
    for category in categories:
        directory = wiki / category
        if not source_is_dir(directory):
            continue
        for path in sorted(source_glob(directory, "*.md")):
            if path.name in {"README.md", "INDEX.md"}:
                continue
            yield path


def task_note_paths(wiki: Path) -> Iterator[Path]:
    directory = wiki / "task-notes"
    if not source_is_dir(directory):
        return
    for path in sorted(source_glob(directory, "*.md", recursive=True)):
        yield path


def scan_existing_records(wiki: Path, categories: Sequence[str]) -> tuple[dict[str, tuple[Path, dict[str, Any], str]], dict[str, tuple[Path, dict[str, Any], str]]]:
    cards: dict[str, tuple[Path, dict[str, Any], str]] = {}
    tasks: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for path in card_paths(wiki, categories):
        metadata, body, _ = read_markdown(path)
        identifier = normalize_space(metadata.get("id"))
        if identifier:
            cards[identifier] = (path, metadata, body)
    for path in task_note_paths(wiki):
        metadata, body, _ = read_markdown(path)
        identifier = normalize_space(metadata.get("id"))
        if identifier:
            tasks[identifier] = (path, metadata, body)
    return cards, tasks


def task_note_filename(task: dict[str, Any], task_id: str, timestamp: datetime) -> Path:
    slug = slugify(task["title"], "task")
    return Path("task-notes") / timestamp.strftime("%Y") / f"{timestamp.strftime('%Y-%m-%d')}-{slug}-{task_id[-8:].lower()}.md"


def card_filename(item: dict[str, Any], card_id: str) -> Path:
    return Path(item["category"]) / f"{card_id.lower()}-{slugify(item['title'], 'knowledge')}.md"


def update_card_supersession(path: Path, new_id: str, timestamp: str, dry_run: bool) -> None:
    metadata, body, _ = read_markdown(path)
    metadata["status"] = "superseded"
    metadata["updated_at"] = timestamp
    values = unique_strings(metadata.get("superseded_by"))
    if new_id not in values:
        values.append(new_id)
    metadata["superseded_by"] = values
    if not dry_run:
        atomic_write_text(path, render_front_matter(metadata, body))


def index_entry_for(
    path: Path,
    root: Path,
    metadata: dict[str, Any],
    body: str,
    rendered_text: str | None = None,
) -> dict[str, Any]:
    source_type = normalize_space(metadata.get("type") or "unknown")
    visibility = normalize_space(metadata.get("visibility") or "active")
    excerpt = "" if visibility == "archived" else extract_section(body, ("结论", "处理摘要", "最终结果")) or clip(body, 400)
    return {
        "id": normalize_space(metadata.get("id")),
        "type": source_type,
        "category": normalize_space(metadata.get("category")) or None,
        "title": normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
        "status": normalize_space(metadata.get("status") or metadata.get("task_status") or "current"),
        "confidence": normalize_space(metadata.get("confidence") or "accepted"),
        "path": path.relative_to(root).as_posix(),
        "created_at": normalize_space(metadata.get("created_at")),
        "updated_at": normalize_space(metadata.get("updated_at")),
        "tags": unique_strings(metadata.get("tags")),
        "topics": unique_strings(metadata.get("topics")),
        "scopes": metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [],
        "paths": unique_strings(metadata.get("paths")),
        "symbols": unique_strings(metadata.get("symbols")),
        "supersedes": unique_strings(metadata.get("supersedes")),
        "superseded_by": unique_strings(metadata.get("superseded_by")),
        "card_ids": unique_strings(metadata.get("card_ids")),
        "knowledge_use_card_ids": unique_strings([
            value.get("card_id")
            for value in (metadata.get("knowledge_use") or [])
            if isinstance(value, dict)
        ]),
        "visibility": visibility,
        "consolidated_from": unique_strings(metadata.get("consolidated_from")),
        "consolidated_into": normalize_space(metadata.get("consolidated_into")) or None,
        "pinned": bool(metadata.get("pinned", False)),
        "revision": int(metadata.get("revision", 1) or 1),
        "fingerprint": normalize_space(metadata.get("fingerprint")),
        "sha256": sha256_text(rendered_text) if rendered_text is not None else sha256_file(path),
        "excerpt": clip(excerpt, 400),
    }


def collect_index_entries(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    entries: list[dict[str, Any]] = []
    for path in card_paths(wiki, configured_categories(config)):
        metadata, body, _ = read_markdown(path)
        entries.append(index_entry_for(path, root, metadata, body))
    for path in task_note_paths(wiki):
        metadata, body, _ = read_markdown(path)
        entries.append(index_entry_for(path, root, metadata, body))
    return sorted(
        entries,
        key=lambda item: (
            0 if item["type"] == "knowledge-card" else 1,
            item.get("category") or "",
            item.get("created_at") or "",
            item.get("id") or "",
        ),
    )


def relative_link(from_path: Path, target_path: Path) -> str:
    return Path(os.path.relpath(target_path, from_path.parent)).as_posix()


def index_root(root: Path, config: dict[str, Any]) -> Path:
    return root / ".codestable/cache/wiki"


def stable_navigation(root: Path, config: dict[str, Any]) -> dict[Path, str]:
    wiki = wiki_root(root, config)
    generated = index_root(root, config)
    notice = "目录由共享工具 `reindex` 生成到本地缓存；缓存缺失时仍可用 `brief` 检索正文。"
    lines = ["# CodeStable Wiki 当前入口", "", "卡片和任务记录是知识来源；下面的入口不随任务数量变化。", "",
             "- [项目总览](PROJECT.md)", "- [使用说明](README.md)", "- [业务主题](TOPICS.md)",
             "- [历史关系](HISTORY.md)", f"- [当前知识与最近任务]({relative_link(wiki / 'INDEX.md', generated / 'INDEX.md')})", "",
             "## 知识分类", ""]
    outputs = {}
    for category in configured_categories(config):
        label = CATEGORY_DEFS[category]["label"]
        lines.append(f"- [{label}]({category}/INDEX.md)")
        path = wiki / category / "INDEX.md"
        outputs[path] = f"# {label}\n\n- [人工摘要](README.md)\n- [当前卡片目录]({relative_link(path, generated / category / 'INDEX.md')})\n\n{notice}\n"
    lines.extend(("", notice, ""))
    outputs[wiki / "INDEX.md"] = "\n".join(lines)
    for filename, title in (("TOPICS.md", "业务主题"), ("HISTORY.md", "历史关系")):
        path = wiki / filename
        outputs[path] = f"# CodeStable {title}\n\n[打开{title}目录]({relative_link(path, generated / filename)})\n\n{notice}\n"
    return outputs


def render_root_index(root: Path, config: dict[str, Any], entries: Sequence[dict[str, Any]]) -> str:
    wiki = index_root(root, config)
    cards = [entry for entry in entries if entry["type"] == "knowledge-card"]
    tasks = [entry for entry in entries if entry["type"] == "task-note"]
    active_tasks = [entry for entry in tasks if entry.get("visibility") != "archived"]
    archived_tasks = [entry for entry in tasks if entry.get("visibility") == "archived"]
    current_cards = [entry for entry in cards if entry["status"] == "current"]
    proposed_cards = [entry for entry in cards if entry["status"] == "proposed"]
    topic_definitions = configured_topics(config)
    lines = [
        "# CodeStable Wiki 当前入口",
        "",
        "> 这是 CodeStable Wiki 的唯一当前入口。分类和主题页只提供导航；知识卡片是结论正文的唯一来源。",
        "",
        f"- 当前知识卡片：{len(current_cards)}",
        f"- 提议知识卡片：{len(proposed_cards)}",
        f"- 已取代/弃用卡片：{sum(1 for entry in cards if entry['status'] in {'superseded', 'deprecated'})}",
        f"- 默认任务记录：{len(active_tasks)}",
        f"- 已折叠历史记录：{len(archived_tasks)}",
        "",
        "## 知识分区",
        "",
        "| 分区 | 当前 | 提议 | 历史 |",
        "|---|---:|---:|---:|",
    ]
    for category in configured_categories(config):
        category_cards = [entry for entry in cards if entry.get("category") == category]
        current = sum(entry["status"] == "current" for entry in category_cards)
        proposed = sum(entry["status"] == "proposed" for entry in category_cards)
        history = sum(entry["status"] in {"superseded", "deprecated"} for entry in category_cards)
        label = CATEGORY_DEFS[category]["label"]
        lines.append(f"| [{label}]({category}/INDEX.md) | {current} | {proposed} | {history} |")
    lines.extend(("", "## 业务主题", ""))
    topic_counts: dict[str, int] = {}
    aliases = topic_aliases(config)
    for entry in current_cards:
        for topic in entry.get("topics") or []:
            canonical = aliases.get(topic, topic)
            topic_counts[canonical] = topic_counts.get(canonical, 0) + 1
    if not topic_counts:
        lines.append("- 暂无带业务主题的当前卡片；未带主题元数据的当前卡片仍可通过分类、路径和符号检索。")
    else:
        lines.extend(("| 主题 | 当前卡片 | 导航说明 |", "|---|---:|---|"))
        for topic in sorted(topic_counts):
            definition = topic_definitions.get(topic, {"label": topic, "summary": ""})
            lines.append(
                f"| [{definition['label']}](TOPICS.md#{slugify(definition['label'], topic)}) | "
                f"{topic_counts[topic]} | {definition['summary'] or '未填写主题说明'} |"
            )
    lines.extend(("", "历史卡片、取代链和归档任务见 [历史索引](HISTORY.md)。", ""))
    lines.extend(("## 最近完成任务", ""))
    completed = sorted(
        [entry for entry in active_tasks if entry["status"] == "completed"],
        key=lambda item: (item.get("updated_at") or item.get("created_at") or "", item.get("id") or ""),
        reverse=True,
    )[:20]
    if not completed:
        lines.append("- 暂无任务记录。")
    else:
        index_path = wiki / "INDEX.md"
        for entry in completed:
            target = root / entry["path"]
            lines.append(
                f"- [{entry['title']}]({relative_link(index_path, target)}) · "
                f"{entry['status']} · {entry.get('created_at') or 'unknown time'}"
            )
    lines.extend(("", "## 未完成任务", ""))
    incomplete = sorted(
        [entry for entry in active_tasks if entry["status"] in {"in-progress", "partial", "blocked"}],
        key=lambda item: (item.get("updated_at") or item.get("created_at") or "", item.get("id") or ""),
        reverse=True,
    )
    if not incomplete:
        lines.append("- 无未完成任务。")
    else:
        index_path = wiki / "INDEX.md"
        for entry in incomplete:
            target = root / entry["path"]
            lines.append(f"- [{entry['title']}]({relative_link(index_path, target)}) · {entry['status']}")
    lines.extend(("", "参见 Wiki 当前入口和项目总览。", ""))
    return "\n".join(lines)


def render_category_index(root: Path, config: dict[str, Any], category: str, entries: Sequence[dict[str, Any]]) -> str:
    wiki = index_root(root, config)
    path = wiki / category / "INDEX.md"
    label = CATEGORY_DEFS[category]["label"]
    cards = [entry for entry in entries if entry["type"] == "knowledge-card" and entry.get("category") == category]
    lines = [f"# {label} · Index", "", CATEGORY_DEFS[category]["description"], ""]
    groups = (
        ("当前知识", {"current"}),
        ("提议知识", {"proposed"}),
    )
    for heading, statuses in groups:
        group = sorted(
            [entry for entry in cards if entry["status"] in statuses],
            key=lambda item: (bool(item.get("pinned")), item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        lines.extend((f"## {heading}", ""))
        if not group:
            lines.append("- 无")
        else:
            for entry in group:
                target = root / entry["path"]
                suffixes = [entry.get("confidence") or "accepted"]
                if entry.get("pinned"):
                    suffixes.append("pinned")
                lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {' · '.join(suffixes)}")
                lines.append(f"  - {entry.get('excerpt') or ''}")
        lines.append("")
    lines.append(f"已弃用和被取代的卡片见 [历史索引](../HISTORY.md#{slugify(label, category)})。")
    lines.append("")
    lines.append("本页由 `cs_knowledge.py reindex` 或 `learn` 生成；人工摘要请维护在 Wiki 对应分类的 README.md。")
    lines.append("")
    return "\n".join(lines)


def render_topics_index(root: Path, config: dict[str, Any], entries: Sequence[dict[str, Any]]) -> str:
    wiki = index_root(root, config)
    path = wiki / "TOPICS.md"
    cards = [entry for entry in entries if entry["type"] == "knowledge-card" and entry["status"] == "current"]
    definitions = configured_topics(config)
    aliases = topic_aliases(config)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in cards:
        for topic in entry.get("topics") or []:
            grouped.setdefault(aliases.get(topic, topic), []).append(entry)
    lines = [
        "# CodeStable 业务主题",
        "",
        "本页只组织当前卡片的链接和导航摘要；卡片正文是结论的唯一来源。",
        "",
    ]
    if not grouped:
        lines.extend(("暂无带业务主题的当前知识卡片。", ""))
    for topic in sorted(grouped):
        definition = definitions.get(topic, {"label": topic, "summary": ""})
        lines.extend((f"## {definition['label']}", ""))
        if definition["summary"]:
            lines.extend((definition["summary"], ""))
        for entry in sorted(grouped[topic], key=lambda item: (item.get("category") or "", item["title"], item["id"])):
            target = root / entry["path"]
            label = CATEGORY_DEFS.get(entry.get("category") or "", {}).get("label", entry.get("category") or "其他")
            lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {label}")
        lines.append("")
    ungrouped = sum(not entry.get("topics") for entry in cards)
    if ungrouped:
        lines.extend(("## 未分主题", "", f"- {ungrouped} 张当前卡片没有主题元数据，仍可通过分类、路径和符号检索。", ""))
    lines.append("本页由 `cs_knowledge.py reindex` 或 `learn` 生成。")
    lines.append("")
    return "\n".join(lines)


def render_history_index(root: Path, config: dict[str, Any], entries: Sequence[dict[str, Any]]) -> str:
    wiki = index_root(root, config)
    path = wiki / "HISTORY.md"
    cards = [
        entry for entry in entries
        if entry["type"] == "knowledge-card" and entry["status"] in {"deprecated", "superseded"}
    ]
    tasks = [
        entry for entry in entries
        if entry["type"] == "task-note" and (entry.get("visibility") == "archived" or entry["status"] == "cancelled")
    ]
    lines = [
        "# CodeStable 历史索引",
        "",
        "这里保留已弃用、被取代和归档记录的链接。原卡片、任务记录、来源和取代关系不会被删除。",
        "",
    ]
    for category in configured_categories(config):
        group = [entry for entry in cards if entry.get("category") == category]
        if not group:
            continue
        label = CATEGORY_DEFS[category]["label"]
        lines.extend((f"## {label}", ""))
        for entry in sorted(group, key=lambda item: (item.get("updated_at") or "", item["id"]), reverse=True):
            target = root / entry["path"]
            relation = []
            if entry.get("supersedes"):
                relation.append("取代 " + ", ".join(f"`{value}`" for value in entry["supersedes"]))
            if entry.get("superseded_by"):
                relation.append("被 " + ", ".join(f"`{value}`" for value in entry["superseded_by"]) + " 取代")
            suffix = " · " + "；".join(relation) if relation else ""
            lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {entry['status']}{suffix}")
        lines.append("")
    if tasks:
        lines.extend(("## 归档与取消任务", ""))
        for entry in sorted(tasks, key=lambda item: (item.get("updated_at") or "", item["id"]), reverse=True):
            target = root / entry["path"]
            relation = f" · 合并到 `{entry['consolidated_into']}`" if entry.get("consolidated_into") else ""
            lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {entry['status']}{relation}")
        lines.append("")
    if not cards and not tasks:
        lines.extend(("暂无已弃用、被取代或归档的记录。", ""))
    lines.append("本页由 `cs_knowledge.py reindex` 或 `learn` 生成。")
    lines.append("")
    return "\n".join(lines)


def render_index_outputs(
    root: Path,
    config: dict[str, Any],
    entries: Sequence[dict[str, Any]],
) -> dict[Path, str]:
    wiki = index_root(root, config)
    jsonl = "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries)
    outputs: dict[Path, str] = {
        wiki / "index.jsonl": jsonl,
        wiki / "INDEX.md": render_root_index(root, config, entries),
        wiki / "TOPICS.md": render_topics_index(root, config, entries),
        wiki / "HISTORY.md": render_history_index(root, config, entries),
    }
    for category in configured_categories(config):
        outputs[wiki / category / "INDEX.md"] = render_category_index(root, config, category, entries)
    outputs.update(stable_navigation(root, config))
    return outputs


def build_index_outputs(root: Path, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[Path, str]]:
    root = root.expanduser().resolve()
    entries = collect_index_entries(root, config)
    return entries, render_index_outputs(root, config, entries)


def rebuild_indexes(root: Path, config: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    entries, outputs = build_index_outputs(root, config)
    changed: list[str] = []
    for path, content in outputs.items():
        existing = source_text(path, encoding="utf-8") if source_is_file(path) else None
        if existing != content:
            changed.append(path.relative_to(root).as_posix())
            if not dry_run:
                atomic_write_text(path, content)
    return {"entries": len(entries), "changed": changed, "dry_run": dry_run}


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def restore_recovery_journal(root: Path, transaction: Path) -> None:
    ready = transaction / "READY"
    committed = transaction / "COMMITTED"
    manifest_path = transaction / "manifest.json"
    if source_is_file(committed) or not source_is_file(ready):
        shutil.rmtree(transaction)
        return
    manifest = read_json(manifest_path)
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise KnowledgeError(f"invalid recovery journal: {manifest_path}")
    for entry in entries:
        if not isinstance(entry, dict):
            raise KnowledgeError(f"invalid recovery entry in {manifest_path}")
        target = resolve_inside(root, normalize_space(entry.get("path")))
        backup = normalize_space(entry.get("backup"))
        if backup:
            source = transaction / backup
            atomic_write_text(target, source_text(source, encoding="utf-8"))
        elif source_is_file(target):
            target.unlink()
    shutil.rmtree(transaction)


def recover_transactions(root: Path, wiki: Path) -> None:
    transactions = wiki / ".transactions"
    if source_is_dir(transactions):
        for transaction in sorted(path for path in source_children(transactions) if source_is_dir(path)):
            restore_recovery_journal(root, transaction)
        try:
            transactions.rmdir()
        except OSError:
            pass


def recover_abandoned_write(root: Path, wiki: Path, lock: Path) -> None:
    try:
        lock_data = read_json(lock)
    except KnowledgeError as exc:
        raise KnowledgeError(f"cannot inspect existing wiki write lock {lock}: {exc}") from exc
    pid = int(lock_data.get("pid", 0) or 0) if isinstance(lock_data, dict) else 0
    if process_is_alive(pid):
        raise KnowledgeError(f"wiki write lock already exists: {lock}; writer pid {pid} is active")
    recover_transactions(root, wiki)
    lock.unlink()


def acquire_lock(root: Path, wiki: Path) -> Path:
    lock = wiki / ".write.lock"
    wiki.mkdir(parents=True, exist_ok=True)
    if source_exists(lock):
        recover_abandoned_write(root, wiki, lock)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise KnowledgeError(f"wiki write lock already exists: {lock}; inspect and remove it only if no writer is active") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json_dump({"pid": os.getpid(), "created_at": now_iso()}))
    try:
        recover_transactions(root, wiki)
    except Exception:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        raise
    return lock


def create_recovery_journal(
    root: Path,
    wiki: Path,
    task_id: str,
    snapshot: dict[Path, str | None],
) -> Path:
    transactions = wiki / ".transactions"
    transaction = transactions / task_id.lower()
    if source_exists(transaction):
        raise KnowledgeError(f"knowledge transaction already exists: {transaction}")
    transaction.mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    try:
        for number, (path, content) in enumerate(sorted(snapshot.items(), key=lambda item: str(item[0])), start=1):
            backup = ""
            if content is not None:
                backup = f"files/{number:04d}.txt"
                atomic_write_text(transaction / backup, content)
            entries.append({"path": path.relative_to(root).as_posix(), "backup": backup})
        atomic_write_text(
            transaction / "manifest.json",
            json_dump({"schema_version": 1, "task_id": task_id, "entries": entries}),
        )
        atomic_write_text(transaction / "READY", "ready\n")
    except Exception:
        shutil.rmtree(transaction, ignore_errors=True)
        try:
            transactions.rmdir()
        except OSError:
            pass
        raise
    return transaction


def remove_recovery_journal(transaction: Path) -> None:
    transactions = transaction.parent
    shutil.rmtree(transaction)
    try:
        transactions.rmdir()
    except OSError:
        pass


def restore_snapshot(snapshot: dict[Path, str | None], wiki: Path) -> None:
    errors: list[str] = []
    for path, content in snapshot.items():
        try:
            if content is None:
                if source_is_file(path):
                    path.unlink()
            else:
                atomic_write_text(path, content)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    task_root = wiki / "task-notes"
    for path, content in snapshot.items():
        if content is not None:
            continue
        parent = path.parent
        while parent != task_root and task_root in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    if errors:
        raise KnowledgeError("failed to roll back knowledge write: " + "; ".join(errors))


def projected_index_plan(
    root: Path,
    config: dict[str, Any],
    cards: dict[str, tuple[Path, dict[str, Any], str]],
    tasks: dict[str, tuple[Path, dict[str, Any], str]],
    created_plan: Sequence[tuple[str, Path, dict[str, Any], str, dict[str, Any]]],
    updated_card_plan: Sequence[tuple[str, Path, dict[str, Any], str, dict[str, Any]]],
    task_path: Path,
    task_metadata: dict[str, Any],
    task_body: str,
    supersession_plan: Sequence[tuple[str, str]],
    timestamp_text: str,
    replaced_task_id: str | None = None,
) -> dict[str, Any]:
    superseded_by: dict[str, list[str]] = {}
    for old_id, new_id in supersession_plan:
        superseded_by.setdefault(old_id, []).append(new_id)

    entries: list[dict[str, Any]] = []
    updated_cards = {identifier: (path, metadata, body) for identifier, path, metadata, body, _ in updated_card_plan}
    for identifier, (path, metadata, body) in cards.items():
        if identifier in updated_cards:
            path, projected, body = updated_cards[identifier]
            projected = dict(projected)
        else:
            projected = dict(metadata)
        if identifier in superseded_by:
            projected["status"] = "superseded"
            projected["updated_at"] = timestamp_text
            values = unique_strings(projected.get("superseded_by"))
            for new_id in superseded_by[identifier]:
                if new_id not in values:
                    values.append(new_id)
            projected["superseded_by"] = values
        rendered = render_front_matter(projected, body)
        entries.append(index_entry_for(path, root, projected, body, rendered))
    for identifier, (path, metadata, body) in tasks.items():
        if identifier == replaced_task_id:
            continue
        rendered = render_front_matter(metadata, body)
        entries.append(index_entry_for(path, root, metadata, body, rendered))
    for _, path, metadata, body, _ in created_plan:
        rendered = render_front_matter(metadata, body)
        entries.append(index_entry_for(path, root, metadata, body, rendered))
    rendered_task = render_front_matter(task_metadata, task_body)
    entries.append(index_entry_for(task_path, root, task_metadata, task_body, rendered_task))
    entries.sort(
        key=lambda item: (
            0 if item["type"] == "knowledge-card" else 1,
            item.get("category") or "",
            item.get("created_at") or "",
            item.get("id") or "",
        )
    )
    outputs = render_index_outputs(root, config, entries)
    changed = [
        path.relative_to(root).as_posix()
        for path, content in outputs.items()
        if (source_text(path, encoding="utf-8") if source_is_file(path) else None) != content
    ]
    return {"entries": len(entries), "changed": changed, "dry_run": True}


def task_similarity_candidates(
    task: dict[str, Any],
    tasks: dict[str, tuple[Path, dict[str, Any], str]],
    root: Path,
) -> list[dict[str, Any]]:
    title = normalize_space(task["title"]).casefold()
    paths = set(task["paths"])
    deliverable = normalize_space(task.get("deliverable")).casefold()
    candidates: list[dict[str, Any]] = []
    for identifier, (path, metadata, _) in tasks.items():
        if normalize_space(metadata.get("visibility") or "active") == "archived":
            continue
        reasons: list[str] = []
        if title and normalize_space(metadata.get("title")).casefold() == title:
            reasons.append("same-title")
        shared_paths = sorted(paths & set(unique_strings(metadata.get("paths"))))
        if shared_paths:
            reasons.append("shared-paths")
        existing_deliverable = normalize_space(metadata.get("deliverable")).casefold()
        if deliverable and existing_deliverable == deliverable:
            reasons.append("same-deliverable")
        if "same-title" in reasons or "same-deliverable" in reasons or len(shared_paths) >= 2:
            candidates.append(
                {
                    "task_id": identifier,
                    "task_note": path.relative_to(root).as_posix(),
                    "task_status": normalize_space(metadata.get("task_status") or "completed"),
                    "revision": int(metadata.get("revision", 1) or 1),
                    "reasons": reasons,
                }
            )
    return candidates


def card_similarity_candidates(
    items: Sequence[dict[str, Any]],
    cards: dict[str, tuple[Path, dict[str, Any], str]],
    root: Path,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items:
        if item.get("operation") == "update":
            continue
        title = normalize_space(item["title"]).casefold()
        fingerprint = item_fingerprint(item)
        item_tokens = lexical_tokens(f"{item['title']} {item['knowledge']}")
        item_paths = set(item["paths"]) | set(scope_paths(item["scopes"]))
        item_topics = set(item["topics"])
        for identifier, (path, metadata, body) in cards.items():
            if normalize_space(metadata.get("status") or "current") != "current":
                continue
            if normalize_space(metadata.get("category")) != item["category"]:
                continue
            if normalize_space(metadata.get("fingerprint")) == fingerprint:
                continue
            if identifier in item["supersedes"]:
                continue
            same_title = normalize_space(metadata.get("title")).casefold() == title
            existing_tokens = lexical_tokens(
                f"{normalize_space(metadata.get('title'))} {extract_section(body, ('结论',))}"
            )
            union = item_tokens | existing_tokens
            similarity = len(item_tokens & existing_tokens) / len(union) if union else 0.0
            try:
                existing_scopes = normalize_scopes(
                    metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
                )
            except KnowledgeError:
                existing_scopes = []
            existing_paths = set(unique_strings(metadata.get("paths"))) | set(scope_paths(existing_scopes))
            existing_topics = set(unique_strings(metadata.get("topics")))
            scope_related = bool(item_paths & existing_paths) or bool(item_topics & existing_topics) or (
                not item_paths and not existing_paths
            )
            if not same_title and not (similarity >= 0.72 and scope_related):
                continue
            blocking = not item["new_card_reason"]
            candidates.append(
                {
                    "item_title": item["title"],
                    "card_id": identifier,
                    "card_path": path.relative_to(root).as_posix(),
                    "reason": "same-category-and-title" if same_title else "high-conclusion-overlap",
                    "similarity": round(similarity, 3),
                    "blocking": blocking,
                    "action": "reuse or update the existing card; provide new_card_reason only for a genuinely orthogonal conclusion",
                }
            )
    return candidates


def knowledge_state_fingerprint(root: Path, config: dict[str, Any]) -> str:
    wiki = wiki_root(root, config)
    paths: set[Path] = set(card_paths(wiki, configured_categories(config)))
    paths.update(task_note_paths(wiki))
    _, outputs = build_index_outputs(root, config)
    paths.update(path for path in outputs if not path.is_relative_to(index_root(root, config)))
    paths.add(root / ".codestable" / "config.json")
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        if source_is_file(path):
            digest.update(source_bytes(path))
        digest.update(b"\0")
    return digest.hexdigest()


def workspace_state_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    git_probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(root),
        capture_output=True,
        check=False,
    )
    if git_probe.returncode == 0:
        head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=str(root), capture_output=True, check=False)
        if head.returncode == 0:
            digest.update(head.stdout)
            diff = subprocess.run(
                ["git", "diff", "--binary", "HEAD", "--", ".", ":(exclude).codestable/**"],
                cwd=str(root),
                capture_output=True,
                check=False,
            )
            if diff.returncode != 0:
                raise KnowledgeError(normalize_space(diff.stderr.decode("utf-8", errors="replace")) or "cannot fingerprint Git worktree")
            digest.update(diff.stdout)
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "-z"],
                cwd=str(root),
                capture_output=True,
                check=False,
            )
            if untracked.returncode != 0:
                raise KnowledgeError(normalize_space(untracked.stderr.decode("utf-8", errors="replace")) or "cannot fingerprint untracked files")
            for raw_path in sorted(value for value in untracked.stdout.split(b"\0") if value):
                relative = raw_path.decode("utf-8", errors="surrogateescape")
                if relative == ".codestable" or relative.startswith(".codestable/"):
                    continue
                path = root / relative
                digest.update(raw_path)
                digest.update(b"\0")
                if source_is_file(path):
                    digest.update(source_bytes(path))
                digest.update(b"\0")
            return digest.hexdigest()
    for path in sorted(value for value in source_glob(root, "*", recursive=True) if source_is_file(value)):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in {".codestable", ".git"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_bytes(path))
        digest.update(b"\0")
    return digest.hexdigest()


def encode_plan_token(
    task_fingerprint_value: str,
    state_fingerprint: str,
    workspace_fingerprint: str,
    timestamp: datetime,
) -> str:
    payload = stable_json(
        {
            "schema_version": 3,
            "task_fingerprint": task_fingerprint_value,
            "state_fingerprint": state_fingerprint,
            "workspace_fingerprint": workspace_fingerprint,
            "timestamp": timestamp.isoformat(timespec="seconds"),
        }
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_plan_token(token: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(token) % 4)
        value = json.loads(base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError("invalid learn plan token") from exc
    if not isinstance(value, dict) or int(value.get("schema_version", 0) or 0) != 3:
        raise KnowledgeError("unsupported mutation plan token")
    return value
