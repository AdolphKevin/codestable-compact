#!/usr/bin/env python3
"""Plan or perform a non-destructive migration from legacy CodeStable layout.

Default mode is dry-run. Current-truth candidates are staged for review;
historical execution directories are copied under work/archive/legacy, where
normal retrieval excludes them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

HISTORY_DIRS = ("features", "issues", "refactors", "goals", "audits")


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def iter_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    return (
        path for path in sorted(base.rglob("*"))
        if path.is_file() and not path.is_symlink() and ".git" not in path.parts
    )


def add_tree(plan: list[dict[str, str]], source: Path, destination: Path, category: str) -> None:
    if not source.exists():
        return
    for path in iter_files(source):
        relative = path.relative_to(source)
        target = destination / relative
        plan.append({
            "category": category,
            "source": str(path),
            "destination": str(target),
            "action": "skip_exists" if target.exists() else "copy",
        })


def build_plan(root: Path) -> list[dict[str, str]]:
    cs = root / ".codestable"
    staging = cs / "migration-staging"
    plan: list[dict[str, str]] = []

    requirements = cs / "requirements"
    direct_files = {
        requirements / "VISION.md": staging / "model" / "vision.legacy.md",
        requirements / "CONTEXT.md": staging / "model" / "domain.legacy.md",
        requirements / "CONTEXT-MAP.md": staging / "model" / "context-map.legacy.md",
    }
    for source, destination in direct_files.items():
        if source.is_file():
            plan.append({
                "category": "current_truth_candidate",
                "source": str(source),
                "destination": str(destination),
                "action": "skip_exists" if destination.exists() else "copy",
            })

    if requirements.exists():
        excluded = {path.resolve() for path in direct_files}
        for path in iter_files(requirements):
            if path.resolve() in excluded:
                continue
            relative = path.relative_to(requirements)
            parts = list(relative.parts)
            if "adrs" in parts:
                adr_index = parts.index("adrs")
                context_parts = parts[:adr_index]
                adr_parts = parts[adr_index + 1:]
                destination = staging / "model" / "decisions" / Path(*context_parts, *adr_parts)
            else:
                destination = staging / "model" / "requirements" / relative
            plan.append({
                "category": "current_truth_candidate",
                "source": str(path),
                "destination": str(destination),
                "action": "skip_exists" if destination.exists() else "copy",
            })

    add_tree(plan, cs / "roadmap", staging / "model" / "roadmaps", "current_truth_candidate")
    add_tree(plan, cs / "compound", staging / "knowledge" / "notes", "knowledge_candidate")

    for directory in HISTORY_DIRS:
        add_tree(
            plan,
            cs / directory,
            cs / "work" / "archive" / "legacy" / directory,
            "historical_work",
        )

    return plan


def historical_roots_from_plan(root: Path, plan: list[dict[str, str]]) -> list[dict[str, Any]]:
    cs = root / ".codestable"
    entries: list[dict[str, Any]] = []
    for kind in HISTORY_DIRS:
        source_base = cs / kind
        if not source_base.is_dir():
            continue
        for child in sorted(source_base.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            destination = cs / "work" / "archive" / "legacy" / kind / child.name
            entries.append({
                "id": child.name,
                "kind": kind[:-1] if kind.endswith("s") else kind,
                "title": child.name,
                "completed_at": None,
                "summary": "Imported legacy work; not current truth and excluded from default retrieval.",
                "legacy": True,
                "path": destination.relative_to(root).as_posix(),
            })
    return entries


def existing_archive_ids(index_path: Path) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    if not index_path.exists():
        return result
    for line in index_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        result.add((str(entry.get("id", "")), str(entry.get("path", ""))))
    return result


def apply_plan(root: Path, plan: list[dict[str, str]]) -> dict[str, Any]:
    copied = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    for item in plan:
        if item["action"] == "skip_exists":
            skipped += 1
            continue
        source = Path(item["source"])
        destination = Path(item["destination"])
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            item["action"] = "copied"
            copied += 1
        except OSError as exc:
            item["action"] = "error"
            item["error"] = str(exc)
            errors.append({"source": str(source), "error": str(exc)})

    index_path = root / ".codestable" / "work" / "archive-index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    known = existing_archive_ids(index_path)
    indexed = 0
    with index_path.open("a", encoding="utf-8", newline="\n") as handle:
        for entry in historical_roots_from_plan(root, plan):
            key = (str(entry["id"]), str(entry["path"]))
            if key in known:
                continue
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            known.add(key)
            indexed += 1

    return {"copied": copied, "skipped": skipped, "indexed": indexed, "errors": errors}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="target repository root")
    parser.add_argument("--apply", action="store_true", help="copy files; default is dry-run")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    cs = root / ".codestable"
    if not cs.is_dir():
        print(json_dump({"ok": False, "error": f"missing legacy directory: {cs}"}), end="")
        return 2

    plan = build_plan(root)
    result: dict[str, Any] = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "root": str(root),
        "generated_at": now_iso(),
        "summary": {
            "current_truth_candidates": sum(item["category"] == "current_truth_candidate" for item in plan),
            "knowledge_candidates": sum(item["category"] == "knowledge_candidate" for item in plan),
            "historical_files": sum(item["category"] == "historical_work" for item in plan),
            "total": len(plan),
        },
        "plan": plan,
    }
    if args.apply:
        result["apply"] = apply_plan(root, plan)
        report_path = cs / "migration-report.json"
        report_path.write_text(json_dump(result), encoding="utf-8")
        result["report"] = str(report_path)
        if result["apply"]["errors"]:
            result["ok"] = False

    print(json_dump(result), end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
