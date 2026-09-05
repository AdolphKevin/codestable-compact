#!/usr/bin/env python3
"""Create a current-format CodeStable knowledge base, or explicitly rebuild it.

Rebuild replaces only the selected project's .codestable directory. Old records
and configuration are not migrated. The Agent fills the fresh Wiki from current
source code, tests and accepted requirements after the empty layout is installed.
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
from pathlib import Path
from typing import Any, Sequence

RUNTIME_MODE = "knowledge_wiki"
RUNTIME_SCHEMA = 4
DEFAULT_CURRENT_ENTRY = ".codestable/wiki/INDEX.md"
ENTRY_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9_./-])((?:\./)?\.codestable/(?:wiki|model|knowledge)/[A-Za-z0-9_.\-/]+\.md)")
SKILL_COMMAND_PATTERN = re.compile(r"\|\s*`\$cs\s+([^`]+)`\s*\|")
RUNTIME_COMMAND_PATTERN = re.compile(r"cs_knowledge\.py(?:\s+--root\s+\S+)?\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?")
SKILL_ONLY_COMMANDS = {"init", "rebuild"}
_COMMAND_CONTRACT_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def agents_entry_check(target_root: Path, current_entry: str, retired_roots: Sequence[str] = (".codestable/model", ".codestable/knowledge")) -> dict[str, Any]:
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
                if any(value == root or value.startswith(root.rstrip("/") + "/") for root in retired_roots):
                    findings.append(
                        {
                            "code": "agents.entry.retired",
                            **reference,
                            "detail": f"AGENTS.md points to a retired knowledge entry: {value}",
                            "action": f"use {current_entry}; rebuild knowledge from current source and tests",
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


def source_assets() -> tuple[dict[str, Path], dict[str, Any]]:
    source = asset_root()
    manifest = load_manifest(source)
    declared = set(unique_strings(manifest.get('managed_files'))) | set(unique_strings(manifest.get('seed_files'))) | {'.codestable/config.json'}
    files = {}
    for path in sorted(source.rglob('*')):
        if '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        if path.is_symlink():
            raise RuntimeError(f'asset must not be a symlink: {path}')
        if path.is_file():
            files[path.relative_to(source).as_posix()] = path
    if set(files) != declared or any(not name.startswith('.codestable/') or '..' in Path(name).parts for name in declared):
        raise RuntimeError('asset manifest does not match the complete .codestable file set')
    defaults = json.loads(files['.codestable/config.json'].read_text(encoding='utf-8'))
    if defaults.get('schema_version') != RUNTIME_SCHEMA or defaults.get('mode') != RUNTIME_MODE or defaults.get('wiki', {}).get('index_storage') != 'local':
        raise RuntimeError('asset configuration does not use the current knowledge format')
    return files, defaults


def knowledge_inventory(target: Path) -> list[dict[str, Any]]:
    if target.is_symlink():
        raise ValueError('.codestable must not be a symlink; rebuild only a real project directory')
    if target.exists() and not target.is_dir():
        raise ValueError('.codestable must be a directory')
    entries = []
    for path in sorted(target.rglob('*')):
        item: dict[str, Any] = {'path': path.relative_to(target.parent).as_posix()}
        if path.is_symlink():
            item.update(type='symlink', target=os.readlink(path))
        elif path.is_file():
            item.update(type='file', sha256=sha256_file(path), bytes=path.stat().st_size)
        elif path.is_dir():
            item['type'] = 'directory'
        else:
            raise ValueError(f'unsupported file in knowledge directory: {path}')
        entries.append(item)
    return entries


def rebuild_plan(root: Path, files: dict[str, Path]) -> dict[str, Any]:
    entries = knowledge_inventory(root / '.codestable')
    binding = {
        'root': str(root),
        'entries': entries,
        'assets': {name: sha256_file(path) for name, path in files.items()},
        'runtime': sha256_file(shared_runtime_path()),
        'skill': sha256_file(skill_document_path()),
    }
    token = hashlib.sha256(json.dumps(binding, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        'target': str(root / '.codestable'),
        'removed': [item['path'] for item in entries if item['type'] != 'directory'],
        'created': sorted(files),
        'plan_token': token,
    }


def run_doctor(root: Path) -> dict[str, Any]:
    process = subprocess.run([sys.executable, str(shared_runtime_path()), '--root', str(root), 'doctor'], text=True, capture_output=True, check=False, timeout=30)
    try:
        value = json.loads(process.stdout)
        if not isinstance(value, dict):
            raise ValueError('doctor output must be an object')
        return {**value, 'exit_code': process.returncode}
    except (ValueError, json.JSONDecodeError) as exc:
        return {'ok': False, 'error': f'cannot read shared-runtime doctor: {exc}', 'exit_code': process.returncode}


def install(target_root: Path, rebuild: bool = False, dry_run: bool = False, plan_token: str | None = None) -> dict[str, Any]:
    root = target_root.expanduser().resolve()
    target = root / '.codestable'
    files, defaults = source_assets()
    contract = distribution_contract()
    plan = rebuild_plan(root, files)
    if (target / 'wiki/.write.lock').exists():
        raise RuntimeError('knowledge writer is active; finish the write before rebuilding')
    if target.exists() and any(target.iterdir()) and not rebuild:
        raise ValueError('.codestable already exists; use an explicitly authorized --rebuild')
    if plan_token and not rebuild:
        raise ValueError('--plan-token is only used with --rebuild')
    result = {
        'root': str(root), 'mode': RUNTIME_MODE, 'version': defaults['version'],
        'rebuild': rebuild, 'dry_run': dry_run, **plan,
        'runtime_source': 'skill', 'runtime_path': str(shared_runtime_path()), 'runtime_contract': contract,
        'knowledge_build': {'required': True, 'complete': False, 'source': 'current-code-tests-requirements'},
        'file_lifecycle': {'automatic_backups': False, 'replacement_scope': '.codestable'},
    }
    if dry_run:
        return result
    if rebuild and plan_token != plan['plan_token']:
        raise ValueError('rebuild requires the current --dry-run plan token; preview again before applying')
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.codestable-new-', dir=root) as temporary:
        staged_root = Path(temporary)
        for relative, source in files.items():
            copy_file(source, staged_root / relative)
        doctor = run_doctor(staged_root)
        if not doctor.get('ok'):
            raise RuntimeError(f'new knowledge layout failed validation: {json_dump(doctor)}')
        if rebuild_plan(root, files)['plan_token'] != plan['plan_token']:
            raise RuntimeError('knowledge or release files changed during preparation; preview again')
        if target.exists():
            shutil.rmtree(target)
        os.replace(staged_root / '.codestable', target)
    result['plan_token'] = None
    result['agents_guidance'] = agents_entry_check(root, DEFAULT_CURRENT_ENTRY)
    result['layout'] = {'current': {'entry': DEFAULT_CURRENT_ENTRY, 'schema_version': RUNTIME_SCHEMA, 'runtime_source': 'skill'}}
    return result


def check_install(target_root: Path) -> dict[str, Any]:
    """Inspect current-format data without migrating or writing it."""
    root = target_root.expanduser().resolve()
    files, defaults = source_assets()
    contract = distribution_contract()
    target = root / '.codestable'
    findings = []
    config: dict[str, Any] = {}
    if target.is_symlink():
        findings.append({'code': 'runtime.directory.symlink', 'detail': '.codestable must be a real directory'})
    elif (target / 'config.json').is_file():
        try:
            config = json.loads((target / 'config.json').read_text(encoding='utf-8'))
            if not isinstance(config, dict):
                raise ValueError('configuration must be an object')
            if config.get('schema_version') != RUNTIME_SCHEMA or config.get('mode') != RUNTIME_MODE or config.get('wiki', {}).get('index_storage') != 'local':
                findings.append({'code': 'runtime.format.unsupported', 'detail': 'old project data must be rebuilt from current source and tests'})
        except (ValueError, AttributeError) as exc:
            config = {}
            findings.append({'code': 'runtime.config.invalid', 'detail': str(exc)})
    else:
        findings.append({'code': 'runtime.config.missing', 'detail': 'current-format configuration is missing'})
    doctor = run_doctor(root) if not findings else {'ok': False, 'status': 'not-run'}
    empty = not target.exists() or (target.is_dir() and not target.is_symlink() and not any(target.iterdir()))
    status = 'not-installed' if empty else 'needs-rebuild' if findings else 'current' if doctor.get('ok') else 'needs-attention'
    command = [sys.executable, str(Path(__file__).resolve()), '--root', str(root)]
    suggested = command if empty else command + ['--rebuild', '--dry-run'] if findings else []
    mismatches = [{'path': name, 'reason': 'missing-or-different'} for name in unique_strings(load_manifest(asset_root()).get('managed_files')) if not (root / name).is_file() or sha256_file(root / name) != sha256_file(files[name])]
    return {
        'ok': status == 'current', 'read_only': True, 'status': status, 'root': str(root),
        'runtime_source': 'skill', 'runtime_path': str(shared_runtime_path()), 'runtime_contract': contract,
        'skill_version': defaults['version'], 'project_version': config.get('version'), 'schema_version': config.get('schema_version'),
        'format_findings': findings, 'managed_file_mismatches': mismatches, 'doctor': doctor,
        'suggested_action': 'initialize the knowledge base' if empty else 'rebuild after explicit user authorization' if findings else 'review doctor findings' if not doctor.get('ok') else 'none',
        'suggested_command': suggested,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='target project root')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--rebuild', action='store_true', help='replace this project\'s .codestable with a fresh layout; requires a preview token')
    mode.add_argument('--check', action='store_true', help='read-only current-format and structure check')
    parser.add_argument('--dry-run', action='store_true', help='preview the full file replacement without writes')
    parser.add_argument('--plan-token', help='apply the exact authorized rebuild preview')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check and (args.dry_run or args.plan_token):
        parser.error('--check cannot be combined with --dry-run or --plan-token')
    try:
        result = check_install(Path(args.root)) if args.check else install(Path(args.root), rebuild=args.rebuild, dry_run=args.dry_run, plan_token=args.plan_token)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json_dump({'ok': False, 'error': str(exc)}), end='')
        return 2
    print(json_dump({'ok': True, **result}), end='')
    return 0 if result.get('ok', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
