#!/usr/bin/env python3
"""Install or upgrade the project-local CodeStable knowledge wiki runtime.

Fresh installs seed a Markdown wiki and one dependency-free tool. Upgrades
refresh only shipped runtime files, back up every replaced/retired file, and
preserve project-authored wiki cards plus all legacy model/knowledge/work data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

RUNTIME_MODE = "knowledge_wiki"
RUNTIME_SCHEMA = 1


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def deep_merge(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, default in defaults.items():
        current = existing.get(key)
        if isinstance(default, dict) and isinstance(current, dict):
            result[key] = deep_merge(default, current)
        elif key in existing:
            result[key] = current
        else:
            result[key] = default
    for key, value in existing.items():
        if key not in result:
            result[key] = value
    return result


def unique_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def normalize_current_config(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    merged = deep_merge(defaults, existing)
    merged["schema_version"] = RUNTIME_SCHEMA
    merged["mode"] = RUNTIME_MODE
    merged["version"] = defaults.get("version")
    default_wiki = defaults.get("wiki") if isinstance(defaults.get("wiki"), dict) else {}
    wiki = merged.setdefault("wiki", {})
    if not isinstance(wiki, dict):
        wiki = dict(default_wiki)
        merged["wiki"] = wiki
    categories = unique_strings(wiki.get("categories"))
    for category in unique_strings(default_wiki.get("categories")):
        if category not in categories:
            categories.append(category)
    wiki["categories"] = categories
    roots = unique_strings(wiki.get("legacy_read_roots"))
    for root in unique_strings(default_wiki.get("legacy_read_roots")):
        if root not in roots:
            roots.append(root)
    wiki["legacy_read_roots"] = roots
    return merged


def migrate_legacy_config(defaults: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    migrated = json.loads(json.dumps(defaults))
    if existing:
        for key in ("project", "extensions", "custom"):
            if key in existing:
                migrated[key] = existing[key]
        migrated["migration"] = {
            "migrated_at": now_iso(),
            "from_schema_version": existing.get("schema_version"),
            "from_mode": existing.get("mode"),
            "legacy_runtime_preserved": True,
        }
    return migrated


def asset_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "project"


def load_manifest(source_root: Path) -> dict[str, Any]:
    path = source_root / ".codestable" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("asset manifest root must be an object")
    return data


def unique_backup_root(target_root: Path) -> Path:
    base = target_root / ".codestable" / "backups" / now_stamp()
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = Path(f"{base}-{counter:02d}")
        counter += 1
    return candidate


def backup_file(target_root: Path, target: Path, backup_root: Path) -> str:
    relative = target.relative_to(target_root)
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, destination)
    return relative.as_posix()


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if target.suffix == ".py" and "tools" in target.parts:
        target.chmod(target.stat().st_mode | stat.S_IXUSR)


def install(target_root: Path, upgrade: bool = False) -> dict[str, Any]:
    source_root = asset_root()
    if not source_root.is_dir():
        raise RuntimeError(f"asset root not found: {source_root}")
    manifest = load_manifest(source_root)
    managed = set(unique_strings(manifest.get("managed_files")))
    seeds = set(unique_strings(manifest.get("seed_files")))
    retired = unique_strings(manifest.get("retired_files"))

    target_root = target_root.expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    backup_root = unique_backup_root(target_root)
    created: list[str] = []
    updated: list[str] = []
    preserved: list[str] = []
    retired_files: list[str] = []
    backed_up: list[str] = []

    source_config = source_root / ".codestable" / "config.json"
    target_config = target_root / ".codestable" / "config.json"
    defaults = json.loads(source_config.read_text(encoding="utf-8"))
    existing: dict[str, Any] | None = None
    config_invalid = False
    if target_config.exists():
        try:
            loaded = json.loads(target_config.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("config root is not an object")
            existing = loaded
        except (json.JSONDecodeError, ValueError):
            config_invalid = True

    if existing and existing.get("mode") == RUNTIME_MODE and int(existing.get("schema_version", 0) or 0) == RUNTIME_SCHEMA:
        desired_config = normalize_current_config(defaults, existing)
    else:
        desired_config = migrate_legacy_config(defaults, existing)

    if not target_config.exists():
        atomic_write(target_config, json_dump(desired_config))
        created.append(".codestable/config.json")
    else:
        current_text = target_config.read_text(encoding="utf-8")
        desired_text = json_dump(desired_config)
        if config_invalid or current_text != desired_text:
            backed_up.append(backup_file(target_root, target_config, backup_root))
            atomic_write(target_config, desired_text)
            updated.append(".codestable/config.json")
        else:
            preserved.append(".codestable/config.json")

    all_asset_files: dict[str, Path] = {}
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        relative = source.relative_to(source_root).as_posix()
        if relative == ".codestable/config.json":
            continue
        all_asset_files[relative] = source

    declared = managed | seeds
    undeclared = sorted(set(all_asset_files) - declared)
    missing = sorted(declared - set(all_asset_files))
    if undeclared or missing:
        raise RuntimeError(f"asset manifest mismatch: undeclared={undeclared}, missing={missing}")

    for relative, source in sorted(all_asset_files.items()):
        target = target_root / relative
        if relative in seeds:
            if target.exists():
                preserved.append(relative)
            else:
                copy_file(source, target)
                created.append(relative)
            continue
        if target.exists():
            if upgrade and sha256_file(source) != sha256_file(target):
                backed_up.append(backup_file(target_root, target, backup_root))
                copy_file(source, target)
                updated.append(relative)
            else:
                preserved.append(relative)
        else:
            copy_file(source, target)
            created.append(relative)

    if upgrade:
        for relative in retired:
            target = target_root / relative
            if not target.is_file():
                continue
            backed_up.append(backup_file(target_root, target, backup_root))
            target.unlink()
            retired_files.append(relative)

    if not backed_up and backup_root.exists():
        shutil.rmtree(backup_root)

    installed_tool = target_root / ".codestable" / "tools" / "cs_knowledge.py"
    source_tool = source_root / ".codestable" / "tools" / "cs_knowledge.py"
    return {
        "root": str(target_root),
        "mode": RUNTIME_MODE,
        "version": defaults.get("version"),
        "created": sorted(created),
        "updated": sorted(updated),
        "preserved": sorted(set(preserved)),
        "retired": sorted(retired_files),
        "backup": str(backup_root) if backed_up else None,
        "backed_up": sorted(set(backed_up)),
        "tool_hash_matches_asset": installed_tool.is_file() and sha256_file(installed_tool) == sha256_file(source_tool),
        "project_data_preserved": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="target project root")
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="refresh shipped runtime files and retire obsolete control-plane tools after backup",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = install(Path(args.root), upgrade=bool(args.upgrade))
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
