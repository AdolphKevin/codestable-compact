#!/usr/bin/env python3
"""Passive, low-cost run observations for CodeStable Compact.

Normal development uses this tool as a flight recorder. It writes compact,
structured, temporary evidence and never diagnoses, proposes, evaluates, or
changes the active Harness. Evolution tools may read only observations that a
human or explicit command has selected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = 3
OBSERVATION_STATES = ("pending", "flagged", "selected")
RUN_STATUSES = ("running", "finished")
OUTCOMES = ("completed", "failed", "blocked", "cancelled")
VALIDATION_STATUSES = ("passed", "failed", "blocked", "not_run")
EVENT_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
SIGNAL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")

FORBIDDEN_PAYLOAD_KEYS = {
    "prompt",
    "raw_prompt",
    "messages",
    "conversation",
    "model_response",
    "raw_response",
    "source",
    "source_code",
    "file_contents",
    "diff",
    "patch",
    "credential",
    "credentials",
    "secret",
    "secrets",
    "environment_variables",
    "env",
    "private_holdout",
    "held_out_tasks",
    "task_traces",
    "stdout",
    "stderr",
    "tool_output",
    "raw_output",
    "full_output",
}

GATE_OUTCOMES = {"passed", "rejected", "paused", "overridden"}
HUMAN_INTERVENTION_TYPES = {"correction", "approval", "override", "input", "scope_change"}
STANDARD_EVENT_RULES: dict[str, tuple[str, ...]] = {
    "stage_started": ("stage",),
    "stage_finished": ("stage",),
    "gate_evaluated": ("gate_id", "outcome", "reason_code"),
    "checkpoint_paused": ("checkpoint_id", "reason_code"),
    "human_intervention": ("intervention_type",),
    "token_usage": ("total_tokens",),
    "policy_applied": ("policy_id",),
    "knowledge_read": ("path",),
    "knowledge_written": ("path", "operation"),
}

DEFAULT_OBSERVABILITY: dict[str, Any] = {
    "enabled": True,
    "mode": "passive",
    "best_effort": True,
    "read_during_normal_runs": False,
    "capture": {
        "raw_prompts": False,
        "raw_model_responses": False,
        "source_or_diffs": False,
        "full_tool_output": False,
        "event_metadata": True,
        "verification_evidence": True,
        "user_corrections": True,
    },
    "limits": {
        "max_run_size_kb": 256,
        "max_events": 500,
        "max_event_payload_bytes": 8192,
        "max_string_chars": 2048,
    },
    "retention": {
        "pending_days": 30,
        "flagged_days": 180,
        "max_pending_runs": 200,
        "stale_running_days": 7,
    },
}


class ObservationError(RuntimeError):
    """A deterministic observation invariant was violated."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ObservationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ObservationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ObservationError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json_dump(data))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def deep_merge(defaults: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, default in defaults.items():
        if key not in actual:
            merged[key] = default
        elif isinstance(default, dict) and isinstance(actual[key], dict):
            merged[key] = deep_merge(default, actual[key])
        else:
            merged[key] = actual[key]
    for key, value in actual.items():
        if key not in merged:
            merged[key] = value
    return merged


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.exists():
            raise ObservationError(f"project root does not exist: {root}")
        return root
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".codestable").is_dir() or (candidate / ".git").exists():
            return candidate
    return current


def cs_dir(root: Path) -> Path:
    return root / ".codestable"


def observations_dir(root: Path) -> Path:
    return cs_dir(root) / "observations"


