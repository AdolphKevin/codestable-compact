"""CodeStable runtime section: 40 retrieval."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def lexical_tokens(value: str) -> set[str]:
    text = value.lower()
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9_.:/-]*", text):
        for part in re.split(r"[_.:/-]+", token):
            if len(part) >= 2 and part not in STOPWORDS:
                tokens.add(part)
        if len(token) >= 2 and token not in STOPWORDS:
            tokens.add(token)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        if run not in STOPWORDS and 1 < len(run) <= 16:
            tokens.add(run)
        if len(run) >= 2:
            for width in (2, 3):
                if len(run) >= width:
                    for index in range(len(run) - width + 1):
                        token = run[index : index + width]
                        if token not in STOPWORDS:
                            tokens.add(token)
    return tokens


def conclusion_similarity(left: str, right: str) -> float:
    """Return deterministic lexical overlap for two non-empty conclusions."""
    left_tokens = lexical_tokens(normalize_space(left))
    right_tokens = lexical_tokens(normalize_space(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def inferred_categories(text: str, include_default_acceptance: bool = True) -> set[str]:
    lowered = text.lower()
    categories: set[str] = set()
    for category, definition in CATEGORY_DEFS.items():
        for alias in definition["aliases"]:
            if str(alias).lower() in lowered:
                categories.add(category)
                break
    # Every implementation should have an observable acceptance contract.
    if include_default_acceptance and normalize_space(text):
        categories.add("acceptance")
    return categories


def infer_legacy_category(path: Path, content: str) -> str | None:
    value = f"{path.as_posix()} {content[:2000]}".lower()
    direct = {
        "decisions": ("decision", "decisions", "adr", "决策"),
        "requirements": ("requirement", "requirements", "需求"),
        "interfaces": ("contract", "contracts", "api", "interface", "接口"),
        "architecture": ("architecture", "domain", "vision", "架构"),
        "acceptance": ("acceptance", "验收"),
    }
    for category, aliases in direct.items():
        if any(alias in value for alias in aliases):
            return category
    hinted = inferred_categories(value)
    return sorted(hinted)[0] if hinted else None


def safe_read_text(path: Path, maximum_bytes: int = 512 * 1024) -> str:
    try:
        if path.stat().st_size > maximum_bytes:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def collect_search_documents(
    root: Path,
    config: dict[str, Any],
    include_history: bool,
    include_legacy: bool = False,
) -> tuple[list[SearchDocument], list[str]]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    categories = configured_categories(config)
    documents: list[SearchDocument] = []
    warnings: list[str] = []

    project_path = wiki / "PROJECT.md"
    if project_path.is_file():
        content = extract_canonical(safe_read_text(project_path))
        if content:
            documents.append(
                SearchDocument(
                    source_type="project-overview",
                    source_path=project_path.relative_to(root).as_posix(),
                    title="Project Overview",
                    content=content,
                    status="navigation",
                    confidence="not-applicable",
                    pinned=True,
                )
            )

    for category in categories:
        readme = wiki / category / "README.md"
        if readme.is_file():
            content = extract_canonical(safe_read_text(readme))
            if content:
                documents.append(
                    SearchDocument(
                        source_type="canonical-page",
                        source_path=readme.relative_to(root).as_posix(),
                        title=f"{CATEGORY_DEFS[category]['label']}人工摘要",
                        content=content,
                        category=category,
                        status="navigation",
                        confidence="not-applicable",
                        content_hash=sha256_text(content),
                    )
                )

    for path in card_paths(wiki, categories):
        try:
            metadata, body, _ = read_markdown(path)
        except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
            warnings.append(f"cannot read card {path.relative_to(root).as_posix()}: {exc}")
            continue
        status = normalize_space(metadata.get("status") or "current")
        if status in {"deprecated", "superseded"} and not include_history:
            continue
        raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            scopes = normalize_scopes(raw_scopes)
        except KnowledgeError as exc:
            warnings.append(f"invalid scopes on card {path.relative_to(root).as_posix()}: {exc}")
            scopes = []
        documents.append(
            SearchDocument(
                source_type="knowledge-card",
                source_path=path.relative_to(root).as_posix(),
                title=normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
                content=extract_section(body, ("结论",)) or body,
                category=normalize_space(metadata.get("category")) or None,
                identifier=normalize_space(metadata.get("id")) or None,
                status=status,
                confidence=normalize_space(metadata.get("confidence") or "accepted"),
                tags=tuple(unique_strings(metadata.get("tags"))),
                topics=tuple(unique_strings(metadata.get("topics"))),
                scopes=tuple(scope_tuple(value) for value in scopes),
                paths=tuple(unique_strings([*unique_strings(metadata.get("paths")), *scope_paths(scopes)])),
                symbols=tuple(unique_strings([*unique_strings(metadata.get("symbols")), *scope_symbols(scopes)])),
                created_at=normalize_space(metadata.get("created_at")),
                updated_at=normalize_space(metadata.get("updated_at")),
                revision=safe_int(metadata.get("revision"), 1, minimum=0),
                content_hash=sha256_text(normalize_space(extract_section(body, ("结论",)) or body)),
                pinned=bool(metadata.get("pinned", False)),
            )
        )

    for path in task_note_paths(wiki):
        try:
            metadata, body, _ = read_markdown(path)
        except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
            warnings.append(f"cannot read task note {path.relative_to(root).as_posix()}: {exc}")
            continue
        if normalize_space(metadata.get("visibility") or "active") == "archived":
            continue
        content = " ".join(
            filter(
                None,
                (
                    extract_section(body, ("请求",)),
                    extract_section(body, ("处理摘要",)),
                    extract_section(body, ("最终结果",)),
                ),
            )
        )
        raw_task_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            task_scopes = normalize_scopes(raw_task_scopes)
        except KnowledgeError as exc:
            warnings.append(f"invalid scopes on task note {path.relative_to(root).as_posix()}: {exc}")
            task_scopes = []
        documents.append(
            SearchDocument(
                source_type="task-note",
                source_path=path.relative_to(root).as_posix(),
                title=normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
                content=content or body,
                identifier=normalize_space(metadata.get("id")) or None,
                status=normalize_space(metadata.get("task_status") or "completed"),
                tags=tuple(unique_strings(metadata.get("tags"))),
                topics=tuple(unique_strings(metadata.get("topics"))),
                scopes=tuple(scope_tuple(value) for value in task_scopes),
                paths=tuple(unique_strings(metadata.get("paths"))),
                symbols=tuple(unique_strings(metadata.get("symbols"))),
                created_at=normalize_space(metadata.get("created_at")),
                updated_at=normalize_space(metadata.get("updated_at")),
            )
        )

    if include_legacy:
        wiki_config = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
        legacy_roots = unique_strings(wiki_config.get("legacy_read_roots"))
        max_files = safe_int(wiki_config.get("max_scan_files"), 2000, minimum=1, maximum=20_000)
        scanned = 0
        for relative in legacy_roots:
            try:
                legacy_root = resolve_inside(root, relative)
            except KnowledgeError as exc:
                warnings.append(str(exc))
                continue
            if not legacy_root.is_dir():
                continue
            for path in sorted(legacy_root.rglob("*.md")):
                scanned += 1
                if scanned > max_files:
                    warnings.append(f"legacy scan stopped at configured max_scan_files={max_files}")
                    break
                content = safe_read_text(path)
                if not content:
                    continue
                documents.append(
                    SearchDocument(
                        source_type="legacy-page",
                        source_path=path.relative_to(root).as_posix(),
                        title=extract_heading(content, path.stem),
                        content=content,
                        category=infer_legacy_category(path, content),
                        status="legacy",
                    )
                )
            if scanned > max_files:
                break
    return documents, warnings


def scope_path_match(query_path: str, scoped_path: str) -> bool:
    left = query_path.strip("./")
    right = scoped_path.strip("./")
    return bool(left and right and (left == right or left.startswith(right + "/") or right.startswith(left + "/")))


def parse_scope_argument(value: str) -> dict[str, str]:
    text = normalize_space(value)
    if ":" not in text:
        raise KnowledgeError("brief --scope must use <repository>:<path>#<symbol>")
    repository, remainder = text.split(":", 1)
    if "#" in remainder:
        path, symbol = remainder.split("#", 1)
    else:
        path, symbol = remainder, ""
    scopes = normalize_scopes([{"repository": repository, "path": path, "symbol": symbol}])
    return scopes[0]


def score_document_details(
    document: SearchDocument,
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
    topics: Sequence[str] = (),
    scopes: Sequence[dict[str, str]] = (),
) -> MatchDetails:
    query_text = " ".join((task, *paths, *symbols, *topics))
    query_tokens = lexical_tokens(query_text)
    title_tokens = lexical_tokens(document.title)
    content_tokens = lexical_tokens(document.content)
    tag_tokens = lexical_tokens(" ".join(document.tags))
    symbol_tokens = lexical_tokens(" ".join(document.symbols))
    scoped_path_tokens = lexical_tokens(" ".join(document.paths))
    source_path_tokens = lexical_tokens(document.source_path)
    path_tokens = scoped_path_tokens | source_path_tokens
    title_overlap = query_tokens & title_tokens
    content_overlap = query_tokens & content_tokens
    tag_overlap = query_tokens & tag_tokens
    symbol_overlap = query_tokens & symbol_tokens
    scoped_path_overlap = query_tokens & scoped_path_tokens
    meaningful_path_overlap = scoped_path_overlap - PATH_SIGNAL_STOPWORDS
    score = 0.0
    score += 7.0 * len(title_overlap)
    score += 5.0 * len(tag_overlap)
    score += 9.0 * len(symbol_overlap)
    score += 6.0 * len(query_tokens & path_tokens)
    score += 1.25 * len(content_overlap)
    reasons: list[tuple[str, str, str]] = []
    precedence = 0
    exact_path_match = False
    hierarchical_path_match = False
    for query_path in paths:
        normalized_query = query_path.strip("./")
        exact_candidates = [value for value in document.paths if normalized_query == value.strip("./")]
        hierarchy_candidates = [
            value for value in document.paths
            if normalized_query != value.strip("./") and scope_path_match(query_path, value)
        ]
        if exact_candidates:
            score += 24.0
            exact_path_match = True
            precedence = max(precedence, 6)
            reasons.append(("exact-path", query_path, exact_candidates[0]))
        elif hierarchy_candidates:
            score += 16.0
            hierarchical_path_match = True
            precedence = max(precedence, 5)
            reasons.append(("path-hierarchy", query_path, hierarchy_candidates[0]))
        elif scope_path_match(query_path, document.source_path):
            score += 10.0
            hierarchical_path_match = True
            precedence = max(precedence, 5)
            reasons.append(("source-path-hierarchy", query_path, document.source_path))
    lowered_symbols = {symbol.lower() for symbol in symbols}
    matched_symbols = lowered_symbols & {symbol.lower() for symbol in document.symbols}
    exact_symbol_match = bool(matched_symbols)
    if exact_symbol_match:
        score += 24.0
        precedence = max(precedence, 6)
        matched = sorted(matched_symbols)[0]
        original = next(value for value in document.symbols if value.lower() == matched)
        reasons.append(("exact-symbol", original, original))
    matched_topics = set(topics) & set(document.topics)
    exact_topic_match = bool(matched_topics)
    if exact_topic_match:
        score += 18.0
        precedence = max(precedence, 4)
        topic = sorted(matched_topics)[0]
        reasons.append(("topic", topic, topic))
    exact_scope_match = False
    hierarchical_scope_match = False
    document_scopes = set(document.scopes)
    for scope in scopes:
        repository, path, symbol = scope_tuple(scope)
        for candidate_repository, candidate_path, candidate_symbol in document_scopes:
            if repository != candidate_repository:
                continue
            path_exact = not path or path.strip("./") == candidate_path.strip("./")
            path_matches = not path or scope_path_match(path, candidate_path)
            symbol_matches = not symbol or symbol.casefold() == candidate_symbol.casefold()
            if path_exact and symbol_matches:
                exact_scope_match = True
                score += 30.0
                precedence = max(precedence, 6)
                query_value = f"{repository}:{path}#{symbol}".rstrip("#")
                matched_value = f"{candidate_repository}:{candidate_path}#{candidate_symbol}".rstrip("#")
                reasons.append(("exact-scope", query_value, matched_value))
                break
            if path_matches and symbol_matches:
                hierarchical_scope_match = True
                score += 20.0
                precedence = max(precedence, 5)
                query_value = f"{repository}:{path}#{symbol}".rstrip("#")
                matched_value = f"{candidate_repository}:{candidate_path}#{candidate_symbol}".rstrip("#")
                reasons.append(("scope-hierarchy", query_value, matched_value))
                break
    # The implicit acceptance category is useful for gap analysis, but must not
    # make every acceptance card relevant to every task.
    hints = inferred_categories(query_text, include_default_acceptance=False)
    if document.category in hints:
        score += 8.0
    if document.pinned:
        score += 2.5
    if document.source_type == "canonical-page":
        score += 1.5
    if document.source_type == "legacy-page":
        score -= 0.5
    if document.source_type == "task-note":
        score -= 1.0
    if document.status in {"deprecated", "superseded"}:
        score -= 5.0
    if title_overlap:
        precedence = max(precedence, 3)
        reasons.append(("title-text", " ".join(sorted(title_overlap)), document.title))
    if tag_overlap:
        precedence = max(precedence, 3)
        reasons.append(("tag", " ".join(sorted(tag_overlap)), " ".join(document.tags)))
    if symbol_overlap and not exact_symbol_match:
        precedence = max(precedence, 3)
        reasons.append(("symbol-text", " ".join(sorted(symbol_overlap)), " ".join(document.symbols)))
    if meaningful_path_overlap and not (exact_path_match or hierarchical_path_match):
        precedence = max(precedence, 3)
        reasons.append(("path-text", " ".join(sorted(meaningful_path_overlap)), " ".join(document.paths)))
    if len(content_overlap) >= 2:
        precedence = max(precedence, 2)
        reasons.append(("body-text", " ".join(sorted(content_overlap)), ""))
    if document.pinned and precedence == 0:
        precedence = 1
        reasons.append(("pinned", "", ""))
    qualifies = bool(
        document.pinned
        or exact_path_match
        or hierarchical_path_match
        or exact_symbol_match
        or exact_topic_match
        or exact_scope_match
        or hierarchical_scope_match
        or title_overlap
        or tag_overlap
        or symbol_overlap
        or meaningful_path_overlap
        or len(content_overlap) >= 2
    )
    return MatchDetails(
        score=score,
        qualifies=qualifies,
        precedence=precedence,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def score_document(
    document: SearchDocument,
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
    topics: Sequence[str] = (),
    scopes: Sequence[dict[str, str]] = (),
) -> float:
    return score_document_details(document, task, paths, symbols, topics, scopes).score


def selected_brief_payload(
    root: Path,
    config: dict[str, Any],
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
    limit_override: int | None,
    include_history: bool,
    topics: Sequence[str] = (),
    scopes: Sequence[dict[str, str]] = (),
    include_legacy: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    documents, warnings = collect_search_documents(root, config, include_history, include_legacy)
    brief_config = config.get("brief") if isinstance(config.get("brief"), dict) else {}
    max_items = limit_override or safe_int(brief_config.get("max_items"), 18, minimum=1, maximum=100)
    per_category = safe_int(brief_config.get("max_items_per_category"), 3, minimum=1, maximum=20)
    summary_limit = safe_int(brief_config.get("max_summaries"), 3, minimum=1, maximum=11)
    related_limit = safe_int(brief_config.get("max_related_tasks"), 3, minimum=1, maximum=20)
    excerpt_limit = safe_int(brief_config.get("max_excerpt_chars"), 700, minimum=120, maximum=5000)
    recent_decisions = safe_int(brief_config.get("include_recent_decisions"), 2, minimum=1, maximum=10)

    overview = [document for document in documents if document.source_type == "project-overview"]
    primary_docs = [
        document
        for document in documents
        if document.source_type == "knowledge-card"
    ]
    summary_docs = [document for document in documents if document.source_type == "canonical-page"]
    legacy_docs = [document for document in documents if document.source_type == "legacy-page"]
    task_docs = [document for document in documents if document.source_type == "task-note"]
    scored = []
    primary_matches: dict[str, MatchDetails] = {}
    for document in primary_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        primary_matches[document.source_path] = match
        if match.qualifies:
            scored.append((match, document))
    scored.sort(
        key=lambda pair: (
            pair[0].precedence,
            pair[0].score,
            pair[1].pinned,
            pair[1].updated_at or pair[1].created_at,
            pair[1].identifier or pair[1].source_path,
        ),
        reverse=True,
    )

    summary_scored: list[tuple[MatchDetails, SearchDocument]] = []
    for document in summary_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        if match.qualifies:
            summary_scored.append((match, document))
    summary_scored.sort(
        key=lambda pair: (pair[0].precedence, pair[0].score, pair[1].category or ""),
        reverse=True,
    )
    selected_summaries = summary_scored[:summary_limit]

    selected: list[tuple[MatchDetails, SearchDocument]] = []
    per_category_counts: dict[str, int] = {}
    selected_paths: set[str] = set()
    for match, document in [pair for pair in scored if pair[1].status in {"current", "proposed"}]:
        category = document.category or "uncategorized"
        if per_category_counts.get(category, 0) >= per_category:
            continue
        selected.append((match, document))
        selected_paths.add(document.source_path)
        per_category_counts[category] = per_category_counts.get(category, 0) + 1
        if len(selected) >= max_items:
            break

    # Recent decisions remain useful context, but only after a real relevance
    # signal (or explicit pinning) qualifies them.
    decision_docs = sorted(
        [
            document
            for document in primary_docs
            if document.source_type == "knowledge-card"
            if document.category == "decisions"
            and document.status in {"current", "proposed"}
            and document.source_path not in selected_paths
            and primary_matches[document.source_path].qualifies
        ],
        key=lambda document: document.updated_at or document.created_at,
        reverse=True,
    )
    for document in decision_docs[:recent_decisions]:
        if len(selected) >= max_items:
            break
        selected.append((score_document_details(document, task, paths, symbols, topics, scopes), document))
        selected_paths.add(document.source_path)

    related_candidates: list[tuple[MatchDetails, SearchDocument]] = []
    for document in task_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        if match.qualifies:
            related_candidates.append((match, document))
    related = sorted(
        related_candidates,
        key=lambda pair: (pair[0].precedence, pair[0].score, pair[1].updated_at or pair[1].created_at),
        reverse=True,
    )[:related_limit]

    def is_current_knowledge(document: SearchDocument) -> bool:
        return document.source_type == "knowledge-card" and document.status == "current"

    legacy_selected: list[tuple[MatchDetails, SearchDocument]] = []
    if include_legacy:
        legacy_scored = []
        for document in legacy_docs:
            match = score_document_details(document, task, paths, symbols, topics, scopes)
            if match.qualifies:
                legacy_scored.append((match, document))
        legacy_scored.sort(
            key=lambda pair: (pair[0].precedence, pair[0].score, pair[1].updated_at or pair[1].created_at),
            reverse=True,
        )
        legacy_category_counts: dict[str, int] = {}
        for match, document in legacy_scored:
            category = document.category or "uncategorized"
            if legacy_category_counts.get(category, 0) >= per_category:
                continue
            legacy_selected.append((match, document))
            legacy_category_counts[category] = legacy_category_counts.get(category, 0) + 1
            if len(legacy_selected) >= 3:
                break

    coverage: dict[str, dict[str, int]] = {}
    current_docs = [document for document in primary_docs if is_current_knowledge(document)]
    for category in configured_categories(config):
        available = sum(document.category == category for document in current_docs)
        matched = sum(document.category == category and is_current_knowledge(document) for _, document in selected)
        coverage[category] = {"available": available, "matched": matched}

    relevant = inferred_categories(" ".join((task, *paths, *symbols)))
    gaps = [category for category in configured_categories(config) if category in relevant and coverage[category]["matched"] == 0]

    current_cards = [
        document
        for document in primary_docs
        if document.source_type == "knowledge-card" and document.status == "current"
    ]
    title_groups: dict[tuple[str | None, str], list[SearchDocument]] = {}
    for document in current_cards:
        key = (document.category, normalize_space(document.title).lower())
        title_groups.setdefault(key, []).append(document)
    conflicts = [
        {
            "category": category,
            "title": title,
            "sources": [document.source_path for document in group],
        }
        for (category, title), group in title_groups.items()
        if title and len(group) > 1 and len({normalize_space(document.content) for document in group}) > 1
    ]

    def serialize(document: SearchDocument, match: MatchDetails | None = None) -> dict[str, Any]:
        value = {
            "id": document.identifier,
            "type": document.source_type,
            "category": document.category,
            "title": document.title,
            "status": document.status,
            "confidence": document.confidence,
            "source": document.source_path,
            "excerpt": clip(document.content, excerpt_limit),
            "paths": list(document.paths),
            "symbols": list(document.symbols),
            "tags": list(document.tags),
            "topics": list(document.topics),
            "scopes": [
                {"repository": repository, "path": path, "symbol": symbol}
                for repository, path, symbol in document.scopes
            ],
        }
        if document.revision:
            value["revision"] = document.revision
        if document.content_hash:
            value["content_hash"] = document.content_hash
        if match is not None:
            value["score"] = round(match.score, 3)
            value["match_precedence"] = match.precedence
            value["match_reasons"] = [
                {"kind": kind, "query": query, "matched": matched}
                for kind, query, matched in match.reasons
            ]
        return value

    current_selected = [(score, document) for score, document in selected if document.status == "current"]
    proposed_selected = [(score, document) for score, document in selected if document.status == "proposed"]
    history_selected = [
        (match, document) for match, document in scored
        if include_history and document.status in {"deprecated", "superseded"}
    ][:max_items]
    displayed_cards = [
        {
            "id": document.identifier,
            "revision": document.revision,
            "status": document.status,
            "source": document.source_path,
            "content_hash": document.content_hash,
        }
        for _, document in [*current_selected, *proposed_selected, *history_selected]
        if document.identifier
    ]
    generated_at = now_iso()
    receipt_core = {
        "task": task,
        "paths": list(paths),
        "symbols": list(symbols),
        "topics": list(topics),
        "scopes": list(scopes),
        "include_history": include_history,
        "knowledge_state": knowledge_state_fingerprint(root, config),
        "generated_at": generated_at,
        "displayed_cards": displayed_cards,
    }
    return {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "task": task,
        "paths": list(paths),
        "symbols": list(symbols),
        "topics": list(topics),
        "scopes": list(scopes),
        "generated_at": generated_at,
        "receipt": {
            "kind": "brief-display",
            "claim": "displayed-only",
            "receipt_id": sha256_text(stable_json(receipt_core)),
            **receipt_core,
        },
        "project_overview": [serialize(document) for document in overview],
        "category_summaries": [serialize(document, match) for match, document in selected_summaries],
        "knowledge": [serialize(document, match) for match, document in current_selected],
        "proposed_knowledge": [serialize(document, match) for match, document in proposed_selected],
        "history": [serialize(document, match) for match, document in history_selected],
        "legacy_clues": [serialize(document, match) for match, document in legacy_selected],
        "related_tasks": [serialize(document, match) for match, document in related],
        "coverage": coverage,
        "gaps": gaps,
        "conflicts": conflicts,
        "warnings": warnings,
        "read_only": True,
    }


def attach_brief_topic_resolution(payload: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    """Attach optional-topic diagnostics while preserving a receipt for the actual query."""
    payload["requested_topics"] = list(resolution.get("requested") or [])
    payload["ignored_topics"] = list(resolution.get("unknown") or [])
    payload["topic_resolution"] = resolution
    payload["warnings"] = [
        *(warning.get("detail") or str(warning) for warning in resolution.get("warnings") or []),
        *(payload.get("warnings") or []),
    ]
    receipt = payload.get("receipt")
    if isinstance(receipt, dict):
        receipt["requested_topics"] = list(resolution.get("requested") or [])
        receipt["ignored_topics"] = list(resolution.get("unknown") or [])
        receipt_core = {
            key: value
            for key, value in receipt.items()
            if key not in {"kind", "claim", "receipt_id"}
        }
        receipt["receipt_id"] = sha256_text(stable_json(receipt_core))
    return payload


def render_brief_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CodeStable 项目知识简报",
        "",
        f"**任务**：{payload['task']}",
    ]
    if payload["paths"]:
        lines.append(f"**已知路径**：{', '.join(payload['paths'])}")
    if payload["symbols"]:
        lines.append(f"**已知符号**：{', '.join(payload['symbols'])}")
    if payload["topics"]:
        lines.append(f"**业务主题**：{', '.join(payload['topics'])}")
    if payload.get("ignored_topics"):
        lines.append(f"**已忽略的未知主题**：{', '.join(payload['ignored_topics'])}")
    if payload["scopes"]:
        lines.append(f"**结构化范围**：{json.dumps(payload['scopes'], ensure_ascii=False)}")
    topic_warnings = (payload.get("topic_resolution") or {}).get("warnings") or []
    if topic_warnings:
        lines.extend(("", "## 主题提示", ""))
        for warning in topic_warnings:
            suggestions = warning.get("suggestions") or []
            suffix = ""
            if suggestions:
                suffix = "；近似主题：" + "、".join(f"`{item['name']}`" for item in suggestions)
            lines.append(f"- `{warning['topic']}` 不存在，已忽略并继续检索{suffix}。")
        lines.append("- 不确定主题名时请省略 `--topic`，或先运行 `topics list`。")
    lines.extend(
        (
            "",
            "> 这些内容用于知识导航。accepted 目标与 verified 行为承担不同作用；冲突必须沿 scope、证据和来源查明，不能机械选择 Wiki 或代码一方。",
            "",
        )
    )

    if payload["project_overview"]:
        lines.extend(("## 项目总览", ""))
        for item in payload["project_overview"]:
            lines.append(item["excerpt"])
            lines.append(f"\n来源：`{item['source']}`\n")

    if payload.get("category_summaries"):
        lines.extend(("## 相关分类摘要（不占卡片配额）", ""))
        for item in payload["category_summaries"]:
            reasons = ", ".join(reason["kind"] for reason in item.get("match_reasons", [])) or "summary"
            lines.append(f"- **{item['title']}**：{item['excerpt']}（匹配：`{reasons}`；来源 `{item['source']}`）")
        lines.append("")

    lines.extend(("## 相关知识", ""))
    if not payload["knowledge"]:
        lines.append("未检索到匹配的 current Wiki 知识。")
        if not payload["legacy_clues"]:
            lines.append("Agent 应从用户要求、公共契约、测试和源码建立事实，并在任务结束后沉淀可复用结论。")
        lines.append("")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in payload["knowledge"]:
        grouped.setdefault(item.get("category") or "uncategorized", []).append(item)
    for category in configured_categories({"wiki": {"categories": list(CATEGORY_DEFS)}}):
        if category not in grouped:
            continue
        lines.extend((f"### {CATEGORY_DEFS[category]['label']}", ""))
        for item in grouped[category]:
            identifier = f" · `{item['id']}`" if item.get("id") else ""
            lines.append(f"#### {item['title']}{identifier}")
            lines.append("")
            lines.append(item["excerpt"])
            lines.append("")
            metadata = [item["type"], item["status"], item["confidence"], f"source `{item['source']}`"]
            if item["paths"]:
                metadata.append("paths " + ", ".join(f"`{path}`" for path in item["paths"]))
            if item["symbols"]:
                metadata.append("symbols " + ", ".join(f"`{symbol}`" for symbol in item["symbols"]))
            if item.get("match_reasons"):
                metadata.append("matches " + ", ".join(reason["kind"] for reason in item["match_reasons"]))
            lines.append("- " + " · ".join(metadata))
            lines.append("")
    if "uncategorized" in grouped:
        lines.extend(("### 其他来源", ""))
        for item in grouped["uncategorized"]:
            lines.append(f"- **{item['title']}**：{item['excerpt']}（`{item['source']}`）")
        lines.append("")

    if payload["proposed_knowledge"]:
        lines.extend(("## 相关提议（不能视为当前约束）", ""))
        for item in payload["proposed_knowledge"]:
            lines.append(f"- **{item['title']}** · `{item['id']}` · {item['excerpt']} · 来源 `{item['source']}`")
        lines.append("")

    if payload["history"]:
        lines.extend(("## 显式历史结果", ""))
        lines.append("以下内容仅因本次启用了历史检索而返回，不属于当前知识。")
        lines.append("")
        for item in payload["history"]:
            lines.append(f"- **{item['title']}** · `{item['id']}` · {item['status']} · 来源 `{item['source']}`")
        lines.append("")

    if payload["legacy_clues"]:
        lines.extend(("## Legacy 线索（需核验）", ""))
        lines.append("以下旧页只因显式启用旧资料检索而返回；它们只用于迁移或历史调查，不代表当前事实，也不计入知识覆盖。")
        lines.append("")
        for item in payload["legacy_clues"]:
            category = CATEGORY_DEFS.get(item.get("category") or "", {}).get("label", "其他")
            lines.append(f"### {item['title']}")
            lines.append("")
            lines.append(item["excerpt"])
            lines.append("")
            lines.append(
                f"- {category} · legacy clue · source `{item['source']}`"
            )
            lines.append("")

    lines.extend(("## 相关历史任务", ""))
    if not payload["related_tasks"]:
        lines.append("- 无匹配记录。")
    else:
        for item in payload["related_tasks"]:
            identifier = f" `{item['id']}`" if item.get("id") else ""
            lines.append(f"- **{item['title']}**{identifier} · {item['status']}")
            lines.append(f"  - {item['excerpt']}")
            lines.append(f"  - 来源：`{item['source']}`")
    lines.append("")

    lines.extend(("## 覆盖与空白", ""))
    lines.append("| 分类 | 已有当前知识 | 本次匹配 |")
    lines.append("|---|---:|---:|")
    for category, counts in payload["coverage"].items():
        lines.append(f"| {CATEGORY_DEFS[category]['label']} | {counts['available']} | {counts['matched']} |")
    lines.append("")
    if payload["gaps"]:
        lines.append("本任务可能相关但尚无匹配知识：" + "、".join(CATEGORY_DEFS[item]["label"] for item in payload["gaps"]) + "。")
    else:
        lines.append("未发现由任务文本直接触发的知识空白。")
    if payload["conflicts"]:
        lines.append("")
        lines.append("检测到可能冲突的当前卡片：")
        for conflict in payload["conflicts"]:
            label = CATEGORY_DEFS.get(conflict["category"] or "", {}).get("label", conflict["category"] or "其他")
            lines.append(f"- {label} / {conflict['title']}：{', '.join(f'`{source}`' for source in conflict['sources'])}")
    if payload["warnings"]:
        lines.append("")
        lines.append("读取警告：")
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    receipt = payload.get("receipt") or {}
    if receipt:
        lines.extend(
            (
                "",
                "## 只读回执",
                "",
                f"- 回执：`{receipt.get('receipt_id', '')}`",
                "- 声明：只证明这些卡片在本次查询中被展示，不证明它们影响了设计、实现、测试或评审。",
            )
        )
    lines.extend(("", f"_只读生成于 {payload['generated_at']}_", ""))
    return "\n".join(lines)
