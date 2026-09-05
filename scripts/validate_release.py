#!/usr/bin/env python3
"""Validate the CodeStable knowledge-only release source and installed runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

RETIRED_SKILLS = ("cs-feat", "cs-issue", "cs-refactor", "cs-roadmap", "cs-model")
RETIRED_TOOLS = (
    "cs_knowledge.py",
    "cs_context.py",
    "cs_eval.py",
    "cs_evolve.py",
    "cs_feedback.py",
    "cs_fixture.py",
    "cs_harness.py",
    "cs_meta.py",
    "cs_observe.py",
    "cs_policy.py",
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run(command: Sequence[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        env=environment,
        text=True,
        capture_output=True,
        check=check,
        timeout=120,
    )


def load_json_output(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise ValueError("command JSON output is not an object")
    return value


def git_init_clean(root: Path) -> None:
    run(["git", "init", "-q"], cwd=root)
    run(["git", "config", "user.email", "codestable-validation@example.invalid"], cwd=root)
    run(["git", "config", "user.name", "CodeStable Validation"], cwd=root)
    run(["git", "add", "."], cwd=root)
    run(["git", "commit", "-qm", "baseline"], cwd=root)


def payload() -> dict[str, Any]:
    future_use = [
        {"change": "调整订单写入", "actor": "订单维护者", "constraint": "订单与库存保持原子提交"},
        {"change": "拆分库存存储", "actor": "库存维护者", "constraint": "重新评估当前提交边界"},
    ]
    test_evidence = [
        {
            "kind": "test",
            "artifact": "tests.test_orders.RollbackTests",
            "result": "匿名回滚夹具通过",
            "supports": "库存不足时订单与库存都不产生部分状态",
        }
    ]
    return {
        "task": {
            "title": "验证订单库存知识闭环",
            "kind": "issue",
            "status": "completed",
            "request": "修复库存不足时订单仍提交",
            "summary": "将订单写入和库存预留收敛到同一本地事务。",
            "result": "库存不足时订单和库存均保持不变。",
            "paths": ["src/orders/service.py"],
            "symbols": ["OrderService.create"],
            "tags": ["orders", "inventory"],
            "verification": ["python3 -m unittest tests.test_orders"],
            "knowledge_summary": "新增事务、验收和决策卡片。",
            "source": {"fixture": "release-validation"},
        },
        "items": [
            {
                "category": "transaction-boundaries",
                "title": "订单与库存共享本地事务",
                "knowledge": "订单写入和库存预留必须在同一本地事务内提交。",
                "rationale": "避免部分成功。",
                "implications": ["库存不足必须在提交点前失败"],
                "future_use": future_use,
                "confidence": "verified",
                "evidence": test_evidence,
            },
            {
                "category": "acceptance",
                "title": "库存不足回滚验收",
                "knowledge": "库存不足时订单数和库存数均保持不变。",
                "future_use": [
                    {"change": "修改库存失败处理", "actor": "服务维护者", "constraint": "失败路径不产生部分状态"},
                    {"change": "增加订单状态", "actor": "订单维护者", "constraint": "回滚验收仍然成立"},
                ],
                "confidence": "verified",
                "evidence": test_evidence,
            },
            {
                "category": "decisions",
                "title": "同库时采用本地事务",
                "knowledge": "订单与库存同库期间采用本地事务，不引入异步补偿。",
                "context": "订单与库存位于同一关系数据库。",
                "rationale": "单事务是当前最小且可验证的边界。",
                "alternatives": ["提交后异步补偿", "分布式事务"],
                "consequences": ["库存失败会回滚订单", "拆库时必须重新评估"],
                "future_use": future_use,
                "confidence": "accepted",
                "evidence": [
                    {
                        "kind": "accepted-decision",
                        "artifact": "release-validation decision fixture",
                        "result": "本地事务边界被明确接受",
                        "supports": "同库期间不引入异步补偿或分布式事务",
                    }
                ],
            },
        ],
    }


def add_result(results: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    results.append({"name": name, "ok": bool(ok), "detail": detail})


def validate(source: Path) -> dict[str, Any]:
    source = source.resolve()
    results: list[dict[str, Any]] = []
    bootstrap = source / "skills" / "cs" / "scripts" / "bootstrap.py"
    shared_tool = source / "skills" / "cs" / "scripts" / "cs_knowledge.py"
    asset_root = source / "skills" / "cs" / "assets" / "project"

    try:
        process = run([sys.executable, "scripts/build_runtime.py", "--check"], cwd=source)
        add_result(results, "generated_runtime_sync", True, process.stdout.strip())
    except Exception as exc:
        add_result(results, "generated_runtime_sync", False, str(exc))

    try:
        process = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=source)
        add_result(results, "unit_regression_suite", True, process.stderr.strip().splitlines()[-3:])
    except Exception as exc:
        add_result(results, "unit_regression_suite", False, str(exc))

    skills = sorted(path.name for path in (source / "skills").iterdir() if path.is_dir()) if (source / "skills").is_dir() else []
    add_result(results, "single_public_skill", skills == ["cs"], {"skills": skills})
    retired_present = [name for name in RETIRED_SKILLS if (source / "skills" / name).exists()]
    add_result(results, "retired_skills_absent", not retired_present, {"present": retired_present})
    asset_retired = [name for name in RETIRED_TOOLS if (asset_root / ".codestable" / "tools" / name).exists()]
    add_result(results, "retired_tools_absent_from_assets", not asset_retired, {"present": asset_retired})

    try:
        canonical_doctor = load_json_output(run([sys.executable, str(shared_tool), "--root", str(asset_root), "doctor"]))
        add_result(results, "canonical_assets_doctor", bool(canonical_doctor.get("ok")), canonical_doctor)
    except Exception as exc:
        add_result(results, "canonical_assets_doctor", False, str(exc))

    with tempfile.TemporaryDirectory() as temporary:
        fresh = Path(temporary) / "fresh"
        fresh.mkdir()
        try:
            install = load_json_output(run([sys.executable, str(bootstrap), "--root", str(fresh)]))
            tool = shared_tool
            add_result(
                results,
                "fresh_install_shared_runtime",
                bool(install.get("ok"))
                and install.get("runtime_contract", {}).get("ok") is True
                and install.get("runtime_source") == "skill"
                and Path(str(install.get("runtime_path"))).resolve() == shared_tool.resolve()
                and not (fresh / ".codestable" / "tools" / "cs_knowledge.py").exists(),
                install,
            )
            preflight = load_json_output(run([sys.executable, str(bootstrap), "--root", str(fresh), "--check"]))
            add_result(
                results,
                "fresh_install_distribution_preflight",
                preflight.get("ok") is True
                and preflight.get("read_only") is True
                and preflight.get("status") == "current"
                and preflight.get("runtime_contract", {}).get("ok") is True
                and preflight.get("runtime_source") == "skill"
                and Path(str(preflight.get("runtime_path"))).resolve() == shared_tool.resolve(),
                preflight,
            )
            doctor = load_json_output(run([sys.executable, str(tool), "--root", str(fresh), "doctor"]))
            add_result(results, "fresh_install_doctor", bool(doctor.get("ok")), doctor)

            git_init_clean(fresh)
            learning = fresh / "learning.json"
            learning.write_text(json.dumps(payload(), ensure_ascii=False, indent=2), encoding="utf-8")
            run(["git", "add", "learning.json"], cwd=fresh)
            run(["git", "commit", "-qm", "learning input"], cwd=fresh)
            before_digest = tree_digest(fresh / ".codestable")
            before_status = run(["git", "status", "--porcelain"], cwd=fresh).stdout
            read_commands = (
                [sys.executable, str(bootstrap), "--root", str(fresh), "--check"],
                [sys.executable, str(tool), "--root", str(fresh), "brief", "--task", "订单库存事务", "--path", "src/orders/service.py"],
                [sys.executable, str(tool), "--root", str(fresh), "brief", "--task", "订单库存事务", "--topic", "synthetic-unknown", "--path", "src/orders/service.py", "--format", "json"],
                [sys.executable, str(tool), "--root", str(fresh), "status"],
                [sys.executable, str(tool), "--root", str(fresh), "doctor"],
                [sys.executable, str(tool), "--root", str(fresh), "drift", "--references-only", "--format", "json"],
                [sys.executable, str(tool), "--root", str(fresh), "audit", "--format", "json"],
                [sys.executable, str(tool), "--root", str(fresh), "topics", "list", "--format", "json"],
                [sys.executable, str(tool), "--root", str(fresh), "topics", "suggest"],
                [sys.executable, str(tool), "--root", str(fresh), "reindex", "--dry-run"],
            )
            for command in read_commands:
                run(command)
            dry_plan = load_json_output(
                run([sys.executable, str(tool), "--root", str(fresh), "learn", "--file", str(learning), "--dry-run"])
            )
            full_plan = load_json_output(
                run(
                    [
                        sys.executable,
                        str(tool),
                        "--root",
                        str(fresh),
                        "learn",
                        "--file",
                        str(learning),
                        "--dry-run",
                        "--full",
                    ]
                )
            )
            task_template = load_json_output(
                run([sys.executable, str(tool), "--root", str(fresh), "template", "--title", "Release task template"])
            )
            card_template = load_json_output(
                run(
                    [
                        sys.executable,
                        str(tool),
                        "--root",
                        str(fresh),
                        "template",
                        "--title",
                        "Release card template",
                        "--card-category",
                        "architecture",
                        "--card-category",
                        "decisions",
                    ]
                )
            )
            add_result(
                results,
                "compact_default_and_disposition_templates",
                dry_plan.get("output_mode") == "compact"
                and "verified" not in dry_plan.get("reference_check", {})
                and "verified" in full_plan.get("reference_check", {})
                and task_template.get("items") == []
                and len(task_template.get("task", {})) == 9
                and [item.get("category") for item in card_template.get("items", [])]
                == ["architecture", "decisions"],
                {
                    "compact": dry_plan,
                    "full_verified_count": len(full_plan.get("reference_check", {}).get("verified", [])),
                    "task_template_fields": sorted(task_template.get("task", {})),
                    "card_categories": [item.get("category") for item in card_template.get("items", [])],
                },
            )
            after_digest = tree_digest(fresh / ".codestable")
            after_status = run(["git", "status", "--porcelain"], cwd=fresh).stdout
            add_result(
                results,
                "read_and_dry_run_zero_writes",
                before_digest == after_digest and before_status == after_status == "",
                {"digest_equal": before_digest == after_digest, "git_clean": after_status == ""},
            )

            learned = load_json_output(
                run(
                    [
                        sys.executable,
                        str(tool),
                        "--root",
                        str(fresh),
                        "learn",
                        "--file",
                        str(learning),
                        "--plan-token",
                        str(dry_plan["plan_token"]),
                    ]
                )
            )
            post_doctor = load_json_output(run([sys.executable, str(tool), "--root", str(fresh), "doctor"]))
            brief = load_json_output(
                run(
                    [
                        sys.executable,
                        str(tool),
                        "--root",
                        str(fresh),
                        "brief",
                        "--task",
                        "修改订单库存事务",
                        "--path",
                        "src/orders/service.py",
                        "--format",
                        "json",
                    ]
                )
            )
            titles = {item.get("title") for item in brief.get("knowledge", [])}
            add_result(
                results,
                "knowledge_round_trip",
                len(learned.get("created_cards", [])) == 3
                and learned.get("task_id") == dry_plan.get("task_id")
                and post_doctor.get("ok") is True
                and "订单与库存共享本地事务" in titles
                and "legacy_clues" not in brief,
                {"learn": learned, "doctor": post_doctor, "matched_titles": sorted(title for title in titles if title)},
            )
            repeated = load_json_output(run([sys.executable, str(tool), "--root", str(fresh), "learn", "--file", str(learning)]))
            add_result(results, "learning_idempotency", repeated.get("idempotent") is True, repeated)
        except Exception as exc:
            add_result(results, "fresh_install_flow", False, str(exc))

    with tempfile.TemporaryDirectory() as temporary:
        existing = Path(temporary) / "existing"
        cs = existing / ".codestable"
        (cs / "model").mkdir(parents=True)
        (cs / "wiki").mkdir()
        (cs / "model" / "domain.md").write_text("outdated synthetic rule\n")
        (cs / "wiki" / "old.md").write_text("old card body\n")
        (cs / "config.json").write_text('{"schema_version":3,"custom":{"old":true}}')
        source_file = existing / "service.py"
        source_file.write_text("def ready():\n    return True\n")
        try:
            before = tree_digest(existing)
            preflight = load_json_output(run([sys.executable, str(bootstrap), "--root", str(existing), "--check"], check=False))
            plan = load_json_output(run([sys.executable, str(bootstrap), "--root", str(existing), "--rebuild", "--dry-run"]))
            preview_read_only = tree_digest(existing) == before
            rebuilt = load_json_output(run([sys.executable, str(bootstrap), "--root", str(existing), "--rebuild", "--plan-token", plan["plan_token"]]))
            config = json.loads((cs / "config.json").read_text())
            learning = existing / "learning.json"
            value = payload()
            value["task"].update(title="验证重建后的当前知识", paths=["service.py"], symbols=["ready"], knowledge_summary="建立当前入口卡片。")
            value["items"] = [{
                "category": "interfaces", "title": "当前服务就绪入口", "knowledge": "ready 返回 True 表示服务就绪。",
                "confidence": "verified",
                "evidence": [{"kind": "implementation", "artifact": "service.py#ready", "result": "函数直接返回 True", "supports": "入口的返回值约定"}],
                "future_use": [{"change": "增加就绪条件", "actor": "服务维护者", "constraint": "复核 True 的含义"}, {"change": "替换调用方", "actor": "接口维护者", "constraint": "保持布尔返回值契约"}],
            }]
            learning.write_text(json.dumps(value, ensure_ascii=False))
            dry = load_json_output(run([sys.executable, str(shared_tool), "--root", str(existing), "learn", "--file", str(learning), "--dry-run"]))
            learned = load_json_output(run([sys.executable, str(shared_tool), "--root", str(existing), "learn", "--file", str(learning), "--plan-token", dry["plan_token"]]))
            brief = load_json_output(run([sys.executable, str(shared_tool), "--root", str(existing), "brief", "--task", "就绪入口", "--path", "service.py", "--format", "json"]))
            doctor = load_json_output(run([sys.executable, str(shared_tool), "--root", str(existing), "doctor", "--check-current-references"]))
            add_result(results, "explicit_rebuild_and_new_knowledge", (
                preflight["status"] == "needs-rebuild" and preview_read_only and rebuilt.get("ok") is True
                and not rebuilt["knowledge_build"]["complete"]
                and not (cs / "model").exists() and not (cs / "wiki" / "old.md").exists()
                and not (cs / "backups").exists() and "custom" not in config and config["schema_version"] == 4
                and source_file.read_text() == "def ready():\n    return True\n"
                and len(learned["created_cards"]) == 1
                and [item["title"] for item in brief["knowledge"]] == ["当前服务就绪入口"]
                and doctor.get("ok") is True
            ), {"preview_read_only": preview_read_only, "old_data_absent": not (cs / "model").exists(), "created_cards": len(learned["created_cards"]), "doctor_ok": doctor.get("ok")})
        except Exception as exc:
            add_result(results, "explicit_rebuild_and_new_knowledge", False, str(exc))

    ok = all(item["ok"] for item in results)
    return {
        "ok": ok,
        "generated_at": now_iso(),
        "source": str(source),
        "version": (source / "VERSION").read_text(encoding="utf-8").strip() if (source / "VERSION").is_file() else None,
        "results": results,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# CodeStable Compact release validation",
        "",
        f"- Result: **{'PASS' if report['ok'] else 'FAIL'}**",
        f"- Version: `{report.get('version')}`",
        f"- Generated: `{report['generated_at']}`",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for item in report["results"]:
        lines.append(f"| `{item['name']}` | {'PASS' if item['ok'] else 'FAIL'} |")
    lines.extend(("", "## Details", ""))
    for item in report["results"]:
        lines.append(f"### {item['name']} — {'PASS' if item['ok'] else 'FAIL'}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(item["detail"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".", help="release source root")
    parser.add_argument("--json-out", help="write machine-readable report")
    parser.add_argument("--md-out", help="write Markdown report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate(Path(args.source))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
