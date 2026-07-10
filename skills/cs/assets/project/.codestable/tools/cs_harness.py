#!/usr/bin/env python3
"""Read-only access to the active CodeStable Harness during normal work.

This module deliberately exposes only current Harness identity and a bounded
query over the already-promoted playbook. It never reads observations,
evolution cases, evaluator state, rejected candidates, or version snapshots,
and it has no mutation commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = 1
MAX_RULE_CHARS = 4096
MAX_COLLECTION_ITEMS = 64


class HarnessReadError(RuntimeError):
    """The active Harness cannot be read safely."""


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HarnessReadError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HarnessReadError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HarnessReadError(f"JSON root must be an object: {path}")
    return value


def normalize_relative(value: str) -> str:
    raw = value.replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise HarnessReadError(f"unsafe Harness path: {value!r}")
    return path.as_posix()


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.exists():
            raise HarnessReadError(f"project root does not exist: {root}")
        return root
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".codestable").is_dir() or (candidate / ".git").exists():
            return candidate
    return current


def cs_dir(root: Path) -> Path:
    return root / ".codestable"


def editable_surface_records(root: Path) -> list[dict[str, Any]]:
    manifest_path = cs_dir(root) / "harness" / "manifest.json"
    manifest = read_json(manifest_path)
    surfaces = manifest.get("editable_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise HarnessReadError("Harness manifest has no editable surfaces")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(
        (item for item in surfaces if isinstance(item, dict)),
        key=lambda item: str(item.get("path") or ""),
    ):
        surface_id = str(item.get("id") or "").strip()
        relative = normalize_relative(str(item.get("path") or ""))
        if not surface_id or surface_id in seen:
            raise HarnessReadError(f"invalid or duplicate Harness surface id: {surface_id!r}")
        path = root / relative
        if not path.is_file():
            raise HarnessReadError(f"missing active Harness surface: {relative}")
        records.append({"surface_id": surface_id, "path": relative, "sha256": sha256_file(path)})
        seen.add(surface_id)
    return records


def active_identity(root: Path) -> dict[str, Any]:
    harness = cs_dir(root) / "harness"
    registry_path = harness / "registry.json"
    manifest_path = harness / "manifest.json"
    registry = read_json(registry_path)
    active_version = str(registry.get("active_version") or "seed")
    records = editable_surface_records(root)
    content_sha256 = hashlib.sha256(canonical_json(records)).hexdigest()
    snapshot_sha256 = None
    versions = registry.get("versions")
    if isinstance(versions, list):
        for item in versions:
            if isinstance(item, dict) and str(item.get("id")) == active_version:
                snapshot_sha256 = item.get("content_sha256")
                break
    return {
        "schema_version": SCHEMA_VERSION,
        "version": active_version,
        "content_sha256": content_sha256,
        "snapshot_content_sha256": snapshot_sha256,
        "drift_detected": bool(snapshot_sha256 and snapshot_sha256 != content_sha256),
        "manifest_sha256": sha256_file(manifest_path),
    }


def clean_string(value: Any, limit: int = MAX_RULE_CHARS) -> str:
    return str(value or "").strip()[:limit]


def clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [clean_string(item, 256) for item in value[:MAX_COLLECTION_ITEMS] if clean_string(item, 256)]


def public_rule(item: dict[str, Any]) -> dict[str, Any]:
    """Return only fields that are safe and useful in normal execution context."""
    result: dict[str, Any] = {
        "id": clean_string(item.get("id"), 128),
        "rule": clean_string(item.get("rule")),
        "status": clean_string(item.get("status") or "active", 32),
        "applies_to": clean_string_list(item.get("applies_to")),
        "keywords": clean_string_list(item.get("keywords")),
    }
    for field in ("source_case", "last_validated"):
        value = clean_string(item.get(field), 256)
        if value:
            result[field] = value
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        result["confidence"] = max(0.0, min(1.0, float(confidence)))
    return result


def query_playbook(
    root: Path,
    *,
    kind: str | None,
    stage: str | None,
    keywords: Sequence[str],
    limit: int,
) -> dict[str, Any]:
    if limit < 0 or limit > 20:
        raise HarnessReadError("playbook query limit must be between 0 and 20")
    path = cs_dir(root) / "harness" / "playbook.jsonl"
    if not path.is_file():
        return {"identity": active_identity(root), "rules": []}
    terms = {value.strip().casefold() for value in keywords if value.strip()}
    scored: list[tuple[int, dict[str, Any]]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarnessReadError(f"invalid active playbook JSONL at line {number}: {exc}") from exc
        if not isinstance(raw, dict):
            raise HarnessReadError(f"active playbook line {number} must be an object")
        item = public_rule(raw)
        if not item["id"] or not item["rule"] or item["status"] != "active":
            continue
        applies = {value.casefold() for value in item["applies_to"]}
        if kind and applies and kind.casefold() not in applies:
            continue
        if stage and applies and stage.casefold() not in applies:
            continue
        haystack = " ".join([item["id"], item["rule"], *item["keywords"]]).casefold()
        score = sum(1 for term in terms if term in haystack)
        if terms and score == 0:
            continue
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return {
        "identity": active_identity(root),
        "rules": [item for _, item in scored[:limit]],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root")

    identity = sub.add_parser("identity", help="show only the current active Harness identity")
    root_arg(identity)

    playbook = sub.add_parser("playbook-query", help="read a bounded set of already-promoted active rules")
    root_arg(playbook)
    playbook.add_argument("--kind")
    playbook.add_argument("--stage")
    playbook.add_argument("--keyword", action="append", default=[])
    playbook.add_argument("--limit", type=int, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root_value = getattr(args, "root", None) or getattr(args, "global_root", None)
    try:
        root = find_project_root(explicit=root_value)
        if args.command == "identity":
            result = {"identity": active_identity(root)}
        elif args.command == "playbook-query":
            result = query_playbook(
                root,
                kind=args.kind,
                stage=args.stage,
                keywords=args.keyword,
                limit=args.limit,
            )
        else:
            raise HarnessReadError(f"unsupported command: {args.command}")
    except (HarnessReadError, OSError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
