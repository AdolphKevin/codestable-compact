"""Read-only evidence bindings and human-summary dependencies."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def normalize_card_dependencies(value: Any) -> list[str]:
    if value is not None and (not isinstance(value, list) or any(
        not isinstance(item, str) or not re.fullmatch(r"K-[A-Za-z0-9-]+", item) for item in value
    )):
        raise KnowledgeError("depends_on must be an array of K-* card identifiers")
    return unique_strings(value)


def normalize_evidence_reference(value: Any, snapshot: bool = False) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - {"repository", "path", "sha256", "revision"}:
        raise KnowledgeError("evidence references accept repository, path, sha256, and revision")
    scope = normalize_scopes([{key: value[key] for key in ("repository", "path") if key in value}])[0]
    if not scope["path"] or scope["path"] == ".":
        raise KnowledgeError("evidence reference requires a repository-relative file path")
    result = {"repository": scope["repository"], "path": scope["path"]}
    digest = normalize_space(value.get("sha256")).lower()
    if digest or snapshot:
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise KnowledgeError("source snapshots require a SHA-256 content fingerprint")
        result["sha256"] = digest
    if value.get("revision"):
        result["revision"] = normalize_space(value["revision"])
    return result


def evidence_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def normalize_evidence_binding(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if raw.get("verified_at"):
        if evidence_time(raw["verified_at"]) is None:
            raise KnowledgeError("verified_at requires an ISO-8601 time with timezone")
        result["verified_at"] = normalize_space(raw["verified_at"])
    if raw.get("source_snapshots") is not None:
        if not isinstance(raw["source_snapshots"], list):
            raise KnowledgeError("source_snapshots must be an array")
        snapshots = [normalize_evidence_reference(value, snapshot=True) for value in raw["source_snapshots"]]
        if len({(value["repository"], value["path"]) for value in snapshots}) != len(snapshots):
            raise KnowledgeError("source_snapshots must not repeat a repository/path")
        if snapshots:
            result["source_snapshots"] = snapshots
    if raw.get("case_ids") is not None:
        if not isinstance(raw["case_ids"], list) or any(not isinstance(value, str) for value in raw["case_ids"]):
            raise KnowledgeError("case_ids must be an array of test identifiers")
        if unique_strings(raw["case_ids"]):
            result["case_ids"] = unique_strings(raw["case_ids"])
    if raw.get("run_record"):
        record = raw["run_record"]
        if isinstance(record, str) and re.match(r"https?://", record):
            result["run_record"] = record
        else:
            result["run_record"] = normalize_evidence_reference(record)
    return result


class EvidenceReader:
    """Cache reads for one operation; never fetch URLs or mix external worktrees into Git views."""
    def __init__(self, root: Path, config: dict[str, Any]):
        self.root = root
        self.repositories = configured_repositories(root, config)
        self.cache: dict[str, tuple[bytes | None, str]] = {}

    def read(self, reference: Any) -> tuple[bytes | None, str]:
        key = stable_json(reference)
        if key in self.cache:
            return self.cache[key]
        try:
            ref = normalize_evidence_reference(reference)
            repository = ref["repository"]
            if repository not in self.repositories:
                result = (None, "repository-unavailable")
            elif READ_VIEW.get() is not None and repository != "self":
                # A verification commit is not the consuming commit's external version.
                result = (None, "external-snapshot-unavailable")
            else:
                root = self.repositories[repository]
                path = root / ref["path"]
                if READ_VIEW.get() is None and not path.resolve().is_relative_to(root):
                    result = (None, "reference-outside-repository")
                elif not source_is_dir(root):
                    result = (None, "repository-unavailable")
                elif not source_is_file(path):
                    result = (None, "file-missing")
                elif source_size(path) > 16 * 1024 * 1024:
                    result = (None, "file-too-large")
                else:
                    result = (source_bytes(path), "read")
        except (KnowledgeError, OSError, ValueError):
            result = (None, "reference-unavailable")
        self.cache[key] = result
        return result

    def fingerprint(self) -> str:
        return sha256_text(stable_json([
            {"reference": key, "state": state, "sha256": sha256_bytes(data) if data is not None else None}
            for key, (data, state) in sorted(self.cache.items())
        ]))


def evidence_input_state(cards: dict[str, Any], items: Sequence[dict[str, Any]], reader: EvidenceReader) -> str:
    records = [metadata for _, metadata, _ in cards.values() if metadata.get("status") == "current"] + list(items)
    for record in records:
        evidence = record.get("evidence")
        for value in evidence if isinstance(evidence, list) else []:
            if not isinstance(value, dict):
                continue
            snapshots = value.get("source_snapshots")
            for reference in snapshots if isinstance(snapshots, list) else []:
                reader.read(reference)
            if value.get("run_record"):
                reader.read(value["run_record"])
    return reader.fingerprint()


def validity_status(values: Sequence[str]) -> str:
    if "needs-review" in values:
        return "needs-review"
    if "unverifiable" in values or not values:
        return "unverifiable"
    return "current" if "current" in values else "not-applicable"


def evidence_validity(root: Path, config: dict[str, Any], evidence: Any,
                      reader: EvidenceReader | None = None) -> dict[str, Any]:
    reader = reader or EvidenceReader(root, config)
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(evidence if isinstance(evidence, list) else []):
        result: dict[str, Any] = {"index": index, "status": "current", "reasons": [], "sources": []}
        def problem(code: str, changed: bool = False) -> None:
            result["reasons"].append(code)
            result["status"] = validity_status([result["status"], "needs-review" if changed else "unverifiable"])
        if not isinstance(raw, dict):
            problem("evidence-unstructured")
            results.append(result)
            continue
        result["kind"] = raw.get("kind")
        if raw.get("kind") == "accepted-decision" and not raw.get("source_snapshots"):
            result.update(status="not-applicable", reasons=["accepted-authority-is-not-a-behavior-test"])
            results.append(result)
            continue
        try:
            binding = normalize_evidence_binding(raw)
        except KnowledgeError:
            problem("evidence-binding-invalid")
            results.append(result)
            continue
        verified = evidence_time(binding.get("verified_at"))
        if verified is None or verified > now_local():
            problem("verification-time-missing-or-invalid")
        result["verified_at"] = binding.get("verified_at")
        snapshots = binding.get("source_snapshots") or []
        if not snapshots:
            problem("source-snapshots-missing")
        for reference in snapshots:
            data, state = reader.read(reference)
            observed = sha256_bytes(data) if data is not None else None
            result["sources"].append({**reference, "observed_sha256": observed, "read_status": state})
            if data is None:
                problem(state, changed=state == "file-missing")
            elif observed != reference["sha256"]:
                problem("source-content-changed", changed=True)
        if raw.get("kind") == "test":
            record_ref = binding.get("run_record")
            cases = binding.get("case_ids") or []
            result["case_ids"] = cases
            result["run_record"] = record_ref
            if not record_ref or not cases:
                problem("test-run-or-cases-missing")
            else:
                data, state = reader.read(record_ref)
                if data is None:
                    problem("test-run-" + state)
                else:
                    result["run_sha256"] = sha256_bytes(data)
                    if isinstance(record_ref, dict) and record_ref.get("sha256") and record_ref["sha256"] != result["run_sha256"]:
                        problem("test-run-content-changed", changed=True)
                    try:
                        record = json.loads(data)
                        if not isinstance(record, dict):
                            raise ValueError("not an object")
                        record_sources = record.get("sources")
                        if not isinstance(record_sources, list) or not record_sources:
                            raise ValueError("no source bindings")
                        normalized_sources = [normalize_evidence_reference(value, snapshot=True) for value in record_sources]
                        # Both sets must bind exactly the same declared files and versions.
                        if sorted(map(stable_json, snapshots)) != sorted(map(stable_json, normalized_sources)):
                            problem("test-run-source-bindings-differ")
                        if verified is None or evidence_time(record.get("verified_at")) != verified:
                            problem("test-run-time-differs")
                        records = record.get("cases")
                        if not isinstance(records, list) or any(not isinstance(value, dict) for value in records):
                            raise ValueError("invalid cases")
                        ids = [value.get("id") for value in records]
                        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
                            raise ValueError("ambiguous cases")
                        outcomes = {value["id"]: value.get("result") for value in records}
                        for case in cases:
                            if case not in outcomes:
                                problem("test-case-not-recorded")
                            elif outcomes[case] != "passed":
                                problem("test-case-not-passed", changed=outcomes[case] in {"failed", "skipped"})
                    except (ValueError, TypeError, KnowledgeError, UnicodeDecodeError):
                        problem("test-run-summary-invalid")
        result["reasons"] = unique_strings(result["reasons"])
        results.append(result)
    return {"status": validity_status([value["status"] for value in results]), "evidence": results,
            "claim": "declared-source-bindings-only; business truth is not evaluated"}


def review_finding(target: str, path: str, issue: str, reason: str, sources: Sequence[str], action: str) -> dict[str, Any]:
    return {"target": target, "path": path, "issue_type": issue, "reason": reason,
            "sources": sorted(set(sources)), "suggested_action": action}


def knowledge_review(root: Path, config: dict[str, Any], cards: dict[str, Any] | None = None,
                     reader: EvidenceReader | None = None) -> dict[str, Any]:
    """Derive review state from source records, including an in-memory learn projection."""
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    if cards is None:
        cards, _ = scan_existing_records(wiki, configured_categories(config))
    reader = reader or EvidenceReader(root, config)
    current = {key: record for key, record in cards.items() if record[1].get("status") == "current"}
    card_reports: dict[str, Any] = {}
    queue: list[dict[str, Any]] = []
    for identifier, (path, metadata, _) in sorted(current.items()):
        report = evidence_validity(root, config, metadata.get("evidence"), reader)
        card_reports[identifier] = report
        if report["status"] not in {"current", "not-applicable"}:
            reasons = sorted({reason for value in report["evidence"] for reason in value["reasons"]})
            queue.append(review_finding(identifier, path.relative_to(root).as_posix(), "evidence-" + report["status"],
                ", ".join(reasons) or "evidence-missing", [
                    f"{source['repository']}:{source['path']}" for value in report["evidence"] for source in value["sources"]
                ], "对照已声明源码版本和实际运行记录复核证据；不要补写未执行的验证。"))
        for dependency in unique_strings(metadata.get("depends_on")):
            if dependency not in current:
                queue.append(review_finding(identifier, path.relative_to(root).as_posix(), "dependency-not-current",
                    "依赖的知识不存在或已不再是当前结论。", [dependency], "复核取代关系并显式更新依赖。"))

    summaries: dict[str, Any] = {}
    categories = configured_categories(config)
    policy = topic_governance(config)
    themed = sum(bool(metadata.get("topics")) for _, metadata, _ in current.values())
    topic_view_healthy = bool(configured_topics(config)) and policy["mode"] in {"manual", "required"} and (
        policy["mode"] == "manual" or themed / max(1, len(current)) >= policy["minimum_coverage"])
    pages = [(wiki / category / "README.md", category) for category in categories] + [(wiki / "PROJECT.md", None)]
    for path, category in pages:
        text = safe_read_text(path)
        content = extract_canonical(text)
        category_cards = [metadata for _, metadata, _ in current.values() if metadata.get("category") == category]
        empty_summary_required = bool(category and category_cards) and not (
            topic_view_healthy and all(metadata.get("topics") for metadata in category_cards))
        if not content and not empty_summary_required:
            continue
        relative = path.relative_to(root).as_posix()
        marker = summary_review_metadata(text)
        default_sources = ["category:" + category] if category else ["category:" + value for value in categories]
        sources = marker.get("sources", default_sources)
        invalid_sources = not isinstance(sources, list) or not sources or any(not isinstance(value, str) for value in sources)
        if invalid_sources:
            sources = default_sources
        material: list[dict[str, Any]] = []
        source_ids: set[str] = set()
        source_states: list[str] = []
        unresolved: list[str] = []
        def include_card(identifier: str) -> None:
            pending = [identifier]
            while pending:
                target = pending.pop()
                if target in source_ids:
                    continue
                source_ids.add(target)
                if target not in current:
                    unresolved.append(target)
                    material.append({"id": target, "status": "not-current"})
                    continue
                _, metadata, body = current[target]
                report = card_reports[target]
                material.append({"id": target, "record_hash": sha256_text(render_front_matter(metadata, body)),
                                 "evidence_validity": report})
                source_states.append(report["status"])
                pending.extend(reversed(sorted(unique_strings(metadata.get("depends_on")))))
        for source in sorted(set(sources)):
            if source.startswith("category:") and source[9:] in categories:
                name = source[9:]
                members = sorted(identifier for identifier, (_, metadata, _) in current.items() if metadata.get("category") == name)
                material.append({"category": name, "members": members})
                for identifier in members:
                    include_card(identifier)
                if category is None:
                    child_path = (wiki / name / "README.md").relative_to(root).as_posix()
                    child = summaries.get(child_path)
                    material.append({"summary": child_path, "record_hash": sha256_text(safe_read_text(root / child_path)),
                                     "knowledge_hash": child.get("expected_knowledge_hash") if child else None})
                    if child:
                        source_states.append(child["status"])
            elif source.startswith("K-"):
                include_card(source)
            else:
                unresolved.append(source)
        expected_hash = sha256_text(stable_json(material))
        summary_hash = sha256_text(content)
        reasons: list[str] = []
        if not content:
            reasons.append("summary-empty")
        if invalid_sources:
            reasons.append("summary-sources-invalid")
        if not marker.get("knowledge_hash") or not marker.get("summary_hash"):
            reasons.append("summary-review-missing")
        elif marker["knowledge_hash"] != expected_hash or marker["summary_hash"] != summary_hash:
            reasons.append("summary-content-or-sources-changed")
        reviewed = evidence_time(marker.get("reviewed_at"))
        if reviewed is None or reviewed > now_local():
            reasons.append("summary-review-time-missing-or-invalid")
        elif (now_local() - reviewed).days > topic_governance(config)["review_max_age_days"]:
            reasons.append("summary-review-old")
        if unresolved:
            reasons.append("summary-source-unavailable")
        if any(state not in {"current", "not-applicable"} for state in source_states):
            reasons.append("summary-source-needs-review")
        status = "needs-review" if reasons else "current"
        report = {"status": status, "sources": sources, "source_card_ids": sorted(source_ids), "reasons": reasons,
                  "expected_knowledge_hash": expected_hash, "expected_summary_hash": summary_hash}
        summaries[relative] = report
        if reasons:
            queue.append(review_finding(relative, relative, "summary-needs-review", ", ".join(reasons),
                [*sources, *sorted(source_ids), *unresolved], "对照来源复核正文，再更新来源指纹、正文指纹和实际复核时间。"))
    return {"cards": card_reports, "summaries": summaries, "review_queue": queue,
            "evidence_state": reader.fingerprint()}


def review_reason_text(reason: str) -> str:
    labels = {
        "evidence-missing": "未提供证据", "evidence-unstructured": "证据没有结构化记录",
        "evidence-binding-invalid": "证据关联格式不完整", "source-snapshots-missing": "缺少验证时的源码指纹",
        "verification-time-missing-or-invalid": "验证时间缺失或无效", "source-content-changed": "关联文件内容已变化",
        "repository-unavailable": "关联仓库不可访问", "external-snapshot-unavailable": "缺少对应版本的外部仓库内容",
        "file-unavailable": "关联文件不可读取", "file-missing": "关联文件已不存在", "file-too-large": "关联文件超过读取上限",
        "reference-unavailable": "关联记录无法读取", "reference-outside-repository": "关联路径超出仓库范围",
        "test-run-or-cases-missing": "缺少运行记录或具体用例", "test-run-content-changed": "运行记录内容已变化",
        "test-run-source-bindings-differ": "运行记录与声明的源码版本不一致", "test-run-time-differs": "运行时间与声明不一致",
        "test-case-not-recorded": "运行记录未包含指定用例", "test-case-not-passed": "指定用例失败或未通过",
        "test-run-summary-invalid": "运行摘要缺少有效字段", "summary-review-missing": "缺少完整的摘要复核记录",
        "summary-content-or-sources-changed": "摘要正文或来源已变化", "summary-review-old": "摘要已超过配置的复核期限",
        "summary-review-time-missing-or-invalid": "摘要复核时间缺失或无效", "summary-source-unavailable": "摘要来源不存在或已非当前知识",
        "summary-source-needs-review": "摘要引用的知识或分类摘要需要复核", "summary-sources-invalid": "摘要来源声明无效",
        "summary-empty": "已有当前知识但尚未维护分类摘要",
    }
    for key in ("reference-unavailable", "file-unavailable", "file-missing", "file-too-large", "repository-unavailable", "external-snapshot-unavailable", "reference-outside-repository"):
        labels["test-run-" + key] = "运行记录：" + labels[key]
    return "、".join(labels.get(value.strip(), value.strip()) for value in reason.split(","))


def review_notice(report: dict[str, Any]) -> str:
    status = report.get("status")
    label = {"current": "所声明来源与记录一致", "needs-review": "需要复核",
             "unverifiable": "证据不足／无法核实", "not-applicable": "权威决定，不属于行为验证"}.get(status, "尚未检查")
    reasons = report.get("reasons") or sorted({reason for value in report.get("evidence", []) for reason in value["reasons"]})
    detail = review_reason_text(", ".join(reasons)) if reasons else ""
    if status == "current" and report.get("evidence"):
        bindings = []
        for value in report["evidence"]:
            if value.get("verified_at"):
                bindings.append(value["verified_at"])
            bindings.extend(f"{source['repository']}:{source['path']}@{source['sha256'][:12]}" for source in value["sources"])
            bindings.extend(value.get("case_ids") or [])
        values = unique_strings(bindings)
        detail = "；".join(values[:5]) + (f"；另有 {len(values) - 5} 项关联，详见 JSON" if len(values) > 5 else "")
    return label + ("：" + detail if detail and status != "not-applicable" else "")
