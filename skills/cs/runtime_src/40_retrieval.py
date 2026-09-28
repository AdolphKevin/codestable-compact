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




def safe_read_text(path: Path, maximum_bytes: int = 512 * 1024) -> str:
    try:
        if source_size(path) > maximum_bytes:
            return ""
        return source_text(path, encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def card_search_document(
    root: Path, path: Path, metadata: dict[str, Any], body: str, scopes: Sequence[dict[str, str]],
) -> SearchDocument:
    conclusion = extract_section(body, ("结论",)) or body
    return SearchDocument(
        source_type="knowledge-card",
        source_path=path.relative_to(root).as_posix(),
        title=normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
        content=conclusion,
        category=normalize_space(metadata.get("category")) or None,
        identifier=normalize_space(metadata.get("id")) or None,
        status=normalize_space(metadata.get("status") or "current"),
        confidence=normalize_space(metadata.get("confidence") or "accepted"),
        tags=tuple(unique_strings(metadata.get("tags"))),
        topics=tuple(unique_strings(metadata.get("topics"))),
        scopes=tuple(scope_tuple(value) for value in scopes),
        paths=tuple(unique_strings([*unique_strings(metadata.get("paths")), *scope_paths([s for s in scopes if s["repository"] == "self"])])),
        symbols=tuple(unique_strings([*unique_strings(metadata.get("symbols")), *scope_symbols([s for s in scopes if s["repository"] == "self"])])),
        created_at=normalize_space(metadata.get("created_at")),
        updated_at=normalize_space(metadata.get("updated_at")),
        revision=safe_int(metadata.get("revision"), 1, minimum=0),
        content_hash=sha256_text(normalize_space(conclusion)),
        pinned=bool(metadata.get("pinned", False)),
        applies_to=tuple(scope_tuple(value) for value in normalize_scopes(metadata.get("applies_to"))),
        depends_on=tuple(normalize_card_dependencies(metadata.get("depends_on"))),
    )


def collect_search_documents(
    root: Path,
    config: dict[str, Any],
    include_history: bool,
) -> tuple[list[SearchDocument], list[str]]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    categories = configured_categories(config)
    documents: list[SearchDocument] = []
    warnings: list[str] = []

    project_path = wiki / "PROJECT.md"
    if source_is_file(project_path):
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
        if source_is_file(readme):
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
        try:
            documents.append(card_search_document(root, path, metadata, body, scopes))
        except KnowledgeError as exc:
            warnings.append(f"invalid card applicability {path.relative_to(root).as_posix()}: {exc}")

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
                paths=tuple(unique_strings([*unique_strings(metadata.get("paths")), *scope_paths([s for s in task_scopes if s["repository"] == "self"])])),
                symbols=tuple(unique_strings([*unique_strings(metadata.get("symbols")), *scope_symbols([s for s in task_scopes if s["repository"] == "self"])])),
                created_at=normalize_space(metadata.get("created_at")),
                updated_at=normalize_space(metadata.get("updated_at")),
            )
        )

    return documents, warnings


