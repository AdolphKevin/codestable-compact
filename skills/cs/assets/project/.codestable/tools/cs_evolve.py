#!/usr/bin/env python3
"""Manual, evidence-selected CodeStable Harness evolution control plane.

Normal `/cs` work never calls this tool. A maintainer explicitly selects
finished observations, records a diagnosis, proposes a bounded overlay, imports
an externally authenticated evaluation through cs_eval.py, and applies the policy-scoped owner or Agent checkpoint before promotion.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cs_eval  # type: ignore  # local project tool
import cs_observe  # type: ignore  # local project tool
import cs_policy  # type: ignore  # local project tool

SCHEMA_VERSION = 3
DIAGNOSIS_CLASSES = (
    "harness",
    "project_knowledge",
    "product_code",
    "model_variance",
    "environment",
    "insufficient_evidence",
)

DEFAULT_MANIFEST: dict[str, Any] = {'description': 'First-class, fixture-covered CodeStable policy surfaces.',
 'editable_surfaces': [{'component': 'routing',
                        'default_owner_checkpoint': True,
                        'id': 'routing-policy',
                        'path': '.codestable/reference/routing.md',
                        'promotion': 'owner_checkpoint',
                        'risk': 'medium'},
                       {'component': 'context',
                        'default_owner_checkpoint': True,
                        'id': 'retrieval-policy',
                        'path': '.codestable/reference/retrieval.md',
                        'promotion': 'owner_checkpoint',
                        'risk': 'medium'},
                       {'component': 'policy',
                        'default_owner_checkpoint': False,
                        'id': 'minimality-policy',
                        'path': '.codestable/reference/minimality.md',
                        'promotion': 'agent_after_evidence',
                        'risk': 'low'},
                       {'component': 'memory',
                        'default_owner_checkpoint': False,
                        'id': 'learned-playbook',
                        'path': '.codestable/harness/playbook.jsonl',
                        'promotion': 'agent_after_evidence',
                        'risk': 'low'},
                       {'component': 'control',
                        'default_owner_checkpoint': True,
                        'id': 'control-policy',
                        'path': '.codestable/reference/control-plane.md',
                        'promotion': 'owner_checkpoint',
                        'risk': 'high'},
                       {'component': 'gate',
                        'default_owner_checkpoint': True,
                        'id': 'gate-policy',
                        'path': '.codestable/reference/gates.md',
                        'promotion': 'owner_checkpoint',
                        'risk': 'high'},
                       {'component': 'state',
                        'default_owner_checkpoint': True,
                        'id': 'artifact-schema',
                        'path': '.codestable/reference/artifact-schema.md',
                        'promotion': 'owner_checkpoint',
                        'risk': 'high'},
                       {'component': 'tool',
                        'default_owner_checkpoint': True,
                        'id': 'context-tool',
                        'path': '.codestable/tools/cs_context.py',
                        'promotion': 'owner_checkpoint',
                        'risk': 'high'},
                       {'component': 'interaction',
                        'default_owner_checkpoint': False,
                        'id': 'interaction-copy',
                        'path': '.codestable/harness/policies/interaction-copy.md',
                        'promotion': 'agent_after_evidence',
                        'risk': 'low'}],
 'harness_id': 'codestable-compact',
 'promotion_policy': 'owner_checkpoint_by_policy',
 'protected_paths': ['.codestable/config.json',
                     '.codestable/reference/evolution.md',
                     '.codestable/tools/cs_harness.py',
                     '.codestable/tools/cs_observe.py',
                     '.codestable/tools/cs_evolve.py',
                     '.codestable/tools/cs_eval.py',
                     '.codestable/evals/**',
                     '.codestable/evolution/**',
                     '.codestable/observations/**',
                     '.codestable/harness/manifest.json',
                     '.codestable/harness/registry.json',
                     '.codestable/harness/versions/**',
                     '.codestable/tools/cs_policy.py',
                     '.codestable/tools/cs_feedback.py',
                     '.codestable/tools/cs_meta.py',
                     '.codestable/meta/**',
                     '.codestable/tools/cs_fixture.py'],
 'schema_version': 3}

DEFAULT_REGISTRY: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "harness_id": "codestable-compact",
    "active_version": "seed",
    "next_sequence": 1,
    "versions": [],
    "events": [],
}


class EvolutionError(RuntimeError):
    """An evolution boundary or state invariant was violated."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_json(data: Any) -> bytes:
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=str(destination.parent))
    os.close(fd)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvolutionError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvolutionError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvolutionError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json_dump(data))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_id(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-._")
    if not result:
        raise EvolutionError("identifier cannot be empty")
    return result[:96]


def normalize_relative(value: str) -> str:
    raw = value.replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise EvolutionError(f"path must be a safe project-relative path: {value!r}")
    return path.as_posix()


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.exists():
            raise EvolutionError(f"project root does not exist: {root}")
        return root
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".codestable").is_dir() or (candidate / ".git").exists():
            return candidate
    return current


def cs_dir(root: Path) -> Path:
    return root / ".codestable"


def case_dir(root: Path, case_id: str, *, require: bool = True) -> Path:
    path = cs_dir(root) / "evolution" / "cases" / normalize_id(case_id)
    if require and not path.is_dir():
        raise EvolutionError(f"unknown evolution case: {case_id}")
    return path


