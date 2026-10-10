"""Registered source documents. Bodies are read live, never copied into the wiki."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def configured_documents(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if any(key in (config.get("wiki") or {}) for key in ("documents", "repositories")):
        raise KnowledgeError("inline documents/repositories are unsupported")
    root = getattr(config, "root", None)
    raw = {}
    if root is not None:
        directory = root / ".codestable/documents"
        if READ_VIEW.get() is None and (directory.is_symlink() or not directory.resolve().is_relative_to(root / ".codestable")):
            raise KnowledgeError("document registrations must stay inside .codestable/documents")
        for path in sorted(source_glob(directory, "*.json")):
            if READ_VIEW.get() is None and (not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink()):
                raise KnowledgeError("document registration must be a regular file inside documents")
            if path.stem in raw:
                raise KnowledgeError(f"duplicate document ID: {path.stem}")
            raw[path.stem] = read_json(path)
    result = {}
    seen = set()
    for identifier, value in raw.items():
        if not isinstance(identifier, str) or not REPOSITORY_NAME_PATTERN.fullmatch(identifier):
            raise KnowledgeError("document IDs must use lower-case letters, digits, dots, dashes or underscores")
        allowed = {"repository", "path", "title", "category", "status", "applies_to", "topics", "always"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise KnowledgeError(f"invalid document registration: {identifier}")
        ref = normalize_evidence_reference({key: value[key] for key in ("repository", "path") if key in value})
        if not ref["path"].endswith(".md") or ref["path"].startswith(".codestable/"):
            raise KnowledgeError("registered documents must be Markdown sources outside .codestable")
        key = (ref["repository"], ref["path"])
        if key in seen:
            raise KnowledgeError("register a repository/path only once; use references for sections")
        seen.add(key)
        category = value.get("category", "architecture")
        status = value.get("status", "current")
        if category not in CATEGORY_DEFS or status not in INPUT_CARD_STATUSES:
            raise KnowledgeError(f"invalid document category/status: {identifier}")
        if not isinstance(value.get("always", False), bool):
            raise KnowledgeError("document.always must be boolean")
        result[identifier] = {**ref, "id": identifier, "title": normalize_space(value.get("title")) or identifier,
                              "category": category, "status": status,
                              "applies_to": normalize_scopes(value.get("applies_to")),
                              "topics": normalize_topics(value.get("topics"), config),
                              "always": value.get("always", False)}
    return result


def normalize_document_reference(raw: Any, config: dict[str, Any]) -> dict[str, str]:
    if not isinstance(raw, dict) or set(raw) - {"document", "section", "sha256"}:
        raise KnowledgeError("reference accepts document, section and sha256 only")
    identifier = normalize_space(raw.get("document"))
    if identifier not in configured_documents(config):
        raise KnowledgeError(f"reference document is not registered: {identifier}")
    digest = normalize_space(raw.get("sha256"))
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise KnowledgeError("reference.sha256 must match the document read during review")
    return {"document": identifier, "section": normalize_space(raw.get("section")), "sha256": digest}


def document_section(body: str, section: str) -> str:
    if not section:
        return body
    # Exact visible Markdown heading; ambiguous headings must be disambiguated in the source.
    matches = list(re.finditer(r"^(#{1,6}) +(.+?)\s*#*\s*$", body, re.MULTILINE))
    hits = [i for i, match in enumerate(matches) if match[2].strip() == section]
    if len(hits) != 1:
        raise KnowledgeError(f"document section missing or ambiguous: {section}")
    index = hits[0]
    start = matches[index]
    end = next((m.start() for m in matches[index + 1:] if len(m[1]) <= len(start[1])), len(body))
    return body[start.start():end].strip()


def read_registered_document(root: Path, config: dict[str, Any], identifier: str,
                             section: str = "", reader: EvidenceReader | None = None) -> dict[str, Any]:
    definitions = configured_documents(config)
    if identifier not in definitions:
        raise KnowledgeError(f"unknown document: {identifier}")
    definition = definitions[identifier]
    reader = reader or EvidenceReader(root, config)
    data, state = reader.read({key: definition[key] for key in ("repository", "path")})
    result = {**definition, "source": f"{definition['repository']}:{definition['path']}",
              "sha256": sha256_bytes(data) if data is not None else None,
              "read_status": state, "section": section, "body": "", "read_only": True}
    if data is not None:
        try:
            if len(data) > 512 * 1024:
                result["read_status"] = "file-too-large"
            else:
                result["body"] = document_section(data.decode("utf-8"), section)
        except UnicodeDecodeError:
            result["read_status"] = "invalid-utf8"
        except KnowledgeError:
            result["read_status"] = "section-missing-or-ambiguous"
    result["ok"] = result["read_status"] == "read"
    return result



def document_reference_validity(root: Path, config: dict[str, Any], metadata: dict[str, Any],
                                reader: EvidenceReader) -> dict[str, Any]:
    reasons = []
    sources = []
    try:
        ref = normalize_document_reference(metadata["reference"], config)
        doc = read_registered_document(root, config, ref["document"], ref["section"], reader)
        if not doc["ok"]:
            reasons.append(doc["read_status"])
        if ref["sha256"] != doc["sha256"]:
            reasons.append("document-changed")
        if metadata.get("status") != doc["status"]:
            reasons.append("document-status-changed")
        sources.append({"repository": doc["repository"], "path": doc["path"], "sha256": ref["sha256"],
                        "observed_sha256": doc["sha256"]})
    except KnowledgeError:
        reasons.append("reference-invalid")
    status = "needs-review" if reasons else "current"
    return {"status": status, "evidence": [{"status": status, "reasons": reasons, "sources": sources}],
            "claim": "reference-matches-source-only; source authority and business truth require review"}


def document_inventory(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    reader = EvidenceReader(root, config)
    locations = [(reader.repositories.get(doc["repository"], Path("/__unavailable__")) / doc["path"]).resolve()
                 for doc in configured_documents(config).values()]
    if len(set(locations)) != len(locations):
        raise KnowledgeError("document repository aliases resolve to a duplicate source")
    documents = [read_registered_document(root, config, identifier, reader=reader)
                 for identifier in configured_documents(config)]
    state = [{key: doc[key] for key in ("id", "source", "status", "sha256", "read_status", "applies_to")}
             for doc in documents]
    return {"documents": documents, "state": sha256_text(stable_json(state)), "read_only": True}


def document_reference_findings(root: Path, config: dict[str, Any], inventory: dict[str, Any] | None = None,
                                cards: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    inventory = inventory or document_inventory(root, config)
    docs = {doc["id"]: doc for doc in inventory["documents"]}
    findings = [{"target": doc["id"], "issue_type": doc["read_status"], "source": doc["source"]}
                for doc in docs.values() if not doc["ok"]]
    if cards is None:
        cards, _ = scan_existing_records(wiki_root(root, config), configured_categories(config))
    seen = {}
    for identifier, (_, metadata, _) in cards.items():
        ref = metadata.get("reference")
        if not ref or metadata.get("status") not in {"current", "proposed"}:
            continue
        try:
            ref = normalize_document_reference(ref, config)
        except KnowledgeError as exc:
            findings.append({"target": identifier, "issue_type": "reference-invalid", "detail": str(exc)})
            continue
        doc = docs[ref["document"]]
        reasons = []
        if not doc["ok"]:
            reasons.append(doc["read_status"])
        elif ref["sha256"] != doc["sha256"]:
            reasons.append("document-changed")
        if metadata.get("status") != doc["status"]:
            reasons.append("document-status-changed")
        if doc["ok"]:
            try:
                document_section(doc["body"], ref["section"])
            except KnowledgeError:
                reasons.append("section-missing-or-ambiguous")
        key = (doc["id"], ref["section"])
        if key in seen:
            reasons.append("duplicate-reference")
        seen[key] = identifier
        for reason in reasons:
            findings.append({"target": identifier, "issue_type": reason, "source": doc["source"],
                             "expected_sha256": ref["sha256"], "observed_sha256": doc["sha256"]})
    return findings


def validate_reference_items(root: Path, config: dict[str, Any], items: Sequence[dict[str, Any]],
                             cards: dict[str, Any]) -> None:
    seen = {}
    for identifier, (_, metadata, _) in cards.items():
        if metadata.get("reference") and metadata.get("status") in {"current", "proposed"}:
            ref = metadata["reference"]
            seen[(ref.get("document"), ref.get("section", ""))] = identifier
    source_bodies = [normalize_space(doc["body"]) for doc in document_inventory(root, config)["documents"] if doc["ok"]]
    for item in items:
        if not item.get("reference") and item["status"] == "current":
            conclusion = normalize_space(item["knowledge"])
            if len(conclusion) >= 24 and any(conclusion in body for body in source_bodies):
                raise KnowledgeError("conclusion already exists in a registered source; use a reference instead of copying it")
        ref = item.get("reference")
        if not ref:
            continue
        doc = read_registered_document(root, config, ref["document"], ref["section"])
        if not doc["ok"] or doc["sha256"] != ref["sha256"]:
            raise KnowledgeError("reference source missing or changed; read the document and review again")
        if item["status"] != doc["status"]:
            raise KnowledgeError("reference status must match its registered document")
        key = (ref["document"], ref["section"])
        previous = seen.get(key)
        identical = previous in cards and cards[previous][1].get("fingerprint") == item_fingerprint(item)
        if previous and not identical and previous != item.get("card_id") and previous not in item["supersedes"]:
            raise KnowledgeError(f"duplicate document reference; reuse or update {previous}")
        seen[key] = item.get("card_id") or "another item in this payload"


def authoritative_brief(root: Path, config: dict[str, Any], task: str, paths: Sequence[str],
                        symbols: Sequence[str], topics: Sequence[str], scopes: Sequence[dict[str, str]],
                        broad: bool, excerpt_limit: int) -> dict[str, Any]:
    inventory = document_inventory(root, config)
    cards, _ = scan_existing_records(wiki_root(root, config), configured_categories(config))
    findings = document_reference_findings(root, config, inventory, cards)
    ranked = []
    focused = bool(paths or symbols or topics or scopes) and not broad
    for doc in inventory["documents"]:
        refs = [{"id": identifier, "revision": metadata.get("revision", 1), "category": metadata.get("category"), **metadata["reference"]}
                for identifier, (_, metadata, _) in cards.items() if metadata.get("reference", {}).get("document") == doc["id"]
                and metadata.get("status") in {"current", "proposed"}]
        document = SearchDocument(source_type="authoritative-document", source_path=doc["source"],
                                  title=doc["title"], content=doc["body"], category=doc["category"],
                                  topics=tuple(doc["topics"]), pinned=doc["always"],
                                  scopes=tuple(scope_tuple(s) for s in [{"repository": doc["repository"], "path": doc["path"], "symbol": ""}, *doc["applies_to"]]),
                                  paths=(doc["path"],) if doc["repository"] == "self" else ())
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        scope_hit = any((s["path"] == "." or scope_path_match(q.get("path", ""), s["path"]))
                        and (not s["symbol"] or q.get("symbol", "") == s["symbol"])
                        and q.get("repository", "self") == s["repository"]
                        for s in doc["applies_to"] for q in [*scopes, *({"path": p, "repository": "self"} for p in paths)])
        if not (doc["always"] or scope_hit or match.qualifies and (not focused or match.precedence >= 4)):
            continue
        # Select the most relevant heading block without pretending an excerpt is the full document.
        blocks = re.split(r"(?=^#{1,6} )", doc["body"], flags=re.MULTILINE)
        # A document title alone is navigation, not a useful source excerpt.
        blocks = [b for b in blocks if any(line.strip() and not line.startswith("#") for line in b.splitlines())] or [doc["body"]]
        query = lexical_tokens(task + " " + " ".join(symbols))
        block = max(blocks, key=lambda b: len(lexical_tokens(b) & query), default=doc["body"])
        excerpt = clip(block, excerpt_limit)
        item = {key: value for key, value in doc.items() if key != "body"}
        item.update(excerpt=excerpt, truncated=excerpt != doc["body"], references=refs,
                    match_reasons=[{"kind": k, "query": q, "matched": m} for k, q, m in match.reasons], read_command=["documents", "read", "--id", doc["id"]])
        ranked.append((doc["always"], scope_hit, match.precedence, match.score, doc["id"], item))
    ranked.sort(key=lambda row: row[:-1], reverse=True)
    limit = safe_int((config.get("brief") or {}).get("max_documents"), 12, minimum=1, maximum=100)
    return {"documents": [row[-1] for row in ranked[:limit]], "matched_documents": [row[-1] for row in ranked], "state": inventory["state"],
            "review_queue": findings, "omitted": max(0, len(ranked) - limit),
            "claim": "source-documents-and-experience-share-one-entry; order-is-not-authority"}
