"""CodeStable runtime section: 70 cli."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
def template_payload(title: str, kind: str) -> dict[str, Any]:
    return {
        "task": {
            "title": title or "__REPLACE__: 任务标题",
            "kind": kind or "task",
            "status": "completed",
            "request": "__REPLACE__: 用户最初要求",
            "summary": "__REPLACE__: 实际做了什么；不要写计划或完整日志",
            "result": "__REPLACE__: 最终可观察结果",
            "scopes": [{"repository": "self", "path": "__REPLACE__/path.py", "symbol": "__REPLACE__"}],
            "topics": [],
            "tags": ["__REPLACE__"],
            "verification": ["__REPLACE__: 实际执行的验证命令或检查"],
            "deliverable": "__REPLACE__: 公开产物路径",
            "knowledge_summary": "__REPLACE__: 说明为何新增、复用、更新或不创建长期卡片",
            "source": {},
            "knowledge_use": [],
        },
        "items": [
            {
                "category": "architecture",
                "title": "__REPLACE__: 一个未来任务会复用的架构结论",
                "knowledge": "__REPLACE__: 用当前时态写清楚稳定事实、约束或边界",
                "rationale": "__REPLACE__: 说明依据和选择理由",
                "implications": ["__REPLACE__: 对未来实现、测试或运维的具体影响"],
                "future_use": [
                    {
                        "change": "__REPLACE__: 会触发复核的变更",
                        "actor": "__REPLACE__: 未来执行者",
                        "constraint": "__REPLACE__: 必须复核的本卡约束",
                    },
                    {
                        "change": "__REPLACE__: 另一类变更",
                        "actor": "__REPLACE__: 另一未来执行者",
                        "constraint": "__REPLACE__: 必须复核的本卡约束",
                    },
                ],
                "scopes": [{"repository": "self", "path": "__REPLACE__/path.py", "symbol": "__REPLACE__"}],
                "topics": [],
                "tags": ["__REPLACE__"],
                "evidence": [
                    {
                        "kind": "test",
                        "artifact": "__REPLACE__: 测试标识",
                        "result": "__REPLACE__: 可核查结果",
                        "supports": "__REPLACE__: 该产物支持的卡片结论",
                    }
                ],
                "confidence": "verified",
                "status": "current",
                "supersedes": [],
                "pinned": False,
            }
        ],
    }


def markdown_bullet_values(value: str) -> list[str]:
    result: list[str] = []
    for line in value.splitlines():
        line = normalize_space(line)
        if line.startswith("- "):
            line = normalize_space(line[2:])
        if line and line not in {"无", "未记录"}:
            result.append(line)
    return unique_strings(result)


def raw_markdown_section(body: str, headings: Sequence[str]) -> str:
    escaped = "|".join(re.escape(value) for value in headings)
    match = re.search(rf"(?ms)^##\s+(?:{escaped})\s*$\n(.*?)(?=^##\s+|\Z)", body)
    return match.group(1).strip() if match else ""


def task_update_template(root: Path, config: dict[str, Any], task_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"T-[A-Za-z0-9-]+", normalize_space(task_id)):
        raise KnowledgeError("template --task-id requires an existing T-* identifier")
    _, tasks = scan_existing_records(wiki_root(root, config), configured_categories(config))
    record = tasks.get(task_id)
    if record is None:
        raise KnowledgeError(f"template --task-id references unknown task {task_id}")
    _, metadata, body = record
    if normalize_space(metadata.get("visibility") or "active") == "archived":
        raise KnowledgeError(
            f"task {task_id} is archived into {normalize_space(metadata.get('consolidated_into'))}; "
            "update the canonical task instead"
        )
    request = extract_section(body, ("请求",))
    if request == "未单独记录。":
        request = ""
    knowledge_summary = normalize_space(metadata.get("knowledge_summary")) or extract_section(body, ("知识处置",))
    if knowledge_summary.startswith("未说明"):
        knowledge_summary = ""
    return {
        "task": {
            "id": task_id,
            "update_existing": True,
            "expected_revision": int(metadata.get("revision", 1) or 1),
            "title": normalize_space(metadata.get("title")),
            "kind": normalize_space(metadata.get("kind") or "task"),
            "status": normalize_space(metadata.get("task_status") or "completed"),
            "request": request,
            "summary": extract_section(body, ("处理摘要",)),
            "result": extract_section(body, ("最终结果",)),
            "scopes": metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [],
            "paths": unique_strings(metadata.get("paths")),
            "symbols": unique_strings(metadata.get("symbols")),
            "topics": unique_strings(metadata.get("topics")),
            "tags": unique_strings(metadata.get("tags")),
            "verification": markdown_bullet_values(raw_markdown_section(body, ("验证",))),
            "deliverable": normalize_space(metadata.get("deliverable")),
            "new_task_reason": normalize_space(metadata.get("new_task_reason")),
            "knowledge_summary": knowledge_summary,
            "knowledge_use": metadata.get("knowledge_use") if isinstance(metadata.get("knowledge_use"), list) else [],
            "source": metadata.get("source") if isinstance(metadata.get("source"), dict) else {},
        },
        "items": [],
    }


def compact_learn_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in payload.items() if key != "reference_check"}
    reference = payload.get("reference_check") if isinstance(payload.get("reference_check"), dict) else {}
    findings = reference.get("findings") if isinstance(reference.get("findings"), list) else []
    unverified = reference.get("unverified") if isinstance(reference.get("unverified"), list) else []
    verified = reference.get("verified") if isinstance(reference.get("verified"), list) else []
    historical = (
        reference.get("historical_cards_skipped")
        if isinstance(reference.get("historical_cards_skipped"), list)
        else []
    )
    result["reference_check"] = {
        "blocking": bool(reference.get("blocking", False)),
        "review_required": bool(reference.get("review_required", False)),
        "finding_count": len(findings),
        "unverified_count": len(unverified),
        "verified_count": len(verified),
        "historical_cards_skipped_count": len(historical),
        "findings": findings,
        "unverified": unverified,
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="project root or a path inside the project")
    subparsers = parser.add_subparsers(dest="command", required=True)

    brief_parser = subparsers.add_parser("brief", help="read-only task-oriented knowledge brief")
    brief_parser.add_argument("--task", required=True, help="current user request or task description")
    brief_parser.add_argument("--path", action="append", default=[], help="relevant project path; repeatable")
    brief_parser.add_argument("--symbol", action="append", default=[], help="relevant symbol; repeatable")
    brief_parser.add_argument("--topic", action="append", default=[], help="configured business topic; repeatable")
    brief_parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="structured scope as <repository>:<path>#<symbol>; repeatable",
    )
    brief_parser.add_argument("--limit", type=int, help="override maximum selected knowledge items")
    brief_parser.add_argument("--include-history", action="store_true", help="return deprecated and superseded cards separately")
    brief_parser.add_argument("--include-legacy", action="store_true", help="read retained legacy pages for migration or history work")
    brief_parser.add_argument("--include-superseded", action="store_true", help=argparse.SUPPRESS)
    brief_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")

    learn_parser = subparsers.add_parser("learn", help="validate and persist a task note plus durable knowledge cards")
    learn_parser.add_argument("--file", required=True, help="learning JSON file, or '-' for stdin")
    learn_parser.add_argument("--dry-run", action="store_true", help="validate and show the write plan without filesystem changes")
    learn_parser.add_argument("--plan-token", help="apply the exact state and identifiers validated by a prior dry-run")
    learn_parser.add_argument(
        "--compact",
        action="store_true",
        help="keep actionable reference details and counts while omitting the full verified-reference list",
    )

    consolidate_parser = subparsers.add_parser("consolidate", help="archive duplicate task notes into one canonical logical task")
    consolidate_parser.add_argument("--file", required=True, help="consolidation JSON file, or '-' for stdin")
    consolidate_parser.add_argument("--dry-run", action="store_true", help="validate the complete consolidation without writes")
    consolidate_parser.add_argument("--plan-token", help="apply the exact consolidation validated by a prior dry-run")

    doctor_parser = subparsers.add_parser("doctor", help="read-only structural integrity check; does not validate semantic truth")
    doctor_parser.add_argument("--check-current-references", action="store_true", help="also run deterministic current path/symbol checks")
    subparsers.add_parser("status", help="read-only knowledge inventory")

    audit_parser = subparsers.add_parser("audit", help="read-only structure, reference, governance, and delivery acceptance")
    audit_parser.add_argument("--format", choices=("text", "json"), default="text")
    audit_scope = audit_parser.add_mutually_exclusive_group()
    audit_scope.add_argument("--cached", action="store_true", help="audit staged Git delivery")
    audit_scope.add_argument("--base", help="audit committed delivery from <base>...HEAD")

    topics_parser = subparsers.add_parser("topics", help="suggest or safely update business-topic navigation")
    topic_commands = topics_parser.add_subparsers(dest="topics_command", required=True)
    topics_list_parser = topic_commands.add_parser("list", help="list configured canonical topics and aliases")
    topics_list_parser.add_argument("--format", choices=("text", "json"), default="text")
    topics_suggest = topic_commands.add_parser("suggest", help="read-only deterministic topic suggestions")
    topics_suggest.add_argument("--format", choices=("json",), default="json")
    topics_update_parser = topic_commands.add_parser("update", help="reviewed bulk topic configuration and assignment update")
    topics_update_parser.add_argument("--file", required=True, help="topic update JSON file, or '-' for stdin")
    topics_update_parser.add_argument("--dry-run", action="store_true", help="validate the complete update without writes")
    topics_update_parser.add_argument("--plan-token", help="apply the exact update validated by a prior dry-run")

    drift_parser = subparsers.add_parser("drift", help="read-only current-reference and Git knowledge-writeback checks")
    drift_scope = drift_parser.add_mutually_exclusive_group()
    drift_scope.add_argument("--cached", action="store_true", help="check staged changes")
    drift_scope.add_argument("--base", help="check committed changes from <base>...HEAD")
    drift_scope.add_argument("--references-only", action="store_true", help="check current card paths and symbols without Git")
    drift_parser.add_argument("--format", choices=("text", "json"), default="text")

    reindex_parser = subparsers.add_parser("reindex", help="rebuild generated Markdown and JSONL indexes")
    reindex_parser.add_argument("--dry-run", action="store_true", help="show stale indexes without writing")

    template_parser = subparsers.add_parser("template", help="print a fill-required learning JSON template")
    template_parser.add_argument("--title", default="", help="task title")
    template_parser.add_argument("--kind", default="task", help="task kind")
    template_parser.add_argument("--task-id", help="prefill an update snapshot from an existing task note")
    template_parser.add_argument("--output", help="explicit output file; stdout when omitted")
    return parser


def command_main(args: argparse.Namespace) -> tuple[int, str]:
    root = find_project_root(Path(args.root))
    config = load_config(root)
    if args.command == "brief":
        topic_resolution = resolve_brief_topics(args.topic, config)
        topics = topic_resolution["resolved"]
        scopes = [parse_scope_argument(value) for value in args.scope]
        payload = selected_brief_payload(
            root,
            config,
            normalize_space(args.task),
            unique_strings(args.path),
            unique_strings(args.symbol),
            args.limit,
            bool(args.include_history or args.include_superseded),
            topics,
            scopes,
            bool(args.include_legacy),
        )
        attach_brief_topic_resolution(payload, topic_resolution)
        return 0, json_dump(payload) if args.format == "json" else render_brief_markdown(payload)
    if args.command == "learn":
        if args.file == "-":
            try:
                raw = json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise KnowledgeError(f"invalid learning JSON from stdin: line {exc.lineno}, column {exc.colno}") from exc
        else:
            raw = read_json(Path(args.file).expanduser().resolve())
        payload = learn(
            root,
            config,
            raw,
            dry_run=bool(args.dry_run),
            plan_token=normalize_space(args.plan_token) or None,
        )
        return 0, json_dump(compact_learn_result(payload) if args.compact else payload)
    if args.command == "consolidate":
        if args.file == "-":
            try:
                raw = json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise KnowledgeError(f"invalid consolidation JSON from stdin: line {exc.lineno}, column {exc.colno}") from exc
        else:
            raw = read_json(Path(args.file).expanduser().resolve())
        return 0, json_dump(
            consolidate(
                root,
                config,
                raw,
                dry_run=bool(args.dry_run),
                plan_token=normalize_space(args.plan_token) or None,
            )
        )
    if args.command == "doctor":
        payload = doctor(root, config, check_current_references=bool(args.check_current_references))
        return (0 if payload["ok"] else 1), json_dump(payload)
    if args.command == "audit":
        payload = audit_payload(
            root,
            config,
            cached=bool(args.cached),
            base=normalize_space(args.base) or None,
        )
        output = json_dump(payload) if args.format == "json" else render_audit_text(payload)
        return int(payload["exit_code"]), output
    if args.command == "topics":
        if args.topics_command == "list":
            payload = topics_list_payload(root, config)
            return 0, json_dump(payload) if args.format == "json" else render_topics_list_text(payload)
        if args.topics_command == "suggest":
            return 0, json_dump(topics_suggest_payload(root, config))
        if args.file == "-":
            try:
                raw = json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise KnowledgeError(f"invalid topics JSON from stdin: line {exc.lineno}, column {exc.colno}") from exc
        else:
            raw = read_json(Path(args.file).expanduser().resolve())
        return 0, json_dump(
            topics_update(
                root,
                config,
                raw,
                dry_run=bool(args.dry_run),
                plan_token=normalize_space(args.plan_token) or None,
            )
        )
    if args.command == "drift":
        payload = drift_payload(
            root,
            config,
            cached=bool(args.cached),
            base=normalize_space(args.base) or None,
            references_only=bool(args.references_only),
        )
        output = json_dump(payload) if args.format == "json" else render_drift_text(payload)
        return int(payload["exit_code"]), output
    if args.command == "status":
        return 0, json_dump(status_payload(root, config))
    if args.command == "reindex":
        return 0, json_dump({"ok": True, **rebuild_indexes(root, config, dry_run=bool(args.dry_run))})
    if args.command == "template":
        payload = task_update_template(root, config, args.task_id) if args.task_id else template_payload(args.title, args.kind)
        content = json_dump(payload)
        if args.output:
            output = Path(args.output).expanduser().resolve()
            atomic_write_text(output, content)
            return 0, json_dump({"ok": True, "output": str(output)})
        return 0, content
    raise KnowledgeError(f"unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code, output = command_main(args)
    except (KnowledgeError, OSError, UnicodeDecodeError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(output, end="" if output.endswith("\n") else "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