def scope_review_candidates(
    root: Path,
    config: dict[str, Any],
    documents: Sequence[SearchDocument],
    focus_ids: set[str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Surface bounded co-reading candidates, never infer a semantic contradiction."""
    repositories = configured_repositories(root, config)
    buckets: dict[tuple[str, str, str], list[tuple[SearchDocument, str]]] = {}
    for document in sorted(documents, key=lambda item: item.identifier or item.source_path):
        if document.source_type != "knowledge-card" or document.status != "current":
            continue
        scopes = document.scopes or tuple(
            ("self", path, symbol)
            for path in document.paths or ("",)
            for symbol in document.symbols or ("",)
        )
        for repository, path, symbol in sorted(set(scopes)):
            # An unspecific directory or a shared topic is not a concrete rule boundary.
            if path and not symbol:
                repository_root = repositories.get(repository)
                if repository_root is None or not source_is_file(repository_root / path):
                    continue
            if not path and not symbol:
                continue
            key = (repository, "path" if path else "symbol", path or symbol.casefold())
            buckets.setdefault(key, []).append((document, symbol))
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for (repository, kind, value), entries in sorted(buckets.items()):
        for position, (left, left_symbol) in enumerate(entries):
            for right, right_symbol in entries[position + 1:]:
                identifiers = tuple(sorted((left.identifier or left.source_path, right.identifier or right.source_path)))
                if identifiers[0] == identifiers[1] or identifiers in seen:
                    continue
                if focus_ids is not None and not focus_ids.intersection(identifiers):
                    continue
                if left_symbol and right_symbol and left_symbol.casefold() != right_symbol.casefold():
                    continue
                if (left.category, left.title.casefold()) == (right.category, right.title.casefold()):
                    continue  # Existing duplicate-title checks already cover this case.
                if normalize_space(left.content).casefold() == normalize_space(right.content).casefold():
                    continue
                seen.add(identifiers)
                if len(candidates) == limit:
                    return {"items": candidates, "has_more": True, "claim": "scope-overlap-only", "blocking": False}
                candidates.append({
                    "scope": {"repository": repository, "path": value if kind == "path" else "",
                              "symbol": left_symbol or right_symbol},
                    "cards": [
                        {"id": document.identifier, "title": document.title, "category": document.category,
                         "source": document.source_path, "revision": document.revision,
                         "excerpt": clip(document.content, 220)}
                        for document in (left, right)
                    ],
                })
    return {"items": candidates, "has_more": False, "claim": "scope-overlap-only", "blocking": False}


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
    query_text = " ".join((task, *symbols, *topics))
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


def select_shared_constraints(
    documents: Sequence[SearchDocument], direct: list[tuple[MatchDetails, SearchDocument]],
    paths: Sequence[str], symbols: Sequence[str], scopes: Sequence[dict[str, str]],
    total_limit: int, shared_limit: int,
) -> tuple[list[tuple[MatchDetails, SearchDocument]], dict[str, str], dict[str, int]]:
    current = {document.identifier: document for document in documents if document.status == "current" and document.identifier}
    query_scopes = [*path_scopes(paths, symbols), *scopes]
    shared: dict[str, tuple[MatchDetails, SearchDocument]] = {}
    for identifier, document in sorted(current.items()):
        reasons = []
        for repository, path, symbol in document.applies_to:
            for query in query_scopes:
                query_path = query.get("path") or ""
                query_symbols = {query.get("symbol", "").casefold()}
                if query["repository"] == "self":
                    query_symbols.update(value.casefold() for value in symbols)
                path_matches = not path or (bool(query_path) and (path == "." or query_path == path or query_path.startswith(path + "/")))
                if repository == query["repository"] and path_matches and (not symbol or symbol.casefold() in query_symbols):
                    reasons.append(("applies-to", f"{repository}:{query_path}#{query.get('symbol', '')}",
                                    f"{repository}:{path}#{symbol}"))
        if reasons:
            shared[identifier] = (MatchDetails(0, True, 2, tuple(sorted(set(reasons)))), document)
    # Expand this immutable seed set once. Dependencies of an expanded result are not followed.
    seeds = {document.identifier: document for _, document in direct if document.status == "current"}
    seeds.update({identifier: document for identifier, (_, document) in shared.items()})
    for identifier, document in sorted(seeds.items()):
        for target in document.depends_on:
            if target in current and target not in shared:
                shared[target] = (MatchDetails(0, True, 1, (("depends-on", identifier, target),)), current[target])
    direct_ids = {document.identifier for _, document in direct}
    candidates = sorted((pair for identifier, pair in shared.items() if identifier not in direct_ids),
                        key=lambda pair: (-pair[0].precedence, pair[1].identifier or ""))
    count = min(shared_limit, len(candidates), total_limit - (1 if direct and total_limit >= 2 else 0))
    selected_shared = candidates[:count]
    selected_direct = direct[:total_limit - count]
    groups = {document.identifier: "direct" for _, document in selected_direct}
    groups.update({document.identifier: "shared-constraint" for _, document in selected_shared})
    return selected_direct + selected_shared, groups, {
        "direct": len(direct) - len(selected_direct), "shared_constraints": len(candidates) - count,
    }


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
    broad: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    documents, warnings = collect_search_documents(root, config, include_history)
    review_state = knowledge_review(root, config)
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
    task_docs = [document for document in documents if document.source_type == "task-note"]
    focused = bool(paths or symbols or scopes or topics) and not broad

    def relevant(match: MatchDetails, document: SearchDocument) -> bool:
        return match.qualifies and (not focused or match.precedence >= 4 or document.pinned)

    scored = []
    primary_matches: dict[str, MatchDetails] = {}
    for document in primary_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        primary_matches[document.source_path] = match
        if relevant(match, document):
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
    relevant_categories = {document.category for _, document in scored}
    selected_summaries = [pair for pair in summary_scored if not focused or pair[1].category in relevant_categories][:summary_limit]

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
            and relevant(primary_matches[document.source_path], document)
        ],
        key=lambda document: document.updated_at or document.created_at,
        reverse=True,
    )
    for document in decision_docs[:recent_decisions]:
        if len(selected) >= max_items:
            break
        selected.append((score_document_details(document, task, paths, symbols, topics, scopes), document))
        selected_paths.add(document.source_path)

    selected, match_groups, truncation = select_shared_constraints(
        primary_docs, selected, paths, symbols, scopes, max_items,
        safe_int(brief_config.get("max_shared_items"), 5, minimum=1, maximum=100),
    )
    selected_paths = {document.source_path for _, document in selected}
    relevant_categories = {document.category for _, document in selected}
    selected_summaries = [pair for pair in summary_scored if not focused or pair[1].category in relevant_categories][:summary_limit]

    related_candidates: list[tuple[MatchDetails, SearchDocument]] = []
    for document in task_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        if relevant(match, document):
            related_candidates.append((match, document))
    related = sorted(
        related_candidates,
        key=lambda pair: (pair[0].precedence, pair[0].score, pair[1].updated_at or pair[1].created_at),
        reverse=True,
    )[:related_limit]

    def is_current_knowledge(document: SearchDocument) -> bool:
        return document.source_type == "knowledge-card" and document.status == "current"

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
        and any(document.source_path in selected_paths for document in group)
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
        if document.source_type == "knowledge-card":
            value["match_group"] = match_groups.get(document.identifier, "direct")
            value["applies_to"] = [{"repository": repository, "path": path, "symbol": symbol}
                                   for repository, path, symbol in document.applies_to]
            value["depends_on"] = list(document.depends_on)
            value["evidence_validity"] = review_state["cards"].get(document.identifier, {"status": "not-evaluated"})
        if document.source_path in review_state["summaries"]:
            value["review_status"] = review_state["summaries"][document.source_path]
        if match is not None:
            value["score"] = round(match.score, 3)
            value["match_precedence"] = match.precedence
            value["match_reasons"] = [
                {"kind": kind, "query": query, "matched": matched}
                for kind, query, matched in match.reasons
            ]
        return value

    current_selected = [(score, document) for score, document in selected if document.status == "current"]
    reviews = scope_review_candidates(
        root, config, primary_docs,
        {document.identifier for _, document in current_selected if document.identifier},
    )
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
            "match_group": match_groups.get(document.identifier, "direct"),
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
        "review_card_ids": sorted({card["id"] for item in reviews["items"] for card in item["cards"]}),
        "evidence_state": review_state["evidence_state"],
        "validity_hash": sha256_text(stable_json({"cards": review_state["cards"], "summaries": review_state["summaries"]})),
    }
    displayed_targets = {document.identifier for _, document in current_selected}
    displayed_targets.update(document.source_path for document in overview)
    displayed_targets.update(document.source_path for _, document in selected_summaries)
    return {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "task": task,
        "retrieval_mode": "focused" if focused else "broad",
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
        "related_tasks": [serialize(document, match) for match, document in related],
        "coverage": coverage,
        "gaps": gaps,
        "conflicts": conflicts,
        "review_candidates": reviews,
        "review_queue": [value for value in review_state["review_queue"] if value["target"] in displayed_targets],
        "truncation": truncation,
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
            "> 这些内容用于知识导航。作者声明与当前证据有效性分别展示；冲突须对照适用范围、证据和来源复核。",
            "",
        )
    )

    if payload["project_overview"]:
        lines.extend(("## 项目总览", ""))
        for item in payload["project_overview"]:
            lines.append("> " + review_notice(item.get("review_status", {})))
            lines.append("")
            lines.append(item["excerpt"])
            lines.append(f"\n来源：`{item['source']}`\n")

    if payload.get("category_summaries"):
        lines.extend(("## 相关分类摘要（不占卡片配额）", ""))
        for item in payload["category_summaries"]:
            lines.append(f"- **{item['title']}** · {review_notice(item.get('review_status', {}))}：{item['excerpt']}（来源 `{item['source']}`）")
        lines.append("")

    lines.extend(("## 相关知识", ""))
    if not payload["knowledge"]:
        lines.append("未检索到匹配的当前知识。")
        lines.append("Agent 应从用户要求、公共契约、测试和源码建立事实，并在任务结束后沉淀可复用结论。")
        lines.append("")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in payload["knowledge"]:
        grouped.setdefault(item.get("match_group") or "direct", []).append(item)
    for group, label in (("direct", "直接相关知识"), ("shared-constraint", "适用的共享约束")):
        if group not in grouped:
            continue
        lines.extend((f"### {label}", ""))
        for item in grouped[group]:
            identifier = f" · `{item['id']}`" if item.get("id") else ""
            lines.append(f"#### {item['title']}{identifier}")
            lines.append("")
            lines.append("> " + review_notice(item.get("evidence_validity", {})))
            lines.append("")
            lines.append(item["excerpt"])
            lines.append("")
            confidence = {"verified": "作者声明：经过验证", "accepted": "作者声明：已接受", "inferred": "作者声明：推断"}
            metadata = [CATEGORY_DEFS.get(item.get("category"), {}).get("label", "知识"),
                        confidence.get(item["confidence"], "作者声明未说明"), f"来源 `{item['source']}`"]
            if item["paths"]:
                metadata.append("路径 " + ", ".join(f"`{path}`" for path in item["paths"]))
            if item["symbols"]:
                metadata.append("符号 " + ", ".join(f"`{symbol}`" for symbol in item["symbols"]))
            if item.get("match_reasons"):
                metadata.append("命中依据 " + ", ".join(reason["matched"] for reason in item["match_reasons"]
                                                       if reason["kind"] in {"applies-to", "depends-on", "exact-path", "exact-scope"}))
            lines.append("- " + " · ".join(metadata))
            lines.append("")
    truncation = payload.get("truncation", {})
    if any(truncation.values()):
        lines.extend((f"数量限制省略了 {truncation.get('direct', 0)} 条直接结果、{truncation.get('shared_constraints', 0)} 条共享约束；可增加查询上限继续查看。", ""))
    dependency_findings = [value for value in payload.get("review_queue", []) if value["issue_type"] == "dependency-not-current"]
    for finding in dependency_findings:
        lines.extend((f"> 需要复核：`{finding['target']}` 依赖的 {', '.join(finding['sources'])} 已非当前知识。{finding['suggested_action']}", ""))
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
    reviews = payload.get("review_candidates", {})
    if reviews.get("items"):
        lines.extend(("", "## 同范围知识核对", "",
                      "以下卡片声明了同一具体范围，但结论不同；请对照当前需求、实现与测试并读，不代表已经确认冲突。", ""))
        for candidate in reviews["items"]:
            scope = candidate["scope"]
            label = f"{scope['repository']}:{scope['path']}#{scope['symbol']}".rstrip("#")
            links = "；".join(f"[{card['title']}]({card['source']})" for card in candidate["cards"])
            lines.append(f"- {label}：{links}")
        if reviews["has_more"]:
            lines.append("- 还有其他同范围候选；缩小路径或符号范围后继续核对。")
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
