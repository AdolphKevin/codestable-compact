"""CodeStable runtime section: 50 drift."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def run_git(root: Path, arguments: Sequence[str], allow_difference: bool = False) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", *arguments],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    allowed = {0, 1} if allow_difference else {0}
    if process.returncode not in allowed:
        detail = normalize_space(process.stderr) or normalize_space(process.stdout) or "git command failed"
        raise KnowledgeError(detail)
    return process


def git_diff_arguments(cached: bool, base: str | None) -> list[str]:
    if cached and base:
        raise KnowledgeError("drift accepts either --cached or --base, not both")
    if cached:
        return ["diff", "--cached"]
    if base:
        return ["diff", f"{base}...HEAD"]
    return ["diff", "HEAD"]


def git_changes(root: Path, cached: bool, base: str | None) -> tuple[list[GitChange], str, bool]:
    arguments = git_diff_arguments(cached, base)
    names = run_git(root, [*arguments, "--name-status", "-z", "-M", "--"]).stdout
    tokens = names.split("\0")
    if tokens and not tokens[-1]:
        tokens.pop()
    changes: list[GitChange] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                raise KnowledgeError("git returned an incomplete rename/copy record")
            old_path, new_path = tokens[index], tokens[index + 1]
            index += 2
        else:
            if index >= len(tokens):
                raise KnowledgeError("git returned an incomplete change record")
            old_path = new_path = tokens[index]
            index += 1
        changes.append(GitChange(status=status, old_path=old_path, new_path=new_path))
    if not cached and not base:
        untracked = run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).stdout
        for path in sorted(value for value in untracked.split("\0") if value):
            changes.append(GitChange(status="?", old_path=path, new_path=path))
        deleted_changes = [change for change in changes if change.status == "D"]
        untracked_changes = [change for change in changes if change.status == "?"]
        inferred: list[tuple[GitChange, GitChange]] = []
        for deleted_change in deleted_changes:
            try:
                old_hash = run_git(root, ["rev-parse", f"HEAD:{deleted_change.old_path}"]).stdout.strip()
            except KnowledgeError:
                continue
            for untracked_change in untracked_changes:
                try:
                    new_hash = run_git(root, ["hash-object", untracked_change.new_path]).stdout.strip()
                except KnowledgeError:
                    continue
                if old_hash and old_hash == new_hash:
                    inferred.append((deleted_change, untracked_change))
                    untracked_changes.remove(untracked_change)
                    break
        for deleted_change, untracked_change in inferred:
            changes.remove(deleted_change)
            changes.remove(untracked_change)
            changes.append(GitChange(status="R100", old_path=deleted_change.old_path, new_path=untracked_change.new_path))
    patch = run_git(root, [*arguments, "--unified=0", "--"]).stdout
    whitespace = run_git(
        root,
        [*arguments, "-w", "--ignore-blank-lines", "--quiet", "--"],
        allow_difference=True,
    )
    whitespace_only = bool(changes) and whitespace.returncode == 0 and all(
        not change.status.startswith(("R", "C", "D", "?")) for change in changes
    )
    return changes, patch, whitespace_only


def unstaged_wiki_paths(root: Path) -> list[str]:
    changed = run_git(root, ["diff", "--name-only", "-z", "--", ".codestable/wiki"]).stdout
    untracked = run_git(
        root,
        ["ls-files", "--others", "--exclude-standard", "-z", "--", ".codestable/wiki"],
    ).stdout
    return sorted(set(value for value in [*changed.split("\0"), *untracked.split("\0")] if value))


def reference_path_policy(root: Path, value: str) -> tuple[str, Path | None]:
    path = normalize_space(value).replace("\\", "/")
    lowered = path.casefold()
    if re.match(r"^[a-z][a-z0-9+.-]*://", lowered) or lowered.startswith("external:"):
        return "external", None
    if lowered.startswith("generated:"):
        return "generated", None
    if lowered.startswith("legacy:") or lowered in {
        ".codestable/model",
        ".codestable/knowledge",
        ".codestable/backups",
    } or lowered.startswith((".codestable/model/", ".codestable/knowledge/", ".codestable/backups/")):
        return "legacy", None
    if lowered in {".codestable/wiki/index.md", ".codestable/wiki/index.jsonl"} or (
        lowered.startswith(".codestable/wiki/") and lowered.endswith("/index.md")
    ):
        return "generated", None
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            return "external", None
        return "repository", candidate.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return "external", None
    return "repository", resolved


def candidate_source_files(root: Path, paths: Sequence[Path], limit: int) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidates = [path] if source_is_file(path) else sorted(source_glob(path, "*", recursive=True)) if source_is_dir(path) else []
        for candidate in candidates:
            if len(files) >= limit:
                return files
            if not source_is_file(candidate) or candidate in seen or ".git" in candidate.parts:
                continue
            seen.add(candidate)
            files.append(candidate)
    if files:
        return files
    try:
        tracked = run_git(root, ["ls-files", "-z"]).stdout
    except KnowledgeError:
        return []
    for value in tracked.split("\0"):
        if not value or value.startswith(".codestable/"):
            continue
        candidate = root / value
        if source_is_file(candidate):
            files.append(candidate)
            if len(files) >= limit:
                break
    return files


def symbol_present(symbol: str, files: Sequence[Path]) -> tuple[bool, bool]:
    texts: list[str] = []
    checked = False
    for path in files:
        try:
            if source_size(path) > 2_000_000:
                continue
            texts.append(source_text(path, encoding="utf-8", errors="ignore"))
            checked = True
        except OSError:
            continue
    content = "\n".join(texts)
    if not checked:
        return False, False
    if symbol in content:
        return True, True
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u3400-\u9fff]+", symbol)
    return bool(parts) and all(re.search(rf"(?<!\w){re.escape(part)}(?!\w)", content) for part in parts), True


def current_reference_drift(
    root: Path,
    config: dict[str, Any],
    changes: Sequence[GitChange] = (),
    card_ids: Sequence[str] = (),
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, _ = scan_existing_records(wiki, configured_categories(config))
    rename_map = {change.old_path: change.new_path for change in changes if change.status.startswith("R")}
    deleted = {change.old_path for change in changes if change.status == "D"}
    findings: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    historical_skipped: list[dict[str, Any]] = []
    repositories = configured_repositories(root, config)
    scan_limit = safe_int((config.get("wiki") or {}).get("max_scan_files"), 2000, minimum=1, maximum=20_000)
    for card_id, (_, metadata, _) in sorted(cards.items()):
        if card_ids and card_id not in card_ids:
            continue
        status = normalize_space(metadata.get("status"))
        if status != "current":
            historical_skipped.append(
                {
                    "card_id": card_id,
                    "issue_type": "historical-card-skipped",
                    "status": status,
                    "disposition": "non-blocking",
                    "detail": "historical cards do not participate in current-reference blocking",
                }
            )
            continue
        common = {
            "card_id": card_id,
            "category": normalize_space(metadata.get("category")),
            "title": normalize_space(metadata.get("title")),
        }
        repository_paths: list[Path] = []
        raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            scopes = normalize_scopes(raw_scopes)
        except KnowledgeError as exc:
            unverified.append(
                {
                    **common,
                    "issue_type": "scope-invalid",
                    "certainty": "unverified",
                    "detail": str(exc),
                    "suggested_action": "repair the structured scope before relying on reference validation",
                }
            )
            scopes = []
        for scope in scopes:
            repository = scope["repository"]
            scoped_path = scope["path"]
            symbol = scope["symbol"]
            repository_root = repositories.get(repository)
            if repository_root is None:
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unconfigured",
                        "repository": repository,
                        "value": scoped_path or symbol,
                        "certainty": "unverified",
                        "suggested_action": f"configure wiki.repositories.{repository}.root to enable validation",
                    }
                )
                continue
            if not source_is_dir(repository_root):
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unavailable",
                        "repository": repository,
                        "value": scoped_path or symbol,
                        "certainty": "unverified",
                        "suggested_action": "make the configured repository available or correct its local mapping",
                    }
                )
                continue
            resolved = repository_root / scoped_path if scoped_path else repository_root
            relative = scoped_path
            if repository == "self" and relative in rename_map:
                findings.append(
                    {
                        **common,
                        "issue_type": "path-renamed",
                        "repository": repository,
                        "value": relative,
                        "renamed_to": rename_map[relative],
                        "certainty": "likely",
                        "suggested_action": "review the unchanged conclusion and update its scope, or supersede it only if the conclusion changed",
                    }
                )
                continue
            if repository == "self" and relative in deleted:
                findings.append(
                    {
                        **common,
                        "issue_type": "path-deleted",
                        "repository": repository,
                        "value": relative,
                        "certainty": "confirmed",
                        "suggested_action": "review the conclusion and update its scope or supersede it after semantic review",
                    }
                )
                continue
            if scoped_path and not source_exists(resolved):
                findings.append(
                    {
                        **common,
                        "issue_type": "path-missing",
                        "repository": repository,
                        "value": scoped_path,
                        "certainty": "confirmed",
                        "suggested_action": "locate the replacement implementation and update scope, or supersede the card only if its conclusion changed",
                    }
                )
                continue
            if scoped_path:
                repository_paths.append(resolved)
                verified.append(
                    {
                        **common,
                        "issue_type": "path-verified",
                        "repository": repository,
                        "value": scoped_path,
                        "reference_format": "structured",
                    }
                )
            if symbol:
                files = candidate_source_files(repository_root, [resolved] if scoped_path else [], scan_limit)
                present, checked = symbol_present(symbol, files)
                if present:
                    verified.append(
                        {**common, "issue_type": "symbol-verified", "repository": repository, "value": symbol}
                    )
                else:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable" if not checked else "symbol-text-not-found",
                            "repository": repository,
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                            "suggested_action": "review the implementation or rename; text scanning alone cannot prove the knowledge wrong",
                        }
                    )
        legacy_path_values = unique_strings(metadata.get("paths"))
        for raw_path in legacy_path_values:
            policy, resolved = reference_path_policy(root, raw_path)
            if policy != "repository":
                unverified.append(
                    {
                        **common,
                        "issue_type": "legacy-reference-unverified",
                        "value": raw_path,
                        "policy": policy,
                        "certainty": "unverified",
                        "reference_format": "legacy",
                        "suggested_action": "keep the explicit path policy or replace it with a repository-relative path if source checking is required",
                    }
                )
                continue
            assert resolved is not None
            relative = resolved.relative_to(root).as_posix()
            if relative in rename_map:
                findings.append(
                    {
                        **common,
                        "issue_type": "path-renamed",
                        "value": relative,
                        "renamed_to": rename_map[relative],
                        "suggested_action": "review the card against the renamed implementation, then update its scope or supersede it",
                    }
                )
            elif relative in deleted:
                findings.append(
                    {
                        **common,
                        "issue_type": "path-deleted",
                        "value": relative,
                        "certainty": "confirmed",
                        "suggested_action": "review whether the conclusion still applies elsewhere; update or supersede the current card",
                    }
                )
            elif not source_exists(resolved):
                findings.append(
                    {
                        **common,
                        "issue_type": "path-missing",
                        "value": relative,
                        "certainty": "confirmed",
                        "suggested_action": "locate the replacement implementation and update scope, or supersede the card after semantic review",
                    }
                )
            else:
                repository_paths.append(resolved)
                verified.append(
                    {
                        **common,
                        "issue_type": "path-verified",
                        "repository": "self",
                        "value": relative,
                        "reference_format": "legacy-relative",
                    }
                )
        symbols = unique_strings(metadata.get("symbols"))
        if symbols:
            files = (
                candidate_source_files(root, repository_paths, scan_limit)
                if repository_paths or not legacy_path_values
                else []
            )
            for symbol in symbols:
                present, checked = symbol_present(symbol, files)
                if not checked:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable",
                            "value": symbol,
                            "policy": "no-readable-source",
                            "suggested_action": "provide a repository path for deterministic symbol checking",
                        }
                    )
                elif not present:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-text-not-found",
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                            "suggested_action": "review rename/removal and update or supersede the card; text scanning is only a drift candidate",
                        }
                    )
                else:
                    verified.append(
                        {**common, "issue_type": "symbol-verified", "repository": "self", "value": symbol}
                    )
    title_groups: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    for card_id, (_, metadata, _) in cards.items():
        if normalize_space(metadata.get("status")) != "current":
            continue
        key = (normalize_space(metadata.get("category")), normalize_space(metadata.get("title")).casefold())
        title_groups.setdefault(key, []).append((card_id, metadata))
    for (category, _), group in sorted(title_groups.items()):
        if len(group) < 2:
            continue
        scoped = []
        for _, metadata in group:
            values = set(unique_strings(metadata.get("paths")))
            try:
                values.update(
                    f"{scope['repository']}:{scope['path']}"
                    for scope in normalize_scopes(metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [])
                    if scope["path"]
                )
            except KnowledgeError:
                pass
            scoped.append(values)
        overlaps = any(not left or not right or bool(left & right) for index, left in enumerate(scoped) for right in scoped[index + 1 :])
        if not overlaps:
            continue
        first_id, first_metadata = group[0]
        findings.append(
            {
                "card_id": first_id,
                "related_card_ids": [card_id for card_id, _ in group[1:]],
                "category": category,
                "title": normalize_space(first_metadata.get("title")),
                "issue_type": "overlapping-current-cards",
                "value": ", ".join(card_id for card_id, _ in group),
                "suggested_action": "reuse or merge an equivalent current card, or explicitly supersede the replaced conclusion",
            }
        )
    skipped.extend(unverified)
    skipped.extend(historical_skipped)
    return {
        "findings": findings,
        "unverified": unverified,
        "verified": verified,
        "skipped": skipped,
        "historical_cards_skipped": historical_skipped,
        "checked_current_cards": sum(
            1 for identifier, (_, metadata, _) in cards.items()
            if normalize_space(metadata.get("status")) == "current" and (not card_ids or identifier in card_ids)
        ),
    }


def learning_reference_check(
    root: Path,
    config: dict[str, Any],
    task: dict[str, Any],
    items: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    repositories = configured_repositories(root, config)
    scan_limit = safe_int((config.get("wiki") or {}).get("max_scan_files"), 2000, minimum=1, maximum=20_000)
    findings: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    task_deleted_paths: set[str] = set()
    task_renamed_paths: dict[str, str] = {}
    try:
        task_changes, _, _ = git_changes(root, cached=False, base=None)
        task_deleted_paths = {change.old_path for change in task_changes if change.status == "D"}
        task_renamed_paths = {
            change.old_path: change.new_path
            for change in task_changes
            if change.status.startswith("R")
        }
    except KnowledgeError:
        pass
    records = [
        {
            "record_type": "task",
            "title": task["title"],
            "scopes": task["scopes"],
            "paths": task["paths"],
            "symbols": task["symbols"],
        },
        *[
            {
                "record_type": "planned-card",
                "title": item["title"],
                "scopes": item["scopes"],
                "paths": item["paths"],
                "symbols": item["symbols"],
            }
            for item in items
        ],
    ]
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        common = {"record_type": record["record_type"], "title": record["title"]}
        checked_files: list[Path] = []
        for scope in record["scopes"]:
            repository = scope["repository"]
            path = scope["path"]
            symbol = scope["symbol"]
            key = (record["record_type"], repository, path, symbol)
            if key in seen:
                continue
            seen.add(key)
            repository_root = repositories.get(repository)
            if repository_root is None:
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unconfigured",
                        "repository": repository,
                        "value": path or symbol,
                        "certainty": "unverified",
                    }
                )
                continue
            if not source_is_dir(repository_root):
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unavailable",
                        "repository": repository,
                        "value": path or symbol,
                        "certainty": "unverified",
                    }
                )
                continue
            resolved = repository_root / path if path else repository_root
            if path and not source_exists(resolved):
                if record["record_type"] == "task" and repository == "self" and path in task_deleted_paths:
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-deletion-verified",
                            "repository": repository,
                            "value": path,
                            "change_status": "deleted",
                        }
                    )
                    continue
                if record["record_type"] == "task" and repository == "self" and path in task_renamed_paths:
                    renamed_to = task_renamed_paths[path]
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-rename-verified",
                            "repository": repository,
                            "value": path,
                            "renamed_to": renamed_to,
                            "change_status": "renamed",
                        }
                    )
                    resolved = repository_root / renamed_to
                else:
                    findings.append(
                        {
                            **common,
                            "issue_type": "path-missing",
                            "repository": repository,
                            "value": path,
                            "certainty": "confirmed",
                            "suggested_action": "review this task or card scope before relying on it",
                        }
                    )
                    continue
            if path:
                checked_files.append(resolved)
                if path not in task_renamed_paths or record["record_type"] != "task" or repository != "self":
                    verified.append({**common, "issue_type": "path-verified", "repository": repository, "value": path})
            if symbol:
                files = candidate_source_files(repository_root, [resolved] if path else [], scan_limit)
                present, checked = symbol_present(symbol, files)
                if present:
                    verified.append({**common, "issue_type": "symbol-verified", "repository": repository, "value": symbol})
                else:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable" if not checked else "symbol-text-not-found",
                            "repository": repository,
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                        }
                    )
        legacy_paths: list[Path] = []
        for value in record["paths"]:
            policy, resolved = reference_path_policy(root, value)
            if policy != "repository":
                unverified.append(
                    {
                        **common,
                        "issue_type": "legacy-reference-unverified",
                        "value": value,
                        "policy": policy,
                        "certainty": "unverified",
                    }
                )
            elif resolved is not None and source_exists(resolved):
                legacy_paths.append(resolved)
                verified.append(
                    {
                        **common,
                        "issue_type": "path-verified",
                        "repository": "self",
                        "value": resolved.relative_to(root).as_posix(),
                        "reference_format": "legacy-relative",
                    }
                )
            elif resolved is not None:
                relative = resolved.relative_to(root).as_posix()
                if record["record_type"] == "task" and relative in task_deleted_paths:
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-deletion-verified",
                            "repository": "self",
                            "value": relative,
                            "change_status": "deleted",
                            "reference_format": "legacy-relative",
                        }
                    )
                elif record["record_type"] == "task" and relative in task_renamed_paths:
                    renamed_to = task_renamed_paths[relative]
                    renamed_path = root / renamed_to
                    legacy_paths.append(renamed_path)
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-rename-verified",
                            "repository": "self",
                            "value": relative,
                            "renamed_to": renamed_to,
                            "change_status": "renamed",
                            "reference_format": "legacy-relative",
                        }
                    )
                else:
                    findings.append(
                        {
                            **common,
                            "issue_type": "path-missing",
                            "repository": "self",
                            "value": relative,
                            "certainty": "confirmed",
                        }
                    )
        if record["symbols"]:
            files = (
                candidate_source_files(root, legacy_paths, scan_limit)
                if legacy_paths or not record["paths"]
                else []
            )
            for symbol in record["symbols"]:
                present, checked = symbol_present(symbol, files)
                if present:
                    verified.append({**common, "issue_type": "symbol-verified", "repository": "self", "value": symbol})
                else:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable" if not checked else "symbol-text-not-found",
                            "repository": "self",
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                        }
                    )
    used_cards = current_reference_drift(
        root,
        config,
        card_ids=[value["card_id"] for value in task["knowledge_use"]],
    ) if task["knowledge_use"] else {"findings": [], "unverified": [], "verified": [], "historical_cards_skipped": []}
    findings.extend(used_cards["findings"])
    unverified.extend(used_cards["unverified"])
    verified.extend(used_cards["verified"])
    return {
        "blocking": False,
        "review_required": bool(findings or unverified),
        "findings": findings,
        "unverified": unverified,
        "verified": verified,
        "historical_cards_skipped": used_cards["historical_cards_skipped"],
    }


def is_generated_or_knowledge_path(path: str) -> bool:
    lowered = path.casefold()
    return (
        lowered.startswith(".codestable/wiki/")
        or lowered in {"validation/release-report.json", "validation/release-report.md"}
        or lowered.endswith((".generated.md", ".generated.json", ".min.js", ".min.css"))
    )


def is_docs_only_path(path: str) -> bool:
    return Path(path).suffix.casefold() in {".md", ".rst", ".txt", ".adoc"}


def path_is_covered(scope: str, changed: str) -> bool:
    normalized = scope.rstrip("/")
    return changed == normalized or changed.startswith(normalized + "/")


def task_note_scope_paths(metadata: dict[str, Any]) -> list[str]:
    values = list(unique_strings(metadata.get("paths")))
    raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
    try:
        values.extend(
            scope["path"]
            for scope in normalize_scopes(raw_scopes)
            if scope["repository"] == "self" and scope["path"]
        )
    except KnowledgeError:
        pass
    return unique_strings(values)


def task_note_drift(root: Path, changes: Sequence[GitChange], patch: str, whitespace_only: bool) -> dict[str, Any]:
    changed_notes = [
        change.new_path
        for change in changes
        if change.status != "D" and change.new_path.startswith(".codestable/wiki/task-notes/") and change.new_path.endswith(".md")
    ]
    semantic_changes = [
        change
        for change in changes
        if not is_generated_or_knowledge_path(change.new_path) and not is_docs_only_path(change.new_path)
    ]
    if whitespace_only:
        semantic_changes = []
    primary_paths = [change.new_path for change in semantic_changes if not re.search(r"(^|/)(tests?|fixtures?)(/|$)", change.new_path)]
    if not primary_paths:
        primary_paths = [change.new_path for change in semantic_changes]
    primary_paths = sorted(set(primary_paths))
    findings: list[dict[str, Any]] = []
    if not semantic_changes:
        return {
            "semantic_change": False,
            "classification": "mechanical-or-docs-only",
            "primary_paths": [],
            "task_notes": changed_notes,
            "findings": findings,
        }
    if not changed_notes:
        findings.append(
            {
                "issue_type": "missing-task-note",
                "value": ", ".join(primary_paths),
                "suggested_action": "complete CodeStable learn dry-run/apply before commit; a durable card is not required when no reusable fact exists",
            }
        )
        return {
            "semantic_change": True,
            "classification": "semantic-candidate",
            "primary_paths": primary_paths,
            "task_notes": [],
            "findings": findings,
        }
    candidates: list[tuple[int, str, dict[str, Any], str]] = []
    for relative in changed_notes:
        path = root / relative
        if not source_is_file(path):
            continue
        metadata, body, _ = read_markdown(path)
        scopes = task_note_scope_paths(metadata)
        coverage = sum(any(path_is_covered(scope, changed) for scope in scopes) for changed in primary_paths)
        if not coverage and any(symbol and symbol in patch for symbol in unique_strings(metadata.get("symbols"))):
            coverage = 1
        candidates.append((coverage, relative, metadata, body))
    if not candidates:
        findings.append(
            {
                "issue_type": "missing-readable-task-note",
                "value": ", ".join(changed_notes),
                "suggested_action": "restore or regenerate the changed task-note before commit",
            }
        )
    else:
        coverage, relative, metadata, body = max(candidates, key=lambda item: (item[0], item[1]))
        common = {"task_id": normalize_space(metadata.get("id")), "task_note": relative, "title": normalize_space(metadata.get("title"))}
        scopes = task_note_scope_paths(metadata)
        symbol_overlap = any(symbol and symbol in patch for symbol in unique_strings(metadata.get("symbols")))
        if coverage == 0 and not symbol_overlap:
            findings.append(
                {
                    **common,
                    "issue_type": "task-scope-mismatch",
                    "value": ", ".join(primary_paths),
                    "suggested_action": "record at least one representative task path, structured self scope, or changed symbol",
                }
            )
        if normalize_space(metadata.get("task_status")) != "completed":
            findings.append(
                {
                    **common,
                    "issue_type": "task-not-completed",
                    "value": normalize_space(metadata.get("task_status")),
                    "suggested_action": "record the final outcome and update the logical task to completed after acceptance",
                }
            )
        result = extract_section(body, ("最终结果",))
        # A saved or applied plan is an outcome; the noun alone is not pending work.
        if not result or re.search(r"(?:TODO|TBD|待完成|计划(?:稍后|后续|之后|接下来)|将要|尚未完成)", result, re.IGNORECASE):
            findings.append(
                {
                    **common,
                    "issue_type": "task-final-result-missing",
                    "value": result or "missing",
                    "suggested_action": "replace plans with the final observable result",
                }
            )
        verification = extract_section(body, ("验证",))
        if not verification or verification in {"无", "未记录"}:
            findings.append(
                {
                    **common,
                    "issue_type": "task-verification-missing",
                    "value": verification or "missing",
                    "suggested_action": "record the verification actually run; do not claim evidence that was not obtained",
                }
            )
        knowledge_summary = normalize_space(metadata.get("knowledge_summary")) or extract_section(body, ("知识处置",))
        if not knowledge_summary or knowledge_summary.startswith("未说明"):
            findings.append(
                {
                    **common,
                    "issue_type": "task-knowledge-disposition-missing",
                    "value": "missing",
                    "suggested_action": "state which cards were created, reused or superseded, or why no durable card was needed",
                }
            )
    return {
        "semantic_change": True,
        "classification": "semantic-candidate",
        "primary_paths": primary_paths,
        "task_notes": changed_notes,
        "findings": findings,
    }


def drift_payload(
    root: Path,
    config: dict[str, Any],
    cached: bool = False,
    base: str | None = None,
    references_only: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if (cached or base) and READ_VIEW.get() is None:
        with git_read_view(root, ":" if cached else "HEAD"):
            return drift_payload(root, load_config(root), cached=cached, base=base, references_only=references_only)
    root = root.expanduser().resolve()
    changes: list[GitChange] = []
    patch = ""
    whitespace_only = False
    if not references_only:
        changes, patch, whitespace_only = git_changes(root, cached, base)
    references = current_reference_drift(root, config, changes)
    task_check = (
        {"semantic_change": False, "classification": "references-only", "primary_paths": [], "task_notes": [], "findings": []}
        if references_only
        else task_note_drift(root, changes, patch, whitespace_only)
    )
    findings = [*references["findings"], *task_check["findings"]]
    if READ_VIEW.get() is not None:
        structure = doctor(root, config)
        findings.extend({"issue_type": value["code"], "detail": value["detail"]} for value in structure["errors"])
    mode = "references-only" if references_only else "cached" if cached else f"base:{base}" if base else "working-tree"
    return {
        "ok": not findings,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "mode": mode,
        "knowledge_source": "git-index" if cached else "HEAD" if base else "working-tree",
        "exit_code": 0 if not findings else 1,
        "summary": {
            "findings": len(findings),
            "skipped_references": len(references["skipped"]),
            "current_cards_checked": references["checked_current_cards"],
            "git_changes": len(changes),
            "semantic_change": task_check["semantic_change"],
        },
        "findings": findings,
        "skipped_references": references["skipped"],
        "unverified_references": references["unverified"],
        "verified_references": references["verified"],
        "historical_cards_skipped": references["historical_cards_skipped"],
        "git": {
            "classification": task_check["classification"],
            "primary_paths": task_check["primary_paths"],
            "task_notes": task_check["task_notes"],
            "changes": [change.__dict__ for change in changes],
        },
        "limits": [
            "drift reports deterministic candidates; it does not decide whether a business conclusion is true",
            "symbol checks are conservative text scans and do not replace implementation/test review",
        ],
    }


def render_drift_text(payload: dict[str, Any]) -> str:
    lines = [
        f"CodeStable drift · {payload['mode']}",
        f"result: {'PASS' if payload['ok'] else 'ACTION REQUIRED'} · findings={payload['summary']['findings']} · git_changes={payload['summary']['git_changes']}",
    ]
    if payload["findings"]:
        lines.append("")
        for finding in payload["findings"]:
            owner = finding.get("card_id") or finding.get("task_id") or "git"
            if finding.get("card_id"):
                owner = f"{owner} {finding.get('category') or 'uncategorized'} / {finding.get('title') or 'untitled'}"
            elif finding.get("task_id") and finding.get("title"):
                owner = f"{owner} / {finding['title']}"
            value = finding.get("value") or ""
            lines.append(f"- [{finding['issue_type']}] {owner}: {value}")
            lines.append(f"  action: {finding['suggested_action']}")
    if payload["skipped_references"]:
        lines.extend(("", f"unverified or historical references: {len(payload['skipped_references'])}"))
    lines.extend(("", "drift is read-only and reports candidates; semantic truth still requires requirement, code and test review.", ""))
    return "\n".join(lines)


def agents_entry_check(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    wiki_config = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    current_entry = normalize_space(wiki_config.get("current_entry") or CURRENT_ENTRY)
    retired_roots = (".codestable/model", ".codestable/knowledge")
    files: list[str] = []
    findings: list[dict[str, Any]] = []
    declared: set[str] = set()
    for path in sorted(source_glob(root, "AGENTS.md", recursive=True)):
        relative = path.relative_to(root).as_posix()
        if any(part == ".git" for part in path.parts) or relative.startswith(".codestable/backups/"):
            continue
        content = safe_read_text(path)
        if not content:
            continue
        files.append(relative)
        for number, line in enumerate(content.splitlines(), start=1):
            for match in ENTRY_PATH_PATTERN.finditer(line):
                entry = match.group(1).removeprefix("./")
                if not entry.casefold().endswith(("/index.md", "/readme.md")):
                    continue
                declared.add(entry)
                common = {"file": relative, "line": number, "entry": entry}
                if not source_is_file(root / entry):
                    findings.append(
                        {
                            "code": "agents.entry.missing",
                            **common,
                            "detail": f"AGENTS.md points to a missing CodeStable entry: {entry}",
                            "action": f"replace it with {current_entry}",
                        }
                    )
                if any(entry == value or entry.startswith(value + "/") for value in retired_roots):
                    findings.append(
                        {
                            "code": "agents.entry.retired",
                            **common,
                            "detail": f"AGENTS.md points to a retired CodeStable entry: {entry}",
                            "action": f"use {current_entry}; rebuild knowledge from current source and tests",
                        }
                    )
    if len(declared) > 1:
        findings.append(
            {
                "code": "agents.entry.conflict",
                "entries": sorted(declared),
                "detail": "AGENTS.md declares multiple CodeStable knowledge entries",
                "action": f"keep only {current_entry} as the current entry",
            }
        )
    return {"current_entry": current_entry, "files_checked": files, "findings": findings, "modified": False}