def normalize_id(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    if not result:
        raise ObservationError("identifier cannot be empty")
    return result[:96]


def normalize_signal(value: str) -> str:
    signal = value.strip().casefold()
    if not SIGNAL_NAME.fullmatch(signal):
        raise ObservationError(f"invalid signal: {value!r}")
    return signal


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_observability_config(root: Path) -> dict[str, Any]:
    path = cs_dir(root) / "config.json"
    if not path.is_file():
        return dict(DEFAULT_OBSERVABILITY)
    try:
        config = read_json(path)
    except ObservationError:
        return dict(DEFAULT_OBSERVABILITY)
    section = config.get("observability")
    if not isinstance(section, dict):
        section = {}
    return deep_merge(DEFAULT_OBSERVABILITY, section)


def init_runtime(root: Path) -> dict[str, Any]:
    base = observations_dir(root)
    created: list[str] = []
    preserved: list[str] = []
    for state in OBSERVATION_STATES:
        directory = base / state
        if directory.is_dir():
            preserved.append(directory.relative_to(root).as_posix())
        else:
            directory.mkdir(parents=True, exist_ok=True)
            created.append(directory.relative_to(root).as_posix())
    index = base / "index.jsonl"
    if index.exists():
        preserved.append(index.relative_to(root).as_posix())
    else:
        atomic_write(index, "")
        created.append(index.relative_to(root).as_posix())
    return {"root": str(root), "created": created, "preserved": preserved}


def observation_directory(root: Path, run_id: str) -> tuple[str, Path]:
    identifier = normalize_id(run_id)
    base = observations_dir(root)
    matches = [(state, base / state / identifier) for state in OBSERVATION_STATES]
    existing = [(state, path) for state, path in matches if path.is_dir()]
    if not existing:
        raise ObservationError(f"unknown observation: {identifier}")
    if len(existing) > 1:
        raise ObservationError(f"observation exists in multiple states: {identifier}")
    return existing[0]


def load_observation(root: Path, run_id: str) -> dict[str, Any]:
    state, directory = observation_directory(root, run_id)
    meta = read_json(directory / "meta.json")
    outcome = read_json(directory / "outcome.json") if (directory / "outcome.json").is_file() else None
    return {
        "state": state,
        "directory": directory,
        "meta": meta,
        "outcome": outcome,
    }


def harness_identity(root: Path) -> dict[str, Any]:
    registry_path = cs_dir(root) / "harness" / "registry.json"
    manifest_path = cs_dir(root) / "harness" / "manifest.json"
    version = "seed"
    registry: dict[str, Any] = {}
    if registry_path.is_file():
        try:
            registry = read_json(registry_path)
            version = str(registry.get("active_version") or "seed")
        except ObservationError:
            version = "unknown"
            registry = {}

    records: list[dict[str, Any]] = []
    if manifest_path.is_file():
        try:
            manifest = read_json(manifest_path)
            surfaces = manifest.get("editable_surfaces") or []
            if isinstance(surfaces, list):
                for surface in sorted(
                    (item for item in surfaces if isinstance(item, dict)),
                    key=lambda item: str(item.get("path") or ""),
                ):
                    relative = str(surface.get("path") or "").replace("\\", "/").strip()
                    path = root / relative
                    records.append({
                        "surface_id": str(surface.get("id") or ""),
                        "path": relative,
                        "sha256": sha256_file(path) if path.is_file() else None,
                    })
        except ObservationError:
            records = []
    content_sha256 = hashlib.sha256(canonical_json(records)).hexdigest() if records else None
    snapshot_sha256 = None
    versions = registry.get("versions") if isinstance(registry, dict) else None
    if isinstance(versions, list):
        for item in versions:
            if isinstance(item, dict) and item.get("id") == version:
                snapshot_sha256 = item.get("content_sha256")
                break
    return {
        "version": version,
        "content_sha256": content_sha256,
        "snapshot_content_sha256": snapshot_sha256,
        "drift_detected": bool(snapshot_sha256 and content_sha256 and snapshot_sha256 != content_sha256),
        "manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
    }


def append_index(root: Path, action: str, run_id: str, **extra: Any) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": now_iso(),
        "action": action,
        "run_id": run_id,
        **extra,
    }
    append_jsonl(observations_dir(root) / "index.jsonl", payload)


def sanitize_value(value: Any, *, max_string_chars: int, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        items = list(value.items())
        for key, child in items[:100]:
            normalized_key = str(key).strip()
            if normalized_key.casefold() in FORBIDDEN_PAYLOAD_KEYS:
                dotted = ".".join((*path, normalized_key))
                raise ObservationError(f"event payload contains forbidden raw-content field: {dotted}")
            result[normalized_key] = sanitize_value(
                child,
                max_string_chars=max_string_chars,
                path=(*path, normalized_key),
            )
        if len(items) > 100:
            result["_truncated_keys"] = len(items) - 100
        return result
    if isinstance(value, list):
        result = [sanitize_value(child, max_string_chars=max_string_chars, path=path) for child in value[:100]]
        if len(value) > 100:
            result.append({"_truncated_items": len(value) - 100})
        return result
    if isinstance(value, str):
        return value[:max_string_chars]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:max_string_chars]