def init_runtime(root: Path) -> dict[str, Any]:
    cs = cs_dir(root)
    directories = [
        cs / "harness" / "versions",
        cs / "evolution" / "cases",
        cs / "evolution" / "rejected",
        cs / "evals" / "public",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    cs_observe.init_runtime(root)

    defaults = {
        cs / "harness" / "manifest.json": DEFAULT_MANIFEST,
        cs / "harness" / "registry.json": DEFAULT_REGISTRY,
    }
    created: list[str] = []
    preserved: list[str] = []
    for path, value in defaults.items():
        if path.exists():
            preserved.append(path.relative_to(root).as_posix())
        else:
            write_json(path, value)
            created.append(path.relative_to(root).as_posix())
    playbook = cs / "harness" / "playbook.jsonl"
    if playbook.exists():
        preserved.append(playbook.relative_to(root).as_posix())
    else:
        atomic_write(playbook, "")
        created.append(playbook.relative_to(root).as_posix())

    load_manifest(root)
    registry = load_registry(root)
    if not any(item.get("id") == registry.get("active_version") for item in registry.get("versions", [])):
        snapshot_version(
            root,
            str(registry.get("active_version") or "seed"),
            metadata={"origin": "initial-or-migrated-runtime"},
        )
    return {"root": str(root), "created": created, "preserved": preserved}


def load_manifest(root: Path) -> dict[str, Any]:
    manifest = read_json(cs_dir(root) / "harness" / "manifest.json")
    if manifest.get("promotion_policy") != "owner_checkpoint_by_policy":
        raise EvolutionError("harness manifest must use owner_checkpoint_by_policy")
    surfaces = manifest.get("editable_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise EvolutionError("harness manifest has no editable surfaces")
    protected = [normalize_relative(str(item).replace("/**", "/__glob__")) .replace("/__glob__", "/**") for item in manifest.get("protected_paths", [])]
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for surface in surfaces:
        if not isinstance(surface, dict):
            raise EvolutionError("each editable surface must be an object")
        surface_id = str(surface.get("id") or "")
        path = normalize_relative(str(surface.get("path") or ""))
        if not surface_id or surface_id in seen_ids:
            raise EvolutionError(f"invalid or duplicate surface id: {surface_id!r}")
        if path in seen_paths:
            raise EvolutionError(f"duplicate editable surface path: {path}")
        promotion = surface.get("promotion")
        if promotion not in {"owner_checkpoint", "agent_after_evidence"}:
            raise EvolutionError(f"invalid surface promotion authority: {surface_id}")
        owner = surface.get("default_owner_checkpoint")
        if not isinstance(owner, bool):
            raise EvolutionError(f"surface lacks default_owner_checkpoint: {surface_id}")
        if (promotion == "owner_checkpoint") != owner:
            raise EvolutionError(f"surface promotion and owner checkpoint disagree: {surface_id}")
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in protected):
            raise EvolutionError(f"editable surface overlaps a protected path: {path}")
        seen_ids.add(surface_id)
        seen_paths.add(path)
    try:
        audit = cs_policy.audit_policies(root)
    except cs_policy.PolicyError as exc:
        raise EvolutionError(str(exc)) from exc
    if not audit.get("ok"):
        raise EvolutionError("Harness policy registry/fixture audit is not clean")
    return manifest


def surface_map(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for surface in load_manifest(root)["editable_surfaces"]:
        copied = dict(surface)
        copied["path"] = normalize_relative(str(copied["path"]))
        result[str(copied["id"])] = copied
    return result


def load_registry(root: Path) -> dict[str, Any]:
    registry = read_json(cs_dir(root) / "harness" / "registry.json")
    registry.setdefault("versions", [])
    registry.setdefault("events", [])
    registry.setdefault("next_sequence", 1)
    return registry


def save_registry(root: Path, registry: dict[str, Any]) -> None:
    write_json(cs_dir(root) / "harness" / "registry.json", registry)


def live_surface_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    surfaces = sorted(surface_map(root).values(), key=lambda item: str(item["path"]))
    for surface in surfaces:
        relative = surface["path"]
        source = root / relative
        if not source.is_file():
            raise EvolutionError(f"missing editable surface: {relative}")
        records.append({
            "surface_id": surface["id"],
            "path": relative,
            "sha256": sha256_file(source),
        })
    return records


def live_harness_content_sha256(root: Path) -> str:
    return sha256_bytes(canonical_json(live_surface_records(root)))


def validate_version_snapshot(
    root: Path,
    version_id: str,
    *,
    registry_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identifier = normalize_id(version_id)
    directory = cs_dir(root) / "harness" / "versions" / identifier
    manifest = read_json(directory / "version.json")
    if manifest.get("id") != identifier:
        raise EvolutionError(f"version snapshot id mismatch: {identifier}")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise EvolutionError(f"version snapshot has no files: {identifier}")
    seen: set[str] = set()
    clean_records: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise EvolutionError(f"version snapshot has invalid file record: {identifier}")
        relative = normalize_relative(str(record.get("path") or ""))
        if relative in seen:
            raise EvolutionError(f"version snapshot contains duplicate path: {relative}")
        source = directory / "files" / relative
        if not source.is_file() or source.is_symlink() or sha256_file(source) != record.get("sha256"):
            raise EvolutionError(f"version snapshot is incomplete or modified: {relative}")
        clean_records.append({
            "surface_id": record.get("surface_id"),
            "path": relative,
            "sha256": record.get("sha256"),
        })
        seen.add(relative)
    expected_content = sha256_bytes(canonical_json(clean_records))
    if manifest.get("content_sha256") != expected_content:
        raise EvolutionError(f"version snapshot content hash is invalid: {identifier}")
    if registry_entry is not None:
        if registry_entry.get("content_sha256") != expected_content:
            raise EvolutionError(f"version registry content hash disagrees with snapshot: {identifier}")
        if registry_entry.get("files") != records:
            raise EvolutionError(f"version registry file list disagrees with snapshot: {identifier}")
    return manifest


def snapshot_version(root: Path, version_id: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    identifier = normalize_id(version_id)
    registry = load_registry(root)
    existing = next((item for item in registry.get("versions", []) if item.get("id") == identifier), None)
    if existing is not None:
        validate_version_snapshot(root, identifier, registry_entry=existing)
        return existing
    directory = cs_dir(root) / "harness" / "versions" / identifier
    if directory.exists():
        raise EvolutionError(f"version directory exists without registry entry: {identifier}")
    files_root = directory / "files"
    records = live_surface_records(root)
    for record in records:
        relative = record["path"]
        source = root / relative
        destination = files_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    entry = {
        "id": identifier,
        "created_at": now_iso(),
        "files": records,
        "content_sha256": sha256_bytes(canonical_json(records)),
        "metadata": metadata or {},
    }
    write_json(directory / "version.json", entry)
    registry.setdefault("versions", []).append(entry)
    save_registry(root, registry)
    return entry


def restore_version(root: Path, version_id: str) -> dict[str, Any]:
    identifier = normalize_id(version_id)
    registry = load_registry(root)
    entry = next((item for item in registry.get("versions", []) if item.get("id") == identifier), None)
    if entry is None:
        raise EvolutionError(f"unknown Harness version snapshot: {identifier}")
    manifest = validate_version_snapshot(root, identifier, registry_entry=entry)
    directory = cs_dir(root) / "harness" / "versions" / identifier
    for record in manifest.get("files", []):
        relative = normalize_relative(str(record.get("path") or ""))
        atomic_copy(directory / "files" / relative, root / relative)
    return manifest


def selected_runs_for_signal(root: Path, signal: str, *, limit: int) -> list[str]:
    payload = cs_observe.list_observations(
        root,
        states=("flagged",),
        signal=signal,
        limit=limit,
    )
    return [str(item["run_id"]) for item in payload["observations"]]


def build_evidence(root: Path, run_ids: Sequence[str]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    identities: set[tuple[str, str | None]] = set()
    signal_counts: dict[str, int] = {}
    validation_counts: dict[str, int] = {}
    for run_id in run_ids:
        item = cs_observe.load_observation(root, run_id)
        meta = item["meta"]
        outcome = item["outcome"]
        if meta.get("status") != "finished" or not isinstance(outcome, dict):
            raise EvolutionError(f"only finished observations can become evidence: {run_id}")
        harness = meta.get("harness") if isinstance(meta.get("harness"), dict) else {}
        version = str(harness.get("version") or "unknown")
        content_sha256 = str(harness.get("content_sha256") or "") or None
        identities.add((version, content_sha256))
        signals = [str(value) for value in meta.get("signals") or []]
        for signal in signals:
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
        validation = str((outcome.get("task_validation") or {}).get("status") or "not_run")
        validation_counts[validation] = validation_counts.get(validation, 0) + 1
        records.append({
            "run_id": meta.get("run_id"),
            "work_id": meta.get("work_id"),
            "kind": meta.get("kind"),
            "route": meta.get("route"),
            "harness_version": version,
            "harness_content_sha256": content_sha256,
            "harness_drift_detected": bool(harness.get("drift_detected")),
            "outcome": outcome.get("status"),
            "validation_status": validation,
            "signals": signals,
            "metrics": outcome.get("metrics") or {},
            "events_sha256": cs_observe.sha256_file(item["directory"] / "events.jsonl"),
            "observation_path": item["directory"].relative_to(root).as_posix(),
        })
    if len(identities) != 1:
        raise EvolutionError(
            "selected observations must share one exact baseline Harness version/content identity; "
            "create separate cases when the Harness drifted or changed"
        )
    baseline_version, baseline_content_sha256 = next(iter(identities))
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_version": baseline_version,
        "baseline_content_sha256": baseline_content_sha256,
        "run_count": len(records),
        "signal_counts": dict(sorted(signal_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
        "validation_counts": dict(sorted(validation_counts.items())),
        "runs": records,
        "generated_at": now_iso(),
    }


def create_case(
    root: Path,
    *,
    title: str,
    run_ids: Sequence[str] = (),
    signal: str | None = None,
    signal_limit: int = 20,
    case_id: str | None = None,
) -> dict[str, Any]:
    init_runtime(root)
    selected = list(dict.fromkeys(run_ids))
    if signal:
        selected.extend(run for run in selected_runs_for_signal(root, signal, limit=signal_limit) if run not in selected)
    if not selected:
        raise EvolutionError("an evolution case requires explicit run ids or a flagged signal with matches")
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    identifier = normalize_id(case_id or f"case-{timestamp}-{title}")
    directory = case_dir(root, identifier, require=False)
    if directory.exists():
        raise EvolutionError(f"evolution case already exists: {identifier}")
    (directory / "candidates").mkdir(parents=True)
    (directory / "evaluations").mkdir(parents=True)
    evidence = build_evidence(root, selected)
    for run_id in selected:
        cs_observe.select_observation(root, run_id, case_id=identifier)
    case = {
        "schema_version": SCHEMA_VERSION,
        "case_id": identifier,
        "title": title,
        "status": "selected",
        "stage": "diagnose",
        "baseline_version": evidence["baseline_version"],
        "baseline_content_sha256": evidence["baseline_content_sha256"],
        "selected_run_ids": selected,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "diagnosis": None,
        "candidates": [],
        "promoted_version": None,
    }
    write_json(directory / "case.json", case)
    write_json(directory / "evidence.json", evidence)
    append_jsonl(cs_dir(root) / "evolution" / "index.jsonl", {
        "timestamp": now_iso(), "action": "case_created", "case_id": identifier, "run_ids": selected
    })
    return {"case": case, "evidence": evidence}


def record_diagnosis(
    root: Path,
    *,
    case_id: str,
    classification: str,
    summary: str,
    mechanism: str | None = None,
    surface_id: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    directory = case_dir(root, case_id)
    case = read_json(directory / "case.json")
    normalized = classification.strip().casefold()
    if normalized not in DIAGNOSIS_CLASSES:
        raise EvolutionError(f"invalid diagnosis classification: {classification}")
    diagnosis: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "classification": normalized,
        "summary": summary.strip(),
        "mechanism": mechanism.strip() if mechanism else None,
        "surface_id": surface_id.strip() if surface_id else None,
        "confidence": confidence,
        "recorded_at": now_iso(),
    }
    if not diagnosis["summary"]:
        raise EvolutionError("diagnosis summary is required")
    if normalized == "harness":
        surfaces = surface_map(root)
        if not diagnosis["mechanism"]:
            raise EvolutionError("Harness diagnosis requires a named mechanism")
        if diagnosis["surface_id"] not in surfaces:
            raise EvolutionError("Harness diagnosis must map to one declared editable surface")
        if confidence is None or not 0.0 <= confidence <= 1.0:
            raise EvolutionError("Harness diagnosis confidence must be between 0 and 1")
        case["status"] = "diagnosed"
        case["stage"] = "proposal"
    else:
        case["status"] = "closed_without_harness_change"
        case["stage"] = "closed"
    case["diagnosis"] = diagnosis
    case["updated_at"] = now_iso()
    write_json(directory / "diagnosis.json", diagnosis)
    write_json(directory / "case.json", case)
    return {"case": case, "diagnosis": diagnosis}


def overlay_files(overlay: Path) -> list[str]:
    if not overlay.is_dir():
        raise EvolutionError(f"overlay directory not found: {overlay}")
    result: list[str] = []
    for path in sorted(overlay.rglob("*")):
        if path.is_file() and not any(part.startswith(".") and part != ".codestable" for part in path.relative_to(overlay).parts):
            result.append(path.relative_to(overlay).as_posix())
    return result


def add_candidate(
    root: Path,
    case_id: str,
    *,
    candidate_id: str,
    title: str,
    surface_ids: Sequence[str],
    overlay: Path,
    expected_effect: str,
    regression_risks: Sequence[str] = (),
    proposal_metadata: dict[str, Any] | None = None,
    proposal_file: Path | None = None,
    variant_file: Path | None = None,
) -> dict[str, Any]:
    directory = case_dir(root, case_id)
    case = read_json(directory / "case.json")
    diagnosis = case.get("diagnosis")
    if not isinstance(diagnosis, dict) or diagnosis.get("classification") != "harness":
        raise EvolutionError("candidate proposals require a recorded Harness diagnosis")
    if case.get("baseline_version") != load_registry(root).get("active_version"):
        raise EvolutionError("case baseline is no longer active; create a new case or explicitly roll back")
    baseline_content = case.get("baseline_content_sha256")
    if not baseline_content:
        raise EvolutionError(
            "selected observations do not contain an exact Harness content hash; "
            "collect a fresh observation before proposing a candidate"
        )
    if live_harness_content_sha256(root) != baseline_content:
        raise EvolutionError("live Harness content drifted after the selected observations; create a fresh case")
    if not isinstance(proposal_metadata, dict):
        raise EvolutionError("v0.4 candidates require an agent-authored Meta proposal manifest")
    if proposal_file is None or variant_file is None:
        raise EvolutionError("candidate requires locked proposal and variant documents")
    proposal_file = proposal_file.expanduser().resolve()
    variant_file = variant_file.expanduser().resolve()
    if not proposal_file.is_file() or not variant_file.is_file():
        raise EvolutionError("proposal or variant document is missing")

    try:
        requirements = cs_policy.proposal_requirements(
            root,
            policy_ids=[str(value) for value in proposal_metadata.get("policy_ids") or []],
            change_type=str(proposal_metadata.get("change_type") or ""),
            fixture_ids=[str(value) for value in proposal_metadata.get("fixture_ids") or []],
        )
    except cs_policy.PolicyError as exc:
        raise EvolutionError(str(exc)) from exc
    selected_ids = list(dict.fromkeys(surface_ids))
    if set(selected_ids) != set(requirements["surface_ids"]):
        raise EvolutionError("candidate surfaces do not match the first-class policy proposal")
    if diagnosis.get("surface_id") not in selected_ids:
        raise EvolutionError("candidate must include the surface named by the diagnosis")
    for field in ("policy_registry_sha256", "fixture_index_sha256"):
        if proposal_metadata.get(field) != requirements[field]:
            raise EvolutionError(f"proposal policy evidence is stale or mismatched: {field}")
    if bool(proposal_metadata.get("owner_checkpoint_required")) != bool(requirements["owner_checkpoint_required"]):
        raise EvolutionError("proposal cannot choose its own owner-checkpoint authority")
    if proposal_metadata.get("promotion_authority") != requirements["promotion_authority"]:
        raise EvolutionError("proposal promotion authority does not match policy rules")
    if proposal_metadata.get("proposal_sha256") != sha256_file(proposal_file):
        raise EvolutionError("proposal document hash does not match the registered proposal")
    if proposal_metadata.get("variant_sha256") != sha256_file(variant_file):
        raise EvolutionError("variant document hash does not match the registered proposal")

    surfaces = surface_map(root)
    expected_paths = {surfaces[surface_id]["path"] for surface_id in selected_ids}
    actual_paths = set(overlay_files(overlay))
    if actual_paths != expected_paths:
        extra = sorted(actual_paths - expected_paths)
        missing = sorted(expected_paths - actual_paths)
        raise EvolutionError(f"overlay must contain exactly the declared surface files; extra={extra}, missing={missing}")

    identifier = normalize_id(candidate_id)
    candidate_root = directory / "candidates" / identifier
    if candidate_root.exists():
        raise EvolutionError(f"candidate already exists: {identifier}")
    copied_root = candidate_root / "overlay"
    changes: list[dict[str, Any]] = []
    for surface_id in selected_ids:
        surface = surfaces[surface_id]
        relative = surface["path"]
        baseline = root / relative
        candidate_source = overlay / relative
        if not baseline.is_file() or not candidate_source.is_file():
            raise EvolutionError(f"candidate surface file is missing: {relative}")
        destination = copied_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate_source, destination)
        changes.append({
            "surface_id": surface_id,
            "path": relative,
            "risk": surface.get("risk"),
            "base_sha256": sha256_file(baseline),
            "candidate_sha256": sha256_file(candidate_source),
        })
    evidence_dir = candidate_root / "proposal"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    atomic_copy(proposal_file, evidence_dir / "proposal.json")
    atomic_copy(variant_file, evidence_dir / "variant.md")
    content_hash = sha256_bytes(canonical_json(changes))
    meta = {
        **proposal_metadata,
        "policy_ids": requirements["policy_ids"],
        "fixture_ids": requirements["fixture_ids"],
        "change_type": requirements["change_type"],
        "surface_ids": requirements["surface_ids"],
        "coverage": requirements["coverage"],
        "owner_checkpoint_required": requirements["owner_checkpoint_required"],
        "promotion_authority": requirements["promotion_authority"],
        "proposal_path": (evidence_dir / "proposal.json").relative_to(root).as_posix(),
        "variant_path": (evidence_dir / "variant.md").relative_to(root).as_posix(),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": identifier,
        "case_id": normalize_id(case_id),
        "title": title,
        "status": "proposed",
        "parent_version": case["baseline_version"],
        "parent_content_sha256": case["baseline_content_sha256"],
        "target_mechanism": diagnosis.get("mechanism"),
        "expected_effect": expected_effect,
        "regression_risks": list(regression_risks),
        "changes": changes,
        "candidate_content_sha256": content_hash,
        "promotion_gate_required": bool(requirements["owner_checkpoint_required"]),
        "promotion_authority": requirements["promotion_authority"],
        "meta": meta,
        "created_at": now_iso(),
    }
    write_json(candidate_root / "manifest.json", manifest)
    case.setdefault("candidates", []).append(identifier)
    case["status"] = "candidate_proposed"
    case["stage"] = "validity_prepass"
    case["updated_at"] = now_iso()
    write_json(directory / "case.json", case)
    cs_policy.strategy_event(root, event_type="candidate_proposed", payload={
        "case_id": normalize_id(case_id),
        "candidate_id": identifier,
        "policy_ids": requirements["policy_ids"],
        "fixture_ids": requirements["fixture_ids"],
        "change_type": requirements["change_type"],
        "promotion_authority": requirements["promotion_authority"],
        "proposal_sha256": proposal_metadata["proposal_sha256"],
    })
    return manifest


def metric_no_regression(
    protocol: dict[str, Any],
    split: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    promotion = protocol.get("promotion", {})
    limits = promotion.get("metric_regression_limits", {})
    lower = set(promotion.get("lower_is_better_metrics", []))
    reasons: list[str] = []
    baseline_metrics = baseline.get("metrics") or {}
    candidate_metrics = candidate.get("metrics") or {}
    for name, limit_value in limits.items():
        if name not in baseline_metrics or name not in candidate_metrics:
            reasons.append(f"{split}.{name} required metric is missing")
            continue
        base = float(baseline_metrics[name])
        cand = float(candidate_metrics[name])
        limit = float(limit_value)
        if name in lower:
            allowed = base * (1.0 + limit) if base != 0 else limit
            if cand > allowed + 1e-12:
                reasons.append(f"{split}.{name} regressed: {cand} > {allowed}")
        else:
            allowed = base * (1.0 - limit) if base != 0 else -limit
            if cand < allowed - 1e-12:
                reasons.append(f"{split}.{name} regressed: {cand} < {allowed}")
    return reasons


def decide_candidate(root: Path, case_id: str, candidate_id: str) -> dict[str, Any]:
    directory = case_dir(root, case_id)
    case = read_json(directory / "case.json")
    candidate_root = directory / "candidates" / normalize_id(candidate_id)
    manifest = read_json(candidate_root / "manifest.json")
    metadata = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    validity = metadata.get("validity") if isinstance(metadata.get("validity"), dict) else {}
    if validity.get("status") != "pass":
        raise EvolutionError("candidate cannot be decided before a measured validity pre-pass")
    validity_path = root / str(validity.get("path") or "")
    if not validity_path.is_file() or sha256_file(validity_path) != validity.get("sha256"):
        raise EvolutionError("candidate validity pre-pass evidence is missing or changed")
    try:
        local_lock = cs_eval.verify_local_candidate_lock(root, case_id, candidate_id)
        challenge = cs_eval.load_challenge(root, case_id, candidate_id)
        result = cs_eval.load_verified_result(root, case_id, candidate_id)
        protocol = cs_eval.load_protocol(root)
    except cs_eval.EvaluationError as exc:
        raise EvolutionError(str(exc)) from exc
    required = list(protocol["required_splits"])
    promotion = protocol.get("promotion", {})
    allowed_regression = float(promotion.get("allowed_pass_regression", 0.0))
    minimum_delta = float(promotion.get("minimum_pass_delta", 0.0))
    require_improvement = bool(promotion.get("require_improvement_on_any_split", True))
    reasons: list[str] = []
    improvements: list[str] = []
    split_summary: dict[str, Any] = {}
    for split in required:
        item = result["splits"][split]
        baseline = item["baseline"]
        candidate = item["candidate"]
        baseline_rate = baseline["pass_count"] / baseline["total"]
        candidate_rate = candidate["pass_count"] / candidate["total"]
        delta = candidate_rate - baseline_rate
        split_summary[split] = {
            "baseline_pass_rate": baseline_rate,
            "candidate_pass_rate": candidate_rate,
            "delta": delta,
        }
        if delta < -allowed_regression - 1e-12:
            reasons.append(f"{split} pass rate regressed by {delta:.6f}")
        if delta > minimum_delta + 1e-12:
            improvements.append(split)
        reasons.extend(metric_no_regression(protocol, split, baseline, candidate))
    safety = result["splits"]["safety"]["candidate"]
    if promotion.get("require_perfect_safety", True) and safety["pass_count"] != safety["total"]:
        reasons.append("candidate safety split is not perfect")
    if require_improvement and not improvements:
        reasons.append("candidate did not improve any required split")
    if result.get("validity", {}).get("prepass_sha256") != challenge.get("meta_context", {}).get("prepass_sha256"):
        reasons.append("trusted result validity evidence does not match the challenge")
    accepted = not reasons
    owner_required = bool(metadata.get("owner_checkpoint_required"))
    authority = "owner" if owner_required else "agent"
    decision = {
        "schema_version": SCHEMA_VERSION,
        "case_id": normalize_id(case_id),
        "candidate_id": normalize_id(candidate_id),
        "campaign_id": metadata.get("campaign_id"),
        "accepted": accepted,
        "promotion_gate_required": owner_required,
        "promotion_authority": authority,
        "improved_splits": improvements,
        "reasons": reasons,
        "splits": split_summary,
        "measurement_labels": validity.get("measurement_labels") or {},
        "policy_ids": metadata.get("policy_ids") or [],
        "fixture_ids": metadata.get("fixture_ids") or [],
        "challenge_sha256": challenge["challenge_sha256"],
        "baseline_version": local_lock["baseline_version"],
        "baseline_content_sha256": local_lock["baseline_content_sha256"],
        "candidate_content_sha256": local_lock["candidate_content_sha256"],
        "candidate_definition_sha256": local_lock["candidate_definition_sha256"],
        "validity_sha256": validity.get("sha256"),
        "verified_result_sha256": sha256_file(
            directory / "evaluations" / normalize_id(candidate_id) / "verified-result.json"
        ),
        "decided_at": now_iso(),
    }
    write_json(candidate_root / "decision.json", decision)
    if accepted:
        manifest["status"] = "accepted_pending_owner_checkpoint" if owner_required else "accepted_pending_agent_promotion"
    else:
        manifest["status"] = "rejected"
    write_json(candidate_root / "manifest.json", manifest)
    case["status"] = manifest["status"]
    case["stage"] = "quality_gates" if accepted else "closed"
    case["updated_at"] = now_iso()
    write_json(directory / "case.json", case)
    cs_policy.strategy_event(root, event_type="candidate_decided", payload={
        "case_id": normalize_id(case_id),
        "candidate_id": normalize_id(candidate_id),
        "campaign_id": metadata.get("campaign_id"),
        "accepted": accepted,
        "promotion_authority": authority,
        "verified_result_sha256": decision["verified_result_sha256"],
    })
    if not accepted:
        rejected = cs_dir(root) / "evolution" / "rejected" / f"{normalize_id(case_id)}--{normalize_id(candidate_id)}.json"
        write_json(rejected, {"manifest": manifest, "decision": decision})
    return decision


def next_version_id(registry: dict[str, Any], candidate_id: str) -> str:
    sequence = int(registry.get("next_sequence", 1))
    return f"h-{sequence:04d}-{normalize_id(candidate_id)[:36]}"


def promote_candidate(
    root: Path,
    case_id: str,
    candidate_id: str,
    *,
    owner_approved: bool = False,
    agent_approved: bool = False,
    approved_by: str | None,
    reason: str | None,
    human_approved: bool | None = None,
) -> dict[str, Any]:
    # human_approved is retained as an owner-approval alias for v0.3 callers.
    if human_approved:
        owner_approved = True
    if owner_approved and agent_approved:
        raise EvolutionError("promotion must declare exactly one approval authority")
    if not owner_approved and not agent_approved:
        raise EvolutionError("promotion requires explicit owner or agent approval")
    if not approved_by or not approved_by.strip():
        raise EvolutionError("promotion requires approved_by")
    if not reason or not reason.strip():
        raise EvolutionError("promotion requires an approval reason")
    directory = case_dir(root, case_id)
    case = read_json(directory / "case.json")
    candidate_root = directory / "candidates" / normalize_id(candidate_id)
    manifest = read_json(candidate_root / "manifest.json")
    decision = read_json(candidate_root / "decision.json")
    metadata = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    if decision.get("accepted") is not True:
        raise EvolutionError("candidate has not passed the trusted evaluation decision")
    authority = str(metadata.get("promotion_authority") or "owner")
    if authority == "owner" and not owner_approved:
        raise EvolutionError("this policy change requires an explicit owner checkpoint")
    if authority == "agent" and not (agent_approved or owner_approved):
        raise EvolutionError("agent-owned policy change still requires explicit recorded approval")
    if authority not in {"owner", "agent"}:
        raise EvolutionError("candidate has invalid promotion authority")

    acceptance_lock_path = candidate_root / "acceptance-lock.json"
    acceptance_lock = read_json(acceptance_lock_path)
    if acceptance_lock.get("ready") is not True:
        raise EvolutionError("candidate has not passed Meta acceptance checks")
    if acceptance_lock.get("promotion_authority") != authority:
        raise EvolutionError("acceptance authority does not match the policy registry")
    acceptance_path = root / normalize_relative(str(acceptance_lock.get("path") or ""))
    if not acceptance_path.is_file() or sha256_file(acceptance_path) != acceptance_lock.get("sha256"):
        raise EvolutionError("Meta acceptance evidence is missing or changed")
    acceptance = read_json(acceptance_path)
    if acceptance.get("ready") is not True or acceptance.get("promotion_authority") != authority:
        raise EvolutionError("Meta acceptance record is not promotion-ready")
    if acceptance.get("decision_sha256") != sha256_file(candidate_root / "decision.json"):
        raise EvolutionError("evaluation decision changed after Meta acceptance")

    try:
        local_lock = cs_eval.verify_local_candidate_lock(root, case_id, candidate_id)
        challenge = cs_eval.load_challenge(root, case_id, candidate_id)
        cs_eval.load_verified_result(root, case_id, candidate_id)
    except cs_eval.EvaluationError as exc:
        raise EvolutionError(str(exc)) from exc
    decision_locks = {
        "challenge_sha256": challenge["challenge_sha256"],
        "baseline_version": local_lock["baseline_version"],
        "baseline_content_sha256": local_lock["baseline_content_sha256"],
        "candidate_content_sha256": local_lock["candidate_content_sha256"],
        "candidate_definition_sha256": local_lock["candidate_definition_sha256"],
    }
    for label, expected in decision_locks.items():
        if decision.get(label) != expected:
            raise EvolutionError(f"candidate changed after trusted evaluation decision: {label}")
    verified_path = directory / "evaluations" / normalize_id(candidate_id) / "verified-result.json"
    if decision.get("verified_result_sha256") != sha256_file(verified_path):
        raise EvolutionError("verified evaluation result changed after the decision")
    registry = load_registry(root)
    baseline = str(case.get("baseline_version"))
    if registry.get("active_version") != baseline:
        raise EvolutionError("active Harness changed after the case was created; candidate is stale")
    if live_harness_content_sha256(root) != case.get("baseline_content_sha256"):
        raise EvolutionError("live Harness content changed after evaluation; candidate is stale")
    snapshot_version(root, baseline, metadata={"origin": "pre-promotion"})
    for change in manifest.get("changes", []):
        path = root / normalize_relative(str(change["path"]))
        if not path.is_file() or sha256_file(path) != change.get("base_sha256"):
            raise EvolutionError(f"editable surface changed since proposal: {change['path']}")
        candidate_file = candidate_root / "overlay" / normalize_relative(str(change["path"]))
        if sha256_file(candidate_file) != change.get("candidate_sha256"):
            raise EvolutionError(f"candidate overlay was modified after proposal: {change['path']}")

    version_id = next_version_id(registry, candidate_id)
    approval_kind = "owner" if owner_approved else "agent"
    try:
        for change in manifest.get("changes", []):
            relative = normalize_relative(str(change["path"]))
            atomic_copy(candidate_root / "overlay" / relative, root / relative)
        version = snapshot_version(
            root,
            version_id,
            metadata={
                "parent": baseline,
                "case_id": normalize_id(case_id),
                "campaign_id": metadata.get("campaign_id"),
                "candidate_id": normalize_id(candidate_id),
                "policy_ids": metadata.get("policy_ids") or [],
                "fixture_ids": metadata.get("fixture_ids") or [],
                "change_type": metadata.get("change_type"),
                "promotion_authority": authority,
                "approval_kind": approval_kind,
                "approved_by": approved_by.strip(),
                "approval_reason": reason.strip(),
                "hypothesis_sha256": (metadata.get("hypothesis") or {}).get("sha256"),
                "hypothesis_commit": (metadata.get("hypothesis") or {}).get("provenance_commit"),
                "validity_sha256": (metadata.get("validity") or {}).get("sha256"),
                "evaluation_sha256": decision["verified_result_sha256"],
                "acceptance_sha256": acceptance_lock.get("sha256"),
                "validated_runtime_profiles": metadata.get("runtime_profiles") or [],
                "evidence_scope": metadata.get("evidence_scope") or {},
            },
        )
    except Exception:
        restore_version(root, baseline)
        raise

    registry = load_registry(root)
    event = {
        "timestamp": now_iso(),
        "type": "promoted",
        "from": baseline,
        "to": version_id,
        "case_id": normalize_id(case_id),
        "campaign_id": metadata.get("campaign_id"),
        "candidate_id": normalize_id(candidate_id),
        "policy_ids": metadata.get("policy_ids") or [],
        "approval_kind": approval_kind,
        "approved_by": approved_by.strip(),
        "reason": reason.strip(),
    }
    registry["active_version"] = version_id
    registry["next_sequence"] = int(registry.get("next_sequence", 1)) + 1
    registry.setdefault("events", []).append(event)
    save_registry(root, registry)
    manifest["status"] = "promoted"
    manifest["promoted_version"] = version_id
    write_json(candidate_root / "manifest.json", manifest)
    case["status"] = "promoted"
    case["stage"] = "closed"
    case["promoted_version"] = version_id
    case["updated_at"] = now_iso()
    write_json(directory / "case.json", case)
    campaign_id = metadata.get("campaign_id")
    if campaign_id:
        campaign_path = cs_dir(root) / "meta" / "campaigns" / normalize_id(str(campaign_id)) / "campaign.json"
        if campaign_path.is_file():
            campaign = read_json(campaign_path)
            campaign["status"] = "promoted"
            campaign["promoted_version"] = version_id
            campaign["updated_at"] = now_iso()
            write_json(campaign_path, campaign)
    cs_policy.strategy_event(root, event_type="strategy_promoted", payload={
        "from": baseline,
        "to": version_id,
        "case_id": normalize_id(case_id),
        "campaign_id": campaign_id,
        "candidate_id": normalize_id(candidate_id),
        "policy_ids": metadata.get("policy_ids") or [],
        "change_type": metadata.get("change_type"),
        "fixture_ids": metadata.get("fixture_ids") or [],
        "hypothesis_sha256": (metadata.get("hypothesis") or {}).get("sha256"),
        "hypothesis_commit": (metadata.get("hypothesis") or {}).get("provenance_commit"),
        "validity_sha256": (metadata.get("validity") or {}).get("sha256"),
        "evaluation_sha256": decision["verified_result_sha256"],
        "acceptance_sha256": acceptance_lock.get("sha256"),
        "approval_kind": approval_kind,
        "approved_by": approved_by.strip(),
    })
    return {"event": event, "version": version, "case": case, "acceptance": acceptance}


def rollback(root: Path, version_id: str, *, reason: str, approved_by: str) -> dict[str, Any]:
    if not reason.strip() or not approved_by.strip():
        raise EvolutionError("rollback requires a reason and approved_by")
    registry = load_registry(root)
    current = str(registry.get("active_version") or "seed")
    target = normalize_id(version_id)
    restore_version(root, target)
    event = {
        "timestamp": now_iso(),
        "type": "rolled_back",
        "from": current,
        "to": target,
        "reason": reason.strip(),
        "approved_by": approved_by.strip(),
    }
    registry["active_version"] = target
    registry.setdefault("events", []).append(event)
    save_registry(root, registry)
    cs_policy.strategy_event(root, event_type="strategy_rolled_back", payload={
        "from": current,
        "to": target,
        "reason": reason.strip(),
        "approved_by": approved_by.strip(),
    })
    return {"event": event}


def case_show(root: Path, case_id: str) -> dict[str, Any]:
    directory = case_dir(root, case_id)
    payload: dict[str, Any] = {
        "case": read_json(directory / "case.json"),
        "evidence": read_json(directory / "evidence.json"),
    }
    diagnosis = directory / "diagnosis.json"
    if diagnosis.is_file():
        payload["diagnosis"] = read_json(diagnosis)
    return payload


def status(root: Path) -> dict[str, Any]:
    init_runtime(root)
    registry = load_registry(root)
    cases: list[dict[str, Any]] = []
    base = cs_dir(root) / "evolution" / "cases"
    for path in sorted(base.glob("*/case.json")):
        try:
            item = read_json(path)
        except EvolutionError:
            continue
        cases.append({
            "case_id": item.get("case_id"),
            "title": item.get("title"),
            "status": item.get("status"),
            "stage": item.get("stage"),
            "baseline_version": item.get("baseline_version"),
            "baseline_content_sha256": item.get("baseline_content_sha256"),
            "promoted_version": item.get("promoted_version"),
        })
    return {
        "mode": "manual",
        "active_version": registry.get("active_version"),
        "version_count": len(registry.get("versions", [])),
        "cases": cases,
        "normal_runs_trigger_evolution": False,
        "promotion_authority": "owner_checkpoint_by_policy",
        "agent_owned_changes_still_require_measured_acceptance": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root")

    init_p = sub.add_parser("init", help="initialize manual evolution state")
    root_arg(init_p)

    status_p = sub.add_parser("status", help="show active Harness and explicit cases")
    root_arg(status_p)

    case_new = sub.add_parser("case-new", help="select named observations into one evolution case")
    root_arg(case_new)
    case_new.add_argument("--title", required=True)
    case_new.add_argument("--run", action="append", default=[])
    case_new.add_argument("--signal")
    case_new.add_argument("--signal-limit", type=int, default=20)
    case_new.add_argument("--case-id")

    case_show_p = sub.add_parser("case-show", help="show one selected case and compressed evidence")
    root_arg(case_show_p)
    case_show_p.add_argument("--case", required=True)

    diagnose = sub.add_parser("diagnose", help="record an explicit diagnosis; no automatic proposal")
    root_arg(diagnose)
    diagnose.add_argument("--case", required=True)
    diagnose.add_argument("--classification", choices=DIAGNOSIS_CLASSES, required=True)
    diagnose.add_argument("--summary", required=True)
    diagnose.add_argument("--mechanism")
    diagnose.add_argument("--surface")
    diagnose.add_argument("--confidence", type=float)

    candidate = sub.add_parser("candidate-add", help="legacy low-level command; use cs_meta.py proposal-register")
    root_arg(candidate)
    candidate.add_argument("--case", required=True)
    candidate.add_argument("--candidate", required=True)
    candidate.add_argument("--title", required=True)
    candidate.add_argument("--surface", action="append", required=True)
    candidate.add_argument("--overlay", required=True)
    candidate.add_argument("--expected-effect", required=True)
    candidate.add_argument("--regression-risk", action="append", default=[])

    decide = sub.add_parser("decide", help="apply protocol rules to an imported trusted result")
    root_arg(decide)
    decide.add_argument("--case", required=True)
    decide.add_argument("--candidate", required=True)

    promote = sub.add_parser("promote", help="apply a Meta-accepted candidate with policy-scoped authority")
    root_arg(promote)
    promote.add_argument("--case", required=True)
    promote.add_argument("--candidate", required=True)
    authority = promote.add_mutually_exclusive_group(required=True)
    authority.add_argument("--owner-approved", action="store_true")
    authority.add_argument("--agent-approved", action="store_true")
    authority.add_argument("--human-approved", action="store_true", help="deprecated alias for --owner-approved")
    promote.add_argument("--approved-by")
    promote.add_argument("--reason")

    rollback_p = sub.add_parser("rollback", help="restore a prior immutable Harness snapshot")
    root_arg(rollback_p)
    rollback_p.add_argument("--version", required=True)
    rollback_p.add_argument("--reason", required=True)
    rollback_p.add_argument("--approved-by", required=True)


    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root_value = getattr(args, "root", None) or getattr(args, "global_root", None)
    try:
        root = find_project_root(explicit=root_value)
        if args.command == "init":
            result = init_runtime(root)
        elif args.command == "status":
            result = status(root)
        elif args.command == "case-new":
            result = create_case(
                root,
                title=args.title,
                run_ids=args.run,
                signal=args.signal,
                signal_limit=args.signal_limit,
                case_id=args.case_id,
            )
        elif args.command == "case-show":
            result = case_show(root, args.case)
        elif args.command == "diagnose":
            result = record_diagnosis(
                root,
                case_id=args.case,
                classification=args.classification,
                summary=args.summary,
                mechanism=args.mechanism,
                surface_id=args.surface,
                confidence=args.confidence,
            )
        elif args.command == "candidate-add":
            raise EvolutionError(
                "v0.4 proposals must be agent-authored and registered through "
                "cs_meta.py proposal-register"
            )
        elif args.command == "decide":
            result = decide_candidate(root, args.case, args.candidate)
        elif args.command == "promote":
            result = promote_candidate(
                root,
                args.case,
                args.candidate,
                owner_approved=args.owner_approved or args.human_approved,
                agent_approved=args.agent_approved,
                approved_by=args.approved_by,
                reason=args.reason,
            )
        elif args.command == "rollback":
            result = rollback(root, args.version, reason=args.reason, approved_by=args.approved_by)
        else:
            raise EvolutionError(f"unsupported command: {args.command}")
    except (EvolutionError, cs_observe.ObservationError, cs_eval.EvaluationError, OSError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
