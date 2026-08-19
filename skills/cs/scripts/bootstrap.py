#!/usr/bin/env python3
"""Install or structurally upgrade a project's CodeStable knowledge wiki.

Fresh installs seed only project-owned data and configuration. The dependency-
free runtime stays in this Skill and is reused across projects. Upgrades refresh
shipped project files in place and inventory legacy knowledge pages for the
Agent-led semantic audit. No legacy page is copied, promoted, or removed
automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

RUNTIME_MODE = "knowledge_wiki"
RUNTIME_SCHEMA = 3
DEFAULT_CURRENT_ENTRY = ".codestable/wiki/INDEX.md"
ENTRY_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:\./)?\.codestable/(?:wiki|model|knowledge)/[A-Za-z0-9_.\-/]+\.md)"
)
SKILL_COMMAND_PATTERN = re.compile(r"\|\s*`\$cs\s+([^`]+)`\s*\|")
RUNTIME_COMMAND_PATTERN = re.compile(
    r"cs_knowledge\.py(?:\s+--root\s+\S+)?\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?"
)
SKILL_ONLY_COMMANDS = {"init", "upgrade"}
_COMMAND_CONTRACT_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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
    wiki["current_entry"] = str(default_wiki.get("current_entry") or DEFAULT_CURRENT_ENTRY)
    wiki["history_entry"] = str(default_wiki.get("history_entry") or ".codestable/wiki/HISTORY.md")
    wiki["topics_entry"] = str(default_wiki.get("topics_entry") or ".codestable/wiki/TOPICS.md")
    for key in ("repositories", "topics"):
        if not isinstance(wiki.get(key), dict):
            wiki[key] = {}
    if not isinstance(wiki.get("topic_history"), list):
        wiki["topic_history"] = []
    if not isinstance(wiki.get("topic_governance"), dict):
        wiki["topic_governance"] = dict(default_wiki.get("topic_governance") or {})
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
            "project_data_preserved": True,
        }
    return migrated


def asset_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "project"


def shared_runtime_path() -> Path:
    return Path(__file__).resolve().parent / "cs_knowledge.py"


def skill_document_path() -> Path:
    return Path(__file__).resolve().parent.parent / "SKILL.md"


def documented_runtime_commands(path: Path) -> list[str]:
    """Extract the project-runtime commands declared by the Skill command table."""
    content = path.read_text(encoding="utf-8")
    commands: list[str] = []
    for invocation in SKILL_COMMAND_PATTERN.findall(content):
        parts = invocation.strip().split()
        if not parts or parts[0].startswith("<") or parts[0] in SKILL_ONLY_COMMANDS:
            continue
        command = parts[0]
        if command == "topics" and len(parts) > 1 and not parts[1].startswith(("<", "[")):
            command += " " + parts[1]
        if command not in commands:
            commands.append(command)
    for command, nested in RUNTIME_COMMAND_PATTERN.findall(content):
        if command == "topics" and nested:
            command += " " + nested
        if command not in commands:
            commands.append(command)
    return commands


def verify_runtime_command_contract(runtime: Path, skill_path: Path | None = None) -> dict[str, Any]:
    """Verify that every runtime command declared by the Skill has working CLI help."""
    skill_path = skill_path or skill_document_path()
    commands = documented_runtime_commands(skill_path)
    runtime_hash = sha256_file(runtime) if runtime.is_file() else "missing"
    skill_hash = sha256_file(skill_path) if skill_path.is_file() else "missing"
    cache_key = (runtime_hash, skill_hash)
    if cache_key in _COMMAND_CONTRACT_CACHE:
        return json.loads(json.dumps(_COMMAND_CONTRACT_CACHE[cache_key]))
    unavailable: list[dict[str, str]] = []
    if not commands:
        unavailable.append({"command": "<contract>", "detail": "the Skill command table declares no runtime commands"})
    elif not runtime.is_file():
        unavailable.extend({"command": command, "detail": "runtime file is missing"} for command in commands)
    else:
        for command in commands:
            process = subprocess.run(
                [sys.executable, str(runtime), *command.split(), "--help"],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            if process.returncode != 0:
                detail = " ".join((process.stderr or process.stdout).split())[:300]
                unavailable.append({"command": command, "detail": detail or f"exit code {process.returncode}"})
    result = {
        "ok": not unavailable,
        "status": "pass" if not unavailable else "incomplete",
        "documented_commands": commands,
        "unavailable_commands": unavailable,
        "verification": "each documented command path returned successful --help",
    }
    _COMMAND_CONTRACT_CACHE[cache_key] = json.loads(json.dumps(result))
    return result


def distribution_contract() -> dict[str, Any]:
    runtime = shared_runtime_path()
    contract = verify_runtime_command_contract(runtime, skill_document_path())
    if not contract["ok"]:
        missing = ", ".join(value["command"] for value in contract["unavailable_commands"])
        raise RuntimeError(f"Skill/runtime command contract is incomplete: {missing}")
    return {
        **contract,
        "runtime_source": "skill",
        "runtime_path": str(runtime),
    }


def load_manifest(source_root: Path) -> dict[str, Any]:
    path = source_root / ".codestable" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("asset manifest root must be an object")
    return data


def legacy_page_inventory(target_root: Path, roots: Sequence[str]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for relative_root in roots:
        legacy_root = target_root / relative_root
        if not legacy_root.is_dir():
            continue
        for path in sorted(legacy_root.rglob("*.md")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(target_root).as_posix()
            pages.append(
                {
                    "path": relative,
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    return pages


def agents_entry_check(target_root: Path, current_entry: str, legacy_roots: Sequence[str]) -> dict[str, Any]:
    files: list[str] = []
    findings: list[dict[str, Any]] = []
    declared: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(target_root.rglob("AGENTS.md")):
        if any(part == ".git" for part in path.parts) or ".codestable/backups" in path.as_posix():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative_file = path.relative_to(target_root).as_posix()
        files.append(relative_file)
        for number, line in enumerate(content.splitlines(), start=1):
            for match in ENTRY_PATH_PATTERN.finditer(line):
                value = match.group(1).removeprefix("./")
                if not value.casefold().endswith(("/index.md", "/readme.md")):
                    continue
                reference = {"file": relative_file, "line": number, "entry": value}
                declared.setdefault(value, []).append(reference)
                target = target_root / value
                if not target.is_file():
                    findings.append(
                        {
                            "code": "agents.entry.missing",
                            **reference,
                            "detail": f"AGENTS.md points to a missing CodeStable entry: {value}",
                            "action": f"replace it with the current entry {current_entry}",
                        }
                    )
                if any(value == root or value.startswith(root.rstrip("/") + "/") for root in legacy_roots):
                    findings.append(
                        {
                            "code": "agents.entry.retired",
                            **reference,
                            "detail": f"AGENTS.md points to retained legacy knowledge: {value}",
                            "action": f"use {current_entry}; read legacy data only during explicit migration or history work",
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
    return {
        "modified": False,
        "current_entry": current_entry,
        "files_checked": files,
        "findings": findings,
    }


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def install(target_root: Path, upgrade: bool = False) -> dict[str, Any]:
    source_root = asset_root()
    if not source_root.is_dir():
        raise RuntimeError(f"asset root not found: {source_root}")
    source_contract = distribution_contract()
    manifest = load_manifest(source_root)
    managed = set(unique_strings(manifest.get("managed_files")))
    seeds = set(unique_strings(manifest.get("seed_files")))
    retired = unique_strings(manifest.get("retired_files"))
    legacy_roots = unique_strings(manifest.get("legacy_knowledge_roots"))

    target_root = target_root.expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    updated: list[str] = []
    preserved: list[str] = []
    retired_files: list[str] = []

    source_config = source_root / ".codestable" / "config.json"
    target_config = target_root / ".codestable" / "config.json"
    defaults = json.loads(source_config.read_text(encoding="utf-8"))
    existing: dict[str, Any] | None = None
    if target_config.exists():
        try:
            loaded = json.loads(target_config.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("config root is not an object")
            existing = loaded
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                "invalid .codestable/config.json; repair it before install or upgrade"
            ) from exc

    if existing and existing.get("mode") == RUNTIME_MODE:
        desired_config = normalize_current_config(defaults, existing)
    else:
        desired_config = migrate_legacy_config(defaults, existing)

    if not target_config.exists():
        atomic_write(target_config, json_dump(desired_config))
        created.append(".codestable/config.json")
    else:
        current_text = target_config.read_text(encoding="utf-8")
        desired_text = json_dump(desired_config)
        if current_text != desired_text:
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

    legacy_pages = legacy_page_inventory(target_root, legacy_roots)
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
            target.unlink()
            retired_files.append(relative)

    installed_contract = {
        **source_contract,
        "verification": "the shared Skill runtime passed every documented command's --help check",
    }
    if legacy_pages and upgrade:
        migration_status = "pending_page_audit"
    elif legacy_pages:
        migration_status = "upgrade_required"
    else:
        migration_status = "not_required"
    current_entry = str((desired_config.get("wiki") or {}).get("current_entry") or DEFAULT_CURRENT_ENTRY)
    agents_guidance = agents_entry_check(target_root, current_entry, legacy_roots)
    preserve_roots = unique_strings(manifest.get("preserve_roots"))
    preserved_noncurrent = [
        {
            "path": value,
            "normal_task_read": False,
            "reason": "retained for migration, recovery, compatibility, or project ownership",
        }
        for value in preserve_roots
        if value != ".codestable/wiki"
    ]
    return {
        "root": str(target_root),
        "mode": RUNTIME_MODE,
        "version": defaults.get("version"),
        "created": sorted(created),
        "updated": sorted(updated),
        "preserved": sorted(set(preserved)),
        "retired": sorted(retired_files),
        "runtime_contract": installed_contract,
        "runtime_source": "skill",
        "runtime_path": str(shared_runtime_path()),
        "project_data_preserved": True,
        "file_lifecycle": {
            "managed_versioned": sorted(managed),
            "project_owned_after_creation": sorted(seeds),
            "preserved_roots": preserve_roots,
            "automatic_backups": False,
            "upgrade_strategy": (
                "managed release files are updated in place; legacy knowledge stays in place "
                "for page-by-page audit"
            ),
            "generated_repair_command": (
                f"{sys.executable} {shared_runtime_path()} --root {target_root} reindex"
            ),
        },
        "layout": {
            "current": {
                "entry": current_entry,
                "runtime_source": "skill",
                "runtime": str(shared_runtime_path()),
                "schema_version": RUNTIME_SCHEMA,
            },
            "audited_history": {
                "entry": str((desired_config.get("wiki") or {}).get("history_entry") or ".codestable/wiki/HISTORY.md"),
                "task_notes": ".codestable/wiki/task-notes",
            },
            "preserved_not_for_normal_reads": preserved_noncurrent,
        },
        "agents_guidance": agents_guidance,
        "knowledge_migration": {
            "required": bool(legacy_pages),
            "status": migration_status,
            "legacy_roots": legacy_roots,
            "pages": legacy_pages,
            "source_pages_retained_in_place": True,
            "automatic_promotion": False,
            "automatic_removal": False,
        },
    }


def check_install(target_root: Path) -> dict[str, Any]:
    """Read-only compatibility check for project data and the shared Skill runtime."""
    source_root = asset_root()
    if not source_root.is_dir():
        raise RuntimeError(f"asset root not found: {source_root}")
    manifest = load_manifest(source_root)
    source_contract = distribution_contract()
    defaults_path = source_root / ".codestable" / "config.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    expected_version = str(defaults.get("version") or "")
    target_root = target_root.expanduser().resolve()
    target_config = target_root / ".codestable" / "config.json"
    compatibility_findings: list[dict[str, Any]] = []
    config: dict[str, Any] = {}
    if not target_config.is_file():
        compatibility_findings.append(
            {
                "code": "runtime.not-installed",
                "path": ".codestable/config.json",
                "detail": "CodeStable is not installed in this project",
            }
        )
    else:
        try:
            loaded = json.loads(target_config.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("config root is not an object")
            config = loaded
        except (json.JSONDecodeError, ValueError) as exc:
            compatibility_findings.append(
                {
                    "code": "runtime.config.invalid",
                    "path": ".codestable/config.json",
                    "detail": str(exc),
                }
            )
    if config:
        if config.get("mode") != RUNTIME_MODE:
            compatibility_findings.append(
                {
                    "code": "runtime.mode.incompatible",
                    "expected": RUNTIME_MODE,
                    "actual": config.get("mode"),
                }
            )
        raw_schema = config.get("schema_version")
        try:
            actual_schema: Any = int(raw_schema or 0)
        except (TypeError, ValueError):
            actual_schema = raw_schema
        if actual_schema != RUNTIME_SCHEMA:
            compatibility_findings.append(
                {
                    "code": "runtime.schema.incompatible",
                    "expected": RUNTIME_SCHEMA,
                    "actual": actual_schema,
                }
            )

    managed_mismatches: list[dict[str, str]] = []
    for relative in sorted(set(unique_strings(manifest.get("managed_files")))):
        source = source_root / relative
        target = target_root / relative
        if not target.is_file():
            managed_mismatches.append({"path": relative, "reason": "missing"})
        elif sha256_file(source) != sha256_file(target):
            managed_mismatches.append({"path": relative, "reason": "content-differs"})

    target_manifest_path = target_root / ".codestable" / "manifest.json"
    target_manifest: dict[str, Any] = {}
    target_manifest_error: str | None = None
    if target_manifest_path.is_file():
        try:
            loaded_manifest = json.loads(target_manifest_path.read_text(encoding="utf-8"))
            if not isinstance(loaded_manifest, dict):
                raise ValueError("manifest root is not an object")
            target_manifest = loaded_manifest
        except (json.JSONDecodeError, ValueError) as exc:
            target_manifest_error = str(exc)
    release_versions = {
        "skill": expected_version,
        "config": str(config.get("version") or "") if config else "",
        "version_file": (
            (target_root / ".codestable" / "VERSION").read_text(encoding="utf-8").strip()
            if (target_root / ".codestable" / "VERSION").is_file()
            else ""
        ),
        "manifest": str(target_manifest.get("version") or ""),
    }
    release_metadata = {
        "versions": release_versions,
        "aligned": all(value == expected_version for value in release_versions.values()),
        "compatibility_gate": False,
        "manifest_error": target_manifest_error,
    }
    retired_files_present = [
        relative
        for relative in sorted(set(unique_strings(manifest.get("retired_files"))))
        if (target_root / relative).is_file()
    ]

    runtime_contract = {
        **source_contract,
        "verification": "the shared Skill runtime passed every documented command's --help check",
    }
    compatible = not compatibility_findings and runtime_contract["ok"]
    project_doctor: dict[str, Any]
    if compatible:
        process = subprocess.run(
            [sys.executable, str(shared_runtime_path()), "--root", str(target_root), "doctor"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        try:
            parsed = json.loads(process.stdout)
            if not isinstance(parsed, dict):
                raise ValueError("doctor output root is not an object")
            project_doctor = {**parsed, "exit_code": process.returncode}
        except (json.JSONDecodeError, ValueError) as exc:
            project_doctor = {
                "ok": False,
                "error": f"shared-runtime doctor output could not be read: {exc}",
                "exit_code": process.returncode,
            }
    else:
        project_doctor = {
            "ok": False,
            "status": "not-run",
            "reason": "project data is not compatible with the shared runtime",
        }

    if not target_config.is_file():
        status = "not-installed"
        suggested_action = "install CodeStable from the current Skill"
        suggested_command = [sys.executable, str(Path(__file__).resolve()), "--root", str(target_root)]
    elif not compatible:
        status = "needs-upgrade"
        suggested_action = "upgrade the project data structure from the current Skill after reviewing this report"
        suggested_command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--root",
            str(target_root),
            "--upgrade",
        ]
    elif not project_doctor.get("ok"):
        status = "needs-attention"
        suggested_action = "review the project doctor findings; use reindex only for generated-index drift"
        suggested_command = []
    else:
        status = "current"
        suggested_action = "none"
        suggested_command = []
    return {
        "ok": compatible and bool(project_doctor.get("ok")),
        "read_only": True,
        "status": status,
        "root": str(target_root),
        "runtime_source": "skill",
        "runtime_path": str(shared_runtime_path()),
        "skill_version": expected_version,
        "project_version": config.get("version") if config else None,
        "schema_version": config.get("schema_version") if config else None,
        "managed_file_mismatches": managed_mismatches,
        "retired_files_present": retired_files_present,
        "release_metadata": release_metadata,
        "runtime_contract": runtime_contract,
        "compatibility_findings": compatibility_findings,
        "doctor": project_doctor,
        "suggested_action": suggested_action,
        "suggested_command": suggested_command,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="target project root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--upgrade",
        action="store_true",
        help="refresh shipped project files in place, retire legacy tools, and emit the semantic-audit inventory",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="read-only compatibility check of project data against the shared Skill runtime",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = check_install(Path(args.root)) if args.check else install(Path(args.root), upgrade=bool(args.upgrade))
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