def ensure_event_name(value: str) -> str:
    name = value.strip().casefold()
    if not EVENT_NAME.fullmatch(name):
        raise ObservationError(f"invalid event type: {value!r}")
    return name


def validate_standard_event(name: str, payload: dict[str, Any]) -> None:
    required = STANDARD_EVENT_RULES.get(name)
    if required:
        missing = [field for field in required if field not in payload or payload[field] in (None, "")]
        if missing:
            raise ObservationError(f"event {name} is missing required fields: {missing}")
    if name == "gate_evaluated" and str(payload.get("outcome")) not in GATE_OUTCOMES:
        raise ObservationError(f"invalid gate outcome: {payload.get('outcome')!r}")
    if name == "human_intervention" and str(payload.get("intervention_type")) not in HUMAN_INTERVENTION_TYPES:
        raise ObservationError(f"invalid human intervention type: {payload.get('intervention_type')!r}")
    if name == "token_usage":
        total = payload.get("total_tokens")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise ObservationError("token_usage.total_tokens must be a non-negative integer")
        for field in ("input_tokens", "output_tokens", "cached_tokens"):
            value = payload.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ObservationError(f"token_usage.{field} must be a non-negative integer")


def read_events(directory: Path) -> list[dict[str, Any]]:
    path = directory / "events.jsonl"
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ObservationError(f"invalid observation event JSON at line {number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ObservationError(f"observation event line {number} must be an object")
        events.append(value)
    return events


def summarize_trace(events: Sequence[dict[str, Any]], *, dropped_events: int = 0) -> dict[str, Any]:
    stages: list[str] = []
    gates = {"passed": 0, "rejected": 0, "paused": 0, "overridden": 0}
    gate_reasons: dict[str, int] = {}
    checkpoints = 0
    interventions = {kind: 0 for kind in sorted(HUMAN_INTERVENTION_TYPES)}
    tokens = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "reported_events": 0}
    policy_ids: set[str] = set()
    knowledge_reads = 0
    knowledge_writes = 0
    event_types: dict[str, int] = {}
    for event in events:
        name = str(event.get("type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_types[name] = event_types.get(name, 0) + 1
        if name in {"stage_started", "stage_finished"}:
            stage = str(payload.get("stage") or "")
            if stage and stage not in stages:
                stages.append(stage)
        elif name == "gate_evaluated":
            outcome = str(payload.get("outcome") or "")
            if outcome in gates:
                gates[outcome] += 1
            reason = str(payload.get("reason_code") or "")
            if reason:
                gate_reasons[reason] = gate_reasons.get(reason, 0) + 1
        elif name == "checkpoint_paused":
            checkpoints += 1
        elif name == "human_intervention":
            kind = str(payload.get("intervention_type") or "")
            if kind in interventions:
                interventions[kind] += 1
        elif name == "token_usage":
            tokens["reported_events"] += 1
            for field in ("total_tokens", "input_tokens", "output_tokens", "cached_tokens"):
                value = payload.get(field)
                if isinstance(value, int) and not isinstance(value, bool):
                    tokens[field] += max(0, value)
        elif name == "policy_applied":
            policy_id = str(payload.get("policy_id") or "")
            if policy_id:
                policy_ids.add(policy_id)
        elif name == "knowledge_read":
            knowledge_reads += 1
        elif name == "knowledge_written":
            knowledge_writes += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "event_count": len(events),
        "dropped_events": int(dropped_events),
        "stages": stages,
        "gates": {"counts": gates, "reason_counts": dict(sorted(gate_reasons.items()))},
        "checkpoint_pauses": checkpoints,
        "human_interventions": {"counts": interventions, "total": sum(interventions.values())},
        "tokens": tokens,
        "policy_ids": sorted(policy_ids),
        "knowledge": {"reads": knowledge_reads, "writes": knowledge_writes},
        "event_types": dict(sorted(event_types.items())),
    }


def start_observation(
    root: Path,
    *,
    work: str,
    task_id: str,
    kind: str,
    lane: str,
    entry: str,
    route: str,
    model_profile: str,
    adapter: str,
    start_stage: str | None = None,
    repository_commit: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    init_runtime(root)
    config = load_observability_config(root)
    if config.get("enabled") is not True:
        return {"enabled": False, "recorded": False}
    if config.get("mode") != "passive":
        raise ObservationError("observability.mode must be 'passive' for normal work")

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    identifier = normalize_id(run_id or f"run-{timestamp}-{task_id}")
    directory = observations_dir(root) / "pending" / identifier
    if any((observations_dir(root) / state / identifier).exists() for state in OBSERVATION_STATES):
        raise ObservationError(f"observation already exists: {identifier}")
    directory.mkdir(parents=True)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "run_id": identifier,
        "state": "pending",
        "status": "running",
        "work_id": work,
        "task_id": task_id,
        "kind": kind,
        "lane": lane,
        "entry": entry,
        "route": route,
        "start_stage": start_stage,
        "end_stage": None,
        "harness": harness_identity(root),
        "environment": {
            "repository_commit": repository_commit,
            "model_profile": model_profile,
            "adapter": adapter,
        },
        "started_at": now_iso(),
        "finished_at": None,
        "event_count": 0,
        "dropped_events": 0,
        "signals": [],
        "selection": {"case_ids": []},
    }
    write_json(directory / "meta.json", meta)
    atomic_write(directory / "events.jsonl", "")
    append_index(root, "started", identifier, state="pending")
    return {"enabled": True, "recorded": True, **meta}


def append_event(
    root: Path,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    state, directory = observation_directory(root, run_id)
    meta = read_json(directory / "meta.json")
    if meta.get("status") != "running":
        raise ObservationError(f"observation is not running: {run_id}")
    config = load_observability_config(root)
    limits = config.get("limits", {})
    max_events = int(limits.get("max_events", 500))
    max_payload = int(limits.get("max_event_payload_bytes", 8192))
    max_string = int(limits.get("max_string_chars", 2048))
    max_run_bytes = max(16 * 1024, int(limits.get("max_run_size_kb", 256)) * 1024)
    name = ensure_event_name(event_type)
    clean = sanitize_value(payload, max_string_chars=max_string)
    if not isinstance(clean, dict):
        raise ObservationError("event payload must remain an object after sanitization")
    validate_standard_event(name, clean)
    encoded = canonical_json(clean)
    sequence = int(meta.get("event_count", 0)) + 1
    event = {
        "schema_version": SCHEMA_VERSION,
        "seq": sequence,
        "timestamp": now_iso(),
        "type": name,
        "payload": clean,
    }
    event_bytes = len((json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    over_limit = (
        len(encoded) > max_payload
        or int(meta.get("event_count", 0)) >= max_events
        or directory_size(directory) + event_bytes + 2048 > max_run_bytes
    )
    if over_limit:
        meta["dropped_events"] = int(meta.get("dropped_events", 0)) + 1
        write_json(directory / "meta.json", meta)
        return {
            "run_id": meta["run_id"],
            "recorded": False,
            "reason": "event_limit",
            "dropped_events": meta["dropped_events"],
        }
    append_jsonl(directory / "events.jsonl", event)
    meta["event_count"] = sequence
    write_json(directory / "meta.json", meta)
    return {"run_id": meta["run_id"], "recorded": True, "event": event, "state": state}


def validate_evidence(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if index >= 100:
            break
        if not isinstance(item, dict):
            raise ObservationError("validation evidence entries must be objects")
        path = str(item.get("path") or "").strip()
        digest = str(item.get("sha256") or "").strip().casefold()
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ObservationError(f"evidence path must be safe and project-relative: {path!r}")
        if digest and not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ObservationError(f"invalid evidence sha256 for {path}")
        result.append({"path": Path(path).as_posix(), "sha256": digest or None})
    return result


def validate_task_validation(value: dict[str, Any], *, max_string_chars: int = 2048) -> dict[str, Any]:
    status = str(value.get("status") or "not_run").strip().casefold()
    if status not in VALIDATION_STATUSES:
        raise ObservationError(f"invalid task validation status: {status}")
    verifier_id = str(value.get("verifier_id") or "").strip() or None
    exit_code = value.get("exit_code")
    if exit_code is not None:
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ObservationError("task validation exit_code must be an integer")
    evidence = validate_evidence(value.get("evidence") or [])
    if status == "passed":
        if not verifier_id:
            raise ObservationError("passed task validation requires verifier_id")
        if exit_code != 0 and not evidence:
            raise ObservationError("passed task validation requires exit_code=0 or evidence")
    if status == "failed":
        if not verifier_id:
            raise ObservationError("failed task validation requires verifier_id")
        if exit_code in (None, 0) and not evidence:
            raise ObservationError("failed task validation requires non-zero exit_code or evidence")
    return {
        "status": status,
        "verifier_id": verifier_id,
        "command": (str(value.get("command") or "").strip()[:max_string_chars] or None),
        "exit_code": exit_code,
        "evidence": evidence,
        "issued_by": str(value.get("issued_by") or "task-runner").strip()[:256],
    }


def move_observation(root: Path, run_id: str, destination_state: str) -> Path:
    if destination_state not in OBSERVATION_STATES:
        raise ObservationError(f"invalid observation state: {destination_state}")
    current_state, directory = observation_directory(root, run_id)
    if current_state == destination_state:
        return directory
    destination = observations_dir(root) / destination_state / directory.name
    if destination.exists():
        raise ObservationError(f"destination observation already exists: {destination}")
    shutil.move(str(directory), str(destination))
    return destination


def finish_observation(
    root: Path,
    run_id: str,
    *,
    status: str,
    end_stage: str | None,
    task_validation: dict[str, Any],
    signals: Sequence[str] = (),
    metrics: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    current_state, directory = observation_directory(root, run_id)
    meta = read_json(directory / "meta.json")
    if meta.get("status") != "running":
        raise ObservationError(f"observation already finished: {run_id}")
    normalized_status = status.strip().casefold()
    if normalized_status not in OUTCOMES:
        raise ObservationError(f"invalid observation outcome: {status}")
    clean_signals = sorted({normalize_signal(value) for value in (*meta.get("signals", []), *signals)})
    config = load_observability_config(root)
    limits = config.get("limits", {})
    max_string = int(limits.get("max_string_chars", 2048))
    max_payload = int(limits.get("max_event_payload_bytes", 8192))
    max_run_bytes = max(16 * 1024, int(limits.get("max_run_size_kb", 256)) * 1024)
    validation = validate_task_validation(task_validation, max_string_chars=max_string)
    clean_metrics = sanitize_value(metrics or {}, max_string_chars=max_string)
    if len(canonical_json(clean_metrics)) > max_payload:
        clean_metrics = {"dropped": True, "reason": "metrics_payload_limit"}

    meta["status"] = "finished"
    meta["end_stage"] = end_stage
    meta["finished_at"] = now_iso()
    meta["signals"] = clean_signals
    target_state = "flagged" if clean_signals else current_state
    if current_state == "selected":
        target_state = "selected"
    meta["state"] = target_state
    trace_summary = summarize_trace(
        read_events(directory),
        dropped_events=int(meta.get("dropped_events", 0)),
    )
    outcome = {
        "schema_version": SCHEMA_VERSION,
        "run_id": meta["run_id"],
        "status": normalized_status,
        "task_validation": validation,
        "signals": clean_signals,
        "metrics": clean_metrics,
        "trace_summary": trace_summary,
        "note": (note or "")[:max_string],
        "selected_for_evolution": target_state == "selected",
    }
    write_json(directory / "meta.json", meta)
    projected = directory_size(directory) + len(json_dump(outcome).encode("utf-8"))
    if projected > max_run_bytes:
        outcome["metrics"] = {"dropped": True, "reason": "run_size_limit"}
        outcome["note"] = ""
    write_json(directory / "outcome.json", outcome)
    if target_state != current_state:
        directory = move_observation(root, run_id, target_state)
    append_index(root, "finished", meta["run_id"], state=target_state, outcome=normalized_status, signals=clean_signals)
    enforce_pending_cap(root)
    return {"meta": meta, "outcome": outcome, "path": directory.relative_to(root).as_posix()}


def flag_observation(root: Path, run_id: str, *, signals: Sequence[str], note: str | None = None) -> dict[str, Any]:
    if not signals:
        raise ObservationError("flag requires at least one signal")
    current_state, directory = observation_directory(root, run_id)
    meta = read_json(directory / "meta.json")
    combined = sorted({normalize_signal(value) for value in (*meta.get("signals", []), *signals)})
    meta["signals"] = combined
    if current_state != "selected":
        meta["state"] = "flagged"
    write_json(directory / "meta.json", meta)
    outcome_path = directory / "outcome.json"
    if outcome_path.is_file():
        outcome = read_json(outcome_path)
        outcome["signals"] = combined
        if note:
            outcome["note"] = note[: int(load_observability_config(root).get("limits", {}).get("max_string_chars", 2048))]
        write_json(outcome_path, outcome)
    else:
        append_event(root, run_id, "harness_issue_flagged", {"signals": combined, "note": note or ""})
    if current_state == "pending":
        directory = move_observation(root, run_id, "flagged")
    append_index(root, "flagged", meta["run_id"], state="flagged", signals=combined)
    return {"run_id": meta["run_id"], "state": "selected" if current_state == "selected" else "flagged", "signals": combined, "path": directory.relative_to(root).as_posix()}


def select_observation(root: Path, run_id: str, *, case_id: str) -> dict[str, Any]:
    current_state, directory = observation_directory(root, run_id)
    meta = read_json(directory / "meta.json")
    if meta.get("status") != "finished" or not (directory / "outcome.json").is_file():
        raise ObservationError(f"only finished observations can be selected: {run_id}")
    normalized_case = normalize_id(case_id)
    selection = meta.setdefault("selection", {"case_ids": []})
    case_ids = list(selection.get("case_ids") or [])
    if normalized_case not in case_ids:
        case_ids.append(normalized_case)
    selection["case_ids"] = sorted(case_ids)
    meta["state"] = "selected"
    write_json(directory / "meta.json", meta)
    outcome = read_json(directory / "outcome.json")
    outcome["selected_for_evolution"] = True
    write_json(directory / "outcome.json", outcome)
    if current_state != "selected":
        directory = move_observation(root, run_id, "selected")
    append_index(root, "selected", meta["run_id"], state="selected", case_id=normalized_case)
    return {"run_id": meta["run_id"], "state": "selected", "case_id": normalized_case, "path": directory.relative_to(root).as_posix()}


def iter_observations(root: Path, states: Sequence[str] = OBSERVATION_STATES) -> Iterable[dict[str, Any]]:
    base = observations_dir(root)
    for state in states:
        if state not in OBSERVATION_STATES:
            raise ObservationError(f"invalid observation state: {state}")
        directory = base / state
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                meta = read_json(child / "meta.json")
                outcome = read_json(child / "outcome.json") if (child / "outcome.json").is_file() else None
            except ObservationError:
                continue
            yield {"state": state, "directory": child, "meta": meta, "outcome": outcome}


def list_observations(
    root: Path,
    *,
    states: Sequence[str] = OBSERVATION_STATES,
    signal: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    normalized_signal = normalize_signal(signal) if signal else None
    rows: list[dict[str, Any]] = []
    for item in iter_observations(root, states):
        meta = item["meta"]
        signals = list(meta.get("signals") or [])
        if normalized_signal and normalized_signal not in signals:
            continue
        rows.append({
            "run_id": meta.get("run_id"),
            "state": item["state"],
            "status": meta.get("status"),
            "work_id": meta.get("work_id"),
            "kind": meta.get("kind"),
            "route": meta.get("route"),
            "harness_version": (meta.get("harness") or {}).get("version"),
            "started_at": meta.get("started_at"),
            "finished_at": meta.get("finished_at"),
            "signals": signals,
            "outcome": (item["outcome"] or {}).get("status"),
        })
    rows.sort(key=lambda row: str(row.get("started_at") or ""), reverse=True)
    return {"count": len(rows[: max(0, limit)]), "observations": rows[: max(0, limit)]}


def show_observation(root: Path, run_id: str) -> dict[str, Any]:
    item = load_observation(root, run_id)
    events_path = item["directory"] / "events.jsonl"
    return {
        "state": item["state"],
        "path": item["directory"].relative_to(root).as_posix(),
        "meta": item["meta"],
        "outcome": item["outcome"],
        "events_sha256": sha256_file(events_path) if events_path.is_file() else None,
    }


def directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def enforce_pending_cap(root: Path) -> list[str]:
    config = load_observability_config(root)
    max_pending = max(1, int(config.get("retention", {}).get("max_pending_runs", 200)))
    pending = observations_dir(root) / "pending"
    if not pending.is_dir():
        return []
    candidates = [path for path in pending.iterdir() if path.is_dir()]
    if len(candidates) <= max_pending:
        return []
    candidates.sort(key=lambda path: path.stat().st_mtime)
    removed: list[str] = []
    for path in candidates[: len(candidates) - max_pending]:
        try:
            meta = read_json(path / "meta.json")
        except ObservationError:
            meta = {"run_id": path.name, "status": "unknown"}
        if meta.get("status") == "running":
            continue
        shutil.rmtree(path)
        removed.append(path.name)
        append_index(root, "pruned", path.name, reason="pending_cap")
    return removed


def prune_observations(root: Path, *, apply: bool) -> dict[str, Any]:
    config = load_observability_config(root)
    retention = config.get("retention", {})
    now = datetime.now().astimezone()
    plans: list[dict[str, Any]] = []
    for item in iter_observations(root, ("pending", "flagged")):
        meta = item["meta"]
        state = item["state"]
        reference = parse_time(meta.get("finished_at") or meta.get("started_at"))
        if reference is None:
            continue
        if meta.get("status") == "running":
            days = int(retention.get("stale_running_days", 7))
            reason = "stale_running"
        else:
            days = int(retention.get(f"{state}_days", 30 if state == "pending" else 180))
            reason = f"{state}_retention"
        if reference + timedelta(days=max(0, days)) > now:
            continue
        plans.append({
            "run_id": meta.get("run_id"),
            "state": state,
            "path": item["directory"].relative_to(root).as_posix(),
            "reason": reason,
            "size_bytes": directory_size(item["directory"]),
        })
    removed: list[str] = []
    if apply:
        for plan in plans:
            path = root / plan["path"]
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(str(plan["run_id"]))
                append_index(root, "pruned", str(plan["run_id"]), reason=plan["reason"])
        removed.extend(enforce_pending_cap(root))
    return {"apply": apply, "planned": plans, "removed": sorted(set(removed))}


def status(root: Path) -> dict[str, Any]:
    init_runtime(root)
    counts = {state: 0 for state in OBSERVATION_STATES}
    running = 0
    flagged_signals: dict[str, int] = {}
    total_bytes = 0
    for item in iter_observations(root):
        counts[item["state"]] += 1
        total_bytes += directory_size(item["directory"])
        if item["meta"].get("status") == "running":
            running += 1
        for signal in item["meta"].get("signals") or []:
            flagged_signals[str(signal)] = flagged_signals.get(str(signal), 0) + 1
    return {
        "mode": load_observability_config(root).get("mode"),
        "counts": counts,
        "running": running,
        "total_bytes": total_bytes,
        "signals": dict(sorted(flagged_signals.items(), key=lambda pair: (-pair[1], pair[0]))),
    }


def parse_json_argument(value: str | None, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return dict(default or {})
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ObservationError(f"invalid JSON argument: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ObservationError("JSON argument must be an object")
    return parsed


def parse_evidence(values: Sequence[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in values:
        path, separator, digest = value.partition(":")
        result.append({"path": path, "sha256": digest if separator else ""})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root")

    init_p = sub.add_parser("init", help="initialize passive observation storage")
    root_arg(init_p)

    status_p = sub.add_parser("status", help="show observation counts; explicit inspection only")
    root_arg(status_p)

    start_p = sub.add_parser("start", help="start one passive observation")
    root_arg(start_p)
    start_p.add_argument("--work", required=True)
    start_p.add_argument("--task", required=True)
    start_p.add_argument("--kind", required=True)
    start_p.add_argument("--lane", required=True)
    start_p.add_argument("--entry", default="cs")
    start_p.add_argument("--route", required=True)
    start_p.add_argument("--model-profile", default="host-default")
    start_p.add_argument("--adapter", default="host-default")
    start_p.add_argument("--start-stage")
    start_p.add_argument("--repository-commit")
    start_p.add_argument("--run-id")

    event_p = sub.add_parser("event", help="append compact metadata to a running observation")
    root_arg(event_p)
    event_p.add_argument("--run", required=True)
    event_p.add_argument("--type", required=True)
    event_p.add_argument("--json", default="{}")

    end_p = sub.add_parser("end", help="finish an observation without triggering evolution")
    root_arg(end_p)
    end_p.add_argument("--run", required=True)
    end_p.add_argument("--status", choices=OUTCOMES, required=True)
    end_p.add_argument("--end-stage")
    end_p.add_argument("--validation-status", choices=VALIDATION_STATUSES, default="not_run")
    end_p.add_argument("--verifier-id")
    end_p.add_argument("--command")
    end_p.add_argument("--exit-code", type=int)
    end_p.add_argument("--evidence", action="append", default=[])
    end_p.add_argument("--issued-by", default="task-runner")
    end_p.add_argument("--signal", action="append", default=[])
    end_p.add_argument("--metrics-json", default="{}")
    end_p.add_argument("--note")

    flag_p = sub.add_parser("flag", help="mark a named observation as a possible Harness issue")
    root_arg(flag_p)
    flag_p.add_argument("--run", required=True)
    flag_p.add_argument("--signal", action="append", required=True)
    flag_p.add_argument("--note")

    list_p = sub.add_parser("list", help="list observations only when explicitly requested")
    root_arg(list_p)
    list_p.add_argument("--state", action="append", choices=OBSERVATION_STATES, default=[])
    list_p.add_argument("--signal")
    list_p.add_argument("--limit", type=int, default=50)

    show_p = sub.add_parser("show", help="show one named observation without dumping raw events")
    root_arg(show_p)
    show_p.add_argument("--run", required=True)

    prune_p = sub.add_parser("prune", help="plan or apply retention cleanup")
    root_arg(prune_p)
    prune_p.add_argument("--apply", action="store_true")

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
        elif args.command == "start":
            result = start_observation(
                root,
                work=args.work,
                task_id=args.task,
                kind=args.kind,
                lane=args.lane,
                entry=args.entry,
                route=args.route,
                model_profile=args.model_profile,
                adapter=args.adapter,
                start_stage=args.start_stage,
                repository_commit=args.repository_commit,
                run_id=args.run_id,
            )
        elif args.command == "event":
            result = append_event(root, args.run, args.type, parse_json_argument(args.json))
        elif args.command == "end":
            result = finish_observation(
                root,
                args.run,
                status=args.status,
                end_stage=args.end_stage,
                task_validation={
                    "status": args.validation_status,
                    "verifier_id": args.verifier_id,
                    "command": args.command,
                    "exit_code": args.exit_code,
                    "evidence": parse_evidence(args.evidence),
                    "issued_by": args.issued_by,
                },
                signals=args.signal,
                metrics=parse_json_argument(args.metrics_json),
                note=args.note,
            )
        elif args.command == "flag":
            result = flag_observation(root, args.run, signals=args.signal, note=args.note)
        elif args.command == "list":
            result = list_observations(
                root,
                states=args.state or OBSERVATION_STATES,
                signal=args.signal,
                limit=args.limit,
            )
        elif args.command == "show":
            result = show_observation(root, args.run)
        elif args.command == "prune":
            result = prune_observations(root, apply=args.apply)
        else:
            raise ObservationError(f"unsupported command: {args.command}")
    except (ObservationError, OSError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
