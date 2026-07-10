#!/usr/bin/env python3
"""Trusted evaluator boundary for CodeStable Harness evolution.

This tool creates immutable evaluation challenges and imports only aggregate
results authenticated by an evaluator-only HMAC key. Candidate workspaces must
not receive that key, the private held-out tasks, or evaluator implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cs_policy  # type: ignore

SCHEMA_VERSION = 3
DEFAULT_KEY_ENV = "CODESTABLE_EVALUATOR_KEY"
DEFAULT_KEY_ID_ENV = "CODESTABLE_EVALUATOR_KEY_ID"
MUTABLE_CANDIDATE_FIELDS = {"status", "promoted_version"}
IMMUTABLE_CHALLENGE_FIELDS = (
    "schema_version",
    "challenge_id",
    "case_id",
    "candidate_id",
    "nonce",
    "baseline_version",
    "baseline_content_sha256",
    "candidate_content_sha256",
    "candidate_definition_sha256",
    "protocol_sha256",
    "meta_context",
    "locks",
    "required_splits",
    "repeats",
    "holdout_visibility",
    "created_at",
)
FORBIDDEN_RESULT_KEYS = {
    "tasks",
    "task_results",
    "task_traces",
    "traces",
    "raw_trace",
    "raw_prompt",
    "prompt",
    "messages",
    "source_code",
    "diff",
    "patch",
    "private_holdout",
    "held_out_tasks",
    "secrets",
    "credentials",
}


class EvaluationError(RuntimeError):
    """An evaluator integrity or schema invariant was violated."""


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        raise EvaluationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json_dump(data))


def normalize_id(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    if not result:
        raise EvaluationError("identifier cannot be empty")
    return result[:96]


def normalize_relative(value: str) -> str:
    raw = value.replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    relative = Path(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        raise EvaluationError(f"path must be a safe project-relative path: {value!r}")
    return relative.as_posix()


def candidate_definition(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return the immutable candidate definition, excluding lifecycle fields."""
    return {
        key: value
        for key, value in candidate.items()
        if key not in MUTABLE_CANDIDATE_FIELDS
    }


def candidate_definition_sha256(candidate: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(candidate_definition(candidate)))


def immutable_challenge_payload(challenge: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in IMMUTABLE_CHALLENGE_FIELDS if field not in challenge]
    if missing:
        raise EvaluationError(f"evaluation challenge is missing immutable fields: {missing}")
    return {field: challenge[field] for field in IMMUTABLE_CHALLENGE_FIELDS}


def challenge_sha256(challenge: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(immutable_challenge_payload(challenge)))


def verify_challenge_integrity(challenge: dict[str, Any]) -> str:
    expected = challenge_sha256(challenge)
    actual = str(challenge.get("challenge_sha256") or "")
    if not actual or not hmac.compare_digest(actual, expected):
        raise EvaluationError("evaluation challenge immutable fields were modified")
    return expected


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.exists():
            raise EvaluationError(f"project root does not exist: {root}")
        return root
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".codestable").is_dir() or (candidate / ".git").exists():
            return candidate
    return current


def cs_dir(root: Path) -> Path:
    return root / ".codestable"


def case_dir(root: Path, case_id: str) -> Path:
    path = cs_dir(root) / "evolution" / "cases" / normalize_id(case_id)
    if not path.is_dir():
        raise EvaluationError(f"unknown evolution case: {case_id}")
    return path


def candidate_dir(root: Path, case_id: str, candidate_id: str) -> Path:
    path = case_dir(root, case_id) / "candidates" / normalize_id(candidate_id)
    if not path.is_dir():
        raise EvaluationError(f"unknown candidate: {candidate_id}")
    return path


def protocol_path(root: Path) -> Path:
    return cs_dir(root) / "evals" / "protocol.json"


def protocol_hash(root: Path) -> str:
    return sha256_file(protocol_path(root))


def load_protocol(root: Path) -> dict[str, Any]:
    protocol = read_json(protocol_path(root))
    required = protocol.get("required_splits")
    if not isinstance(required, list) or set(required) != {"held_in", "held_out", "safety"}:
        raise EvaluationError("evaluation protocol must require held_in, held_out and safety")
    trusted = protocol.get("trusted_results")
    if not isinstance(trusted, dict) or trusted.get("require_signature") is not True:
        raise EvaluationError("evaluation protocol must require signed results")
    if trusted.get("algorithm") != "hmac-sha256":
        raise EvaluationError("unsupported trusted result algorithm")
    return protocol


def challenge_dir(root: Path, case_id: str, candidate_id: str) -> Path:
    return case_dir(root, case_id) / "evaluations" / normalize_id(candidate_id)


def load_harness_manifest(root: Path) -> dict[str, Any]:
    manifest = read_json(cs_dir(root) / "harness" / "manifest.json")
    surfaces = manifest.get("editable_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise EvaluationError("Harness manifest has no editable surfaces")
    return manifest


def harness_surface_map(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for raw in load_harness_manifest(root)["editable_surfaces"]:
        if not isinstance(raw, dict):
            raise EvaluationError("each Harness editable surface must be an object")
        item = dict(raw)
        surface_id = str(item.get("id") or "").strip()
        relative = normalize_relative(str(item.get("path") or ""))
        if not surface_id or surface_id in result:
            raise EvaluationError(f"invalid or duplicate Harness surface id: {surface_id!r}")
        if relative in paths:
            raise EvaluationError(f"duplicate Harness editable surface path: {relative}")
        item["path"] = relative
        result[surface_id] = item
        paths.add(relative)
    return result


def live_harness_content_sha256(root: Path) -> str:
    records: list[dict[str, Any]] = []
    for surface in sorted(harness_surface_map(root).values(), key=lambda item: str(item["path"])):
        relative = str(surface["path"])
        source = root / relative
        if not source.is_file() or source.is_symlink():
            raise EvaluationError(f"missing or unsafe live Harness surface: {relative}")
        records.append({
            "surface_id": str(surface["id"]),
            "path": relative,
            "sha256": sha256_file(source),
        })
    return sha256_bytes(canonical_json(records))


def overlay_file_paths(overlay: Path) -> set[str]:
    if not overlay.is_dir():
        raise EvaluationError(f"candidate overlay directory is missing: {overlay}")
    result: set[str] = set()
    for item in overlay.rglob("*"):
        if item.is_symlink():
            raise EvaluationError(f"candidate overlay contains a symlink: {item}")
        if item.is_file():
            result.add(normalize_relative(item.relative_to(overlay).as_posix()))
    return result


def verify_local_candidate_lock(root: Path, case_id: str, candidate_id: str) -> dict[str, Any]:
    """Verify baseline, candidate bytes, proposal provenance, and validity evidence."""
    normalized_case = normalize_id(case_id)
    normalized_candidate = normalize_id(candidate_id)
    case = read_json(case_dir(root, normalized_case) / "case.json")
    candidate_root = candidate_dir(root, normalized_case, normalized_candidate)
    candidate = read_json(candidate_root / "manifest.json")

    baseline_version = str(case.get("baseline_version") or "")
    baseline_content = str(case.get("baseline_content_sha256") or "")
    if not baseline_version or not baseline_content:
        raise EvaluationError("evolution case has no exact baseline Harness identity")
    registry = read_json(cs_dir(root) / "harness" / "registry.json")
    if str(registry.get("active_version") or "") != baseline_version:
        raise EvaluationError("active Harness version no longer matches the evolution case baseline")
    if live_harness_content_sha256(root) != baseline_content:
        raise EvaluationError("live Harness content no longer matches the evolution case baseline")

    metadata = candidate.get("meta") if isinstance(candidate.get("meta"), dict) else None
    if not isinstance(metadata, dict):
        raise EvaluationError("candidate has no Meta proposal provenance")
    owner_required = bool(metadata.get("owner_checkpoint_required"))
    authority = "owner" if owner_required else "agent"
    checks = {
        "candidate.case_id": (candidate.get("case_id"), normalized_case),
        "candidate.candidate_id": (candidate.get("candidate_id"), normalized_candidate),
        "candidate.parent_version": (candidate.get("parent_version"), baseline_version),
        "candidate.parent_content_sha256": (candidate.get("parent_content_sha256"), baseline_content),
        "candidate.promotion_gate_required": (candidate.get("promotion_gate_required"), owner_required),
        "candidate.promotion_authority": (candidate.get("promotion_authority"), authority),
        "meta.promotion_authority": (metadata.get("promotion_authority"), authority),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise EvaluationError(f"candidate manifest lock mismatch: {label}")

    # Re-run the first-class policy/fixture whitelist check. No fixture coverage means no candidate.
    try:
        requirements = cs_policy.proposal_requirements(
            root,
            policy_ids=[str(value) for value in metadata.get("policy_ids") or []],
            change_type=str(metadata.get("change_type") or ""),
            fixture_ids=[str(value) for value in metadata.get("fixture_ids") or []],
        )
    except cs_policy.PolicyError as exc:
        raise EvaluationError(str(exc)) from exc
    for field in ("policy_registry_sha256", "fixture_index_sha256", "promotion_authority", "owner_checkpoint_required"):
        if metadata.get(field) != requirements.get(field):
            raise EvaluationError(f"candidate policy evidence is stale or mismatched: {field}")

    proposal_path = root / normalize_relative(str(metadata.get("proposal_path") or ""))
    variant_path = root / normalize_relative(str(metadata.get("variant_path") or ""))
    if not proposal_path.is_file() or sha256_file(proposal_path) != metadata.get("proposal_sha256"):
        raise EvaluationError("agent-authored proposal evidence is missing or modified")
    if not variant_path.is_file() or sha256_file(variant_path) != metadata.get("variant_sha256"):
        raise EvaluationError("agent-authored variant evidence is missing or modified")

    validity = metadata.get("validity") if isinstance(metadata.get("validity"), dict) else None
    if not isinstance(validity, dict) or validity.get("status") != "pass":
        raise EvaluationError("candidate has not passed the validity pre-pass")
    validity_path = root / normalize_relative(str(validity.get("path") or ""))
    if not validity_path.is_file() or sha256_file(validity_path) != validity.get("sha256"):
        raise EvaluationError("validity pre-pass evidence is missing or modified")
    validity_document = read_json(validity_path)
    if validity_document.get("status") != "pass" or validity_document.get("can_support_promotion") is not True:
        raise EvaluationError("validity pre-pass cannot support promotion")
    if validity_document.get("fixture_set_sha256") != validity.get("fixture_set_sha256"):
        raise EvaluationError("validity fixture set hash disagrees with the candidate")
    if validity_document.get("measurement_labels") != validity.get("measurement_labels"):
        raise EvaluationError("validity measurement labels disagree with the candidate")

    changes = candidate.get("changes")
    if not isinstance(changes, list) or not changes:
        raise EvaluationError("candidate manifest must declare at least one change")
    expected_candidate_content = sha256_bytes(canonical_json(changes))
    if candidate.get("candidate_content_sha256") != expected_candidate_content:
        raise EvaluationError("candidate content hash does not match its declared changes")

    surfaces = harness_surface_map(root)
    declared_paths: set[str] = set()
    declared_ids: set[str] = set()
    overlay = candidate_root / "overlay"
    for change in changes:
        if not isinstance(change, dict):
            raise EvaluationError("candidate change entries must be objects")
        surface_id = str(change.get("surface_id") or "")
        relative = normalize_relative(str(change.get("path") or ""))
        if surface_id in declared_ids or relative in declared_paths:
            raise EvaluationError("candidate changes contain duplicate surfaces or paths")
        surface = surfaces.get(surface_id)
        if surface is None or surface.get("path") != relative:
            raise EvaluationError(f"candidate change is not an allowed editable surface: {relative}")
        baseline_file = root / relative
        candidate_file = overlay / relative
        if not baseline_file.is_file() or baseline_file.is_symlink():
            raise EvaluationError(f"candidate baseline surface is missing or unsafe: {relative}")
        if not candidate_file.is_file() or candidate_file.is_symlink():
            raise EvaluationError(f"candidate overlay surface is missing or unsafe: {relative}")
        if sha256_file(baseline_file) != change.get("base_sha256"):
            raise EvaluationError(f"candidate baseline surface hash changed: {relative}")
        if sha256_file(candidate_file) != change.get("candidate_sha256"):
            raise EvaluationError(f"candidate overlay surface hash changed: {relative}")
        declared_ids.add(surface_id)
        declared_paths.add(relative)
    actual_paths = overlay_file_paths(overlay)
    if actual_paths != declared_paths:
        raise EvaluationError(
            "candidate overlay files do not exactly match declared changes; "
            f"extra={sorted(actual_paths - declared_paths)}, missing={sorted(declared_paths - actual_paths)}"
        )

    meta_context = {
        "campaign_id": metadata.get("campaign_id"),
        "policy_ids": requirements["policy_ids"],
        "fixture_ids": requirements["fixture_ids"],
        "change_type": requirements["change_type"],
        "promotion_authority": authority,
        "owner_checkpoint_required": owner_required,
        "proposal_sha256": metadata.get("proposal_sha256"),
        "variant_sha256": metadata.get("variant_sha256"),
        "hypothesis_sha256": (metadata.get("hypothesis") or {}).get("sha256"),
        "hypothesis_commit": (metadata.get("hypothesis") or {}).get("provenance_commit"),
        "validity_sha256": validity.get("sha256"),
        "prepass_sha256": validity_document.get("prepass_sha256"),
        "fixture_set_sha256": validity_document.get("fixture_set_sha256"),
        "measurement_labels": validity_document.get("measurement_labels") or {},
        "policy_registry_sha256": requirements["policy_registry_sha256"],
        "fixture_index_sha256": requirements["fixture_index_sha256"],
    }
    return {
        "baseline_version": baseline_version,
        "baseline_content_sha256": baseline_content,
        "candidate_content_sha256": expected_candidate_content,
        "candidate_definition_sha256": candidate_definition_sha256(candidate),
        "meta_context": meta_context,
    }


def verify_challenge_locks(
    root: Path,
    case_id: str,
    candidate_id: str,
    challenge: dict[str, Any],
) -> dict[str, Any]:
    verify_challenge_integrity(challenge)
    local = verify_local_candidate_lock(root, case_id, candidate_id)
    checks = {
        "case_id": (challenge.get("case_id"), normalize_id(case_id)),
        "candidate_id": (challenge.get("candidate_id"), normalize_id(candidate_id)),
        "baseline_version": (challenge.get("baseline_version"), local["baseline_version"]),
        "baseline_content_sha256": (
            challenge.get("baseline_content_sha256"),
            local["baseline_content_sha256"],
        ),
        "candidate_content_sha256": (
            challenge.get("candidate_content_sha256"),
            local["candidate_content_sha256"],
        ),
        "candidate_definition_sha256": (
            challenge.get("candidate_definition_sha256"),
            local["candidate_definition_sha256"],
        ),
        "meta_context": (challenge.get("meta_context"), local["meta_context"]),
        "protocol_sha256": (challenge.get("protocol_sha256"), protocol_hash(root)),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise EvaluationError(f"evaluation challenge lock is stale or modified: {label}")
    return local


def create_challenge(
    root: Path,
    *,
    case_id: str,
    candidate_id: str,
    model_profile: str,
    adapter: str,
    evaluator: str,
    budget: str,
    challenge_id: str | None = None,
) -> dict[str, Any]:
    lock = verify_local_candidate_lock(root, case_id, candidate_id)
    protocol = load_protocol(root)
    values = {
        "model_profile": model_profile.strip(),
        "adapter": adapter.strip(),
        "evaluator": evaluator.strip(),
        "budget": budget.strip(),
    }
    if any(not value for value in values.values()):
        raise EvaluationError("model profile, adapter, evaluator and budget locks are required")
    directory = challenge_dir(root, case_id, candidate_id)
    directory.mkdir(parents=True, exist_ok=True)
    challenge_path = directory / "challenge.json"
    if challenge_path.exists():
        raise EvaluationError(f"challenge already exists for candidate: {candidate_id}")
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    identifier = normalize_id(challenge_id or f"eval-{timestamp}-{candidate_id}")
    challenge = {
        "schema_version": SCHEMA_VERSION,
        "challenge_id": identifier,
        "case_id": normalize_id(case_id),
        "candidate_id": normalize_id(candidate_id),
        "nonce": secrets.token_hex(32),
        **lock,
        "protocol_sha256": protocol_hash(root),
        "locks": values,
        "required_splits": protocol["required_splits"],
        "repeats": int(protocol.get("repeats", 3)),
        "holdout_visibility": protocol.get("holdout", {}).get("visibility"),
        "created_at": now_iso(),
        "status": "open",
    }
    challenge["challenge_sha256"] = challenge_sha256(challenge)
    write_json(challenge_path, challenge)
    template = result_template(challenge)
    write_json(directory / "result-template.json", template)
    return {
        "challenge": challenge,
        "template_path": (directory / "result-template.json").relative_to(root).as_posix(),
    }

def result_template(challenge: dict[str, Any]) -> dict[str, Any]:
    empty_split = {
        "baseline": {"pass_count": 0, "total": 0, "metrics": {}},
        "candidate": {"pass_count": 0, "total": 0, "metrics": {}},
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "challenge": {
            "id": challenge["challenge_id"],
            "sha256": challenge["challenge_sha256"],
            "nonce": challenge["nonce"],
        },
        "case_id": challenge["case_id"],
        "candidate_id": challenge["candidate_id"],
        "baseline_version": challenge["baseline_version"],
        "baseline_content_sha256": challenge["baseline_content_sha256"],
        "candidate_content_sha256": challenge["candidate_content_sha256"],
        "candidate_definition_sha256": challenge["candidate_definition_sha256"],
        "protocol_sha256": challenge["protocol_sha256"],
        "locks": challenge["locks"],
        "evaluator_id": challenge["locks"]["evaluator"],
        "repeats": challenge["repeats"],
        "splits": {
            name: json.loads(json.dumps(empty_split))
            for name in challenge["required_splits"]
        },
        "validity": {
            "status": "pass",
            "prepass_sha256": challenge["meta_context"]["prepass_sha256"],
            "fixture_set_sha256": challenge["meta_context"]["fixture_set_sha256"],
            "measurement_labels": challenge["meta_context"]["measurement_labels"],
        },
        "issued_at": None,
        "signature": {
            "algorithm": "hmac-sha256",
            "key_id": None,
            "value": None,
        },
    }


def unsigned_payload(payload: dict[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(payload))
    copied.pop("signature", None)
    return copied


def sign_result_payload(payload: dict[str, Any], *, key: bytes, key_id: str) -> dict[str, Any]:
    if not key:
        raise EvaluationError("evaluator signing key is empty")
    signed = json.loads(json.dumps(payload))
    signed["issued_at"] = signed.get("issued_at") or now_iso()
    value = hmac.new(key, canonical_json(unsigned_payload(signed)), hashlib.sha256).hexdigest()
    signed["signature"] = {
        "algorithm": "hmac-sha256",
        "key_id": key_id,
        "value": value,
    }
    return signed


def key_from_environment(root: Path, *, explicit_env: str | None = None) -> tuple[bytes, str, str]:
    protocol = load_protocol(root)
    trusted = protocol.get("trusted_results", {})
    env_name = explicit_env or str(trusted.get("key_env") or DEFAULT_KEY_ENV)
    raw = os.environ.get(env_name)
    if raw is None:
        raise EvaluationError(f"trusted evaluator key is unavailable; set {env_name} only in the evaluator/import boundary")
    key_id_env = str(trusted.get("key_id_env") or DEFAULT_KEY_ID_ENV)
    key_id = os.environ.get(key_id_env, "local-evaluator")
    return raw.encode("utf-8"), key_id, env_name


def assert_no_forbidden_keys(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in FORBIDDEN_RESULT_KEYS:
                raise EvaluationError(f"trusted aggregate result contains forbidden raw field: {'.'.join((*path, str(key)))}")
            assert_no_forbidden_keys(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_forbidden_keys(child, (*path, str(index)))


def validate_score(value: dict[str, Any], *, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationError(f"{location} must be an object")
    passed = value.get("pass_count")
    total = value.get("total")
    if isinstance(passed, bool) or not isinstance(passed, int):
        raise EvaluationError(f"{location}.pass_count must be an integer")
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
        raise EvaluationError(f"{location}.total must be a positive integer")
    if passed < 0 or passed > total:
        raise EvaluationError(f"{location}.pass_count must be between 0 and total")
    metrics = value.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise EvaluationError(f"{location}.metrics must be an object")
    clean_metrics: dict[str, float] = {}
    for name, metric in metrics.items():
        if isinstance(metric, bool) or not isinstance(metric, (int, float)):
            raise EvaluationError(f"{location}.metrics.{name} must be numeric")
        clean_metrics[str(name)] = float(metric)
    return {"pass_count": passed, "total": total, "metrics": clean_metrics}


def verify_result_payload(
    root: Path,
    *,
    case_id: str,
    candidate_id: str,
    payload: dict[str, Any],
    key: bytes,
) -> dict[str, Any]:
    assert_no_forbidden_keys(payload)
    directory = challenge_dir(root, case_id, candidate_id)
    challenge = read_json(directory / "challenge.json")
    verify_challenge_locks(root, case_id, candidate_id, challenge)
    signature = payload.get("signature")
    if not isinstance(signature, dict):
        raise EvaluationError("trusted evaluator result has no signature")
    if signature.get("algorithm") != "hmac-sha256":
        raise EvaluationError("trusted evaluator result uses an unsupported signature algorithm")
    value = str(signature.get("value") or "")
    expected = hmac.new(key, canonical_json(unsigned_payload(payload)), hashlib.sha256).hexdigest()
    if not value or not hmac.compare_digest(value, expected):
        raise EvaluationError("trusted evaluator result signature is invalid")

    challenge_ref = payload.get("challenge")
    if not isinstance(challenge_ref, dict):
        raise EvaluationError("result.challenge must be an object")
    checks = {
        "challenge.id": (challenge_ref.get("id"), challenge.get("challenge_id")),
        "challenge.sha256": (challenge_ref.get("sha256"), challenge.get("challenge_sha256")),
        "challenge.nonce": (challenge_ref.get("nonce"), challenge.get("nonce")),
        "case_id": (payload.get("case_id"), challenge.get("case_id")),
        "candidate_id": (payload.get("candidate_id"), challenge.get("candidate_id")),
        "baseline_version": (payload.get("baseline_version"), challenge.get("baseline_version")),
        "baseline_content_sha256": (
            payload.get("baseline_content_sha256"),
            challenge.get("baseline_content_sha256"),
        ),
        "candidate_content_sha256": (
            payload.get("candidate_content_sha256"),
            challenge.get("candidate_content_sha256"),
        ),
        "candidate_definition_sha256": (
            payload.get("candidate_definition_sha256"),
            challenge.get("candidate_definition_sha256"),
        ),
        "protocol_sha256": (payload.get("protocol_sha256"), challenge.get("protocol_sha256")),
        "locks": (payload.get("locks"), challenge.get("locks")),
        "evaluator_id": (payload.get("evaluator_id"), challenge.get("locks", {}).get("evaluator")),
        "repeats": (payload.get("repeats"), challenge.get("repeats")),
        "validity": (
            payload.get("validity"),
            {
                "status": "pass",
                "prepass_sha256": challenge.get("meta_context", {}).get("prepass_sha256"),
                "fixture_set_sha256": challenge.get("meta_context", {}).get("fixture_set_sha256"),
                "measurement_labels": challenge.get("meta_context", {}).get("measurement_labels"),
            },
        ),
    }
    for name, (actual, expected_value) in checks.items():
        if actual != expected_value:
            raise EvaluationError(f"trusted result does not match challenge lock: {name}")

    required = set(challenge.get("required_splits") or [])
    splits = payload.get("splits")
    if not isinstance(splits, dict) or set(splits) != required:
        raise EvaluationError(f"trusted result splits must be exactly: {sorted(required)}")
    clean_splits: dict[str, Any] = {}
    for split in sorted(required):
        item = splits.get(split)
        if not isinstance(item, dict):
            raise EvaluationError(f"split {split} must be an object")
        clean_splits[split] = {
            "baseline": validate_score(item.get("baseline"), location=f"splits.{split}.baseline"),
            "candidate": validate_score(item.get("candidate"), location=f"splits.{split}.candidate"),
        }
    issued_at = parse_issued_at(payload.get("issued_at"))
    return {
        **unsigned_payload(payload),
        "issued_at": issued_at,
        "splits": clean_splits,
        "signature": {
            "algorithm": "hmac-sha256",
            "key_id": str(signature.get("key_id") or "unknown"),
            "value": value,
        },
    }


def parse_issued_at(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise EvaluationError("trusted result issued_at is required")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EvaluationError("trusted result issued_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise EvaluationError("trusted result issued_at must include a timezone")
    return text


def import_result(
    root: Path,
    *,
    case_id: str,
    candidate_id: str,
    result_file: Path,
    key: bytes | None = None,
) -> dict[str, Any]:
    directory = challenge_dir(root, case_id, candidate_id)
    if not directory.is_dir():
        raise EvaluationError("create an evaluation challenge before importing a result")
    challenge = read_json(directory / "challenge.json")
    verify_challenge_locks(root, case_id, candidate_id, challenge)
    if challenge.get("status") != "open":
        raise EvaluationError("evaluation challenge is not open")
    payload = read_json(result_file.expanduser().resolve())
    if key is None:
        key, _, _ = key_from_environment(root)
    verified = verify_result_payload(
        root,
        case_id=case_id,
        candidate_id=candidate_id,
        payload=payload,
        key=key,
    )
    verified_path = directory / "verified-result.json"
    if verified_path.exists():
        raise EvaluationError("a verified result is already imported for this challenge")
    write_json(verified_path, verified)
    challenge["status"] = "verified"
    challenge["verified_at"] = now_iso()
    challenge["result_sha256"] = sha256_file(verified_path)
    challenge["signing_key_id"] = verified["signature"]["key_id"]
    write_json(directory / "challenge.json", challenge)
    return {
        "case_id": normalize_id(case_id),
        "candidate_id": normalize_id(candidate_id),
        "challenge_id": challenge["challenge_id"],
        "verified": True,
        "result_path": verified_path.relative_to(root).as_posix(),
        "result_sha256": challenge["result_sha256"],
        "signing_key_id": challenge["signing_key_id"],
    }


def load_challenge(root: Path, case_id: str, candidate_id: str) -> dict[str, Any]:
    challenge = read_json(challenge_dir(root, case_id, candidate_id) / "challenge.json")
    verify_challenge_locks(root, case_id, candidate_id, challenge)
    return challenge


def load_verified_result(root: Path, case_id: str, candidate_id: str) -> dict[str, Any]:
    directory = challenge_dir(root, case_id, candidate_id)
    path = directory / "verified-result.json"
    result = read_json(path)
    challenge = load_challenge(root, case_id, candidate_id)
    if challenge.get("status") != "verified":
        raise EvaluationError("evaluation challenge is not verified")
    if challenge.get("result_sha256") != sha256_file(path):
        raise EvaluationError("verified evaluation result was modified after import")
    challenge_ref = result.get("challenge")
    if not isinstance(challenge_ref, dict):
        raise EvaluationError("verified result has no challenge reference")
    checks = {
        "challenge.id": (challenge_ref.get("id"), challenge.get("challenge_id")),
        "challenge.sha256": (challenge_ref.get("sha256"), challenge.get("challenge_sha256")),
        "challenge.nonce": (challenge_ref.get("nonce"), challenge.get("nonce")),
        "baseline_content_sha256": (
            result.get("baseline_content_sha256"),
            challenge.get("baseline_content_sha256"),
        ),
        "candidate_definition_sha256": (
            result.get("candidate_definition_sha256"),
            challenge.get("candidate_definition_sha256"),
        ),
        "validity": (
            result.get("validity"),
            {
                "status": "pass",
                "prepass_sha256": challenge.get("meta_context", {}).get("prepass_sha256"),
                "fixture_set_sha256": challenge.get("meta_context", {}).get("fixture_set_sha256"),
                "measurement_labels": challenge.get("meta_context", {}).get("measurement_labels"),
            },
        ),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise EvaluationError(f"verified result no longer matches its challenge: {label}")
    return result


def evaluation_status(root: Path, *, case_id: str, candidate_id: str) -> dict[str, Any]:
    directory = challenge_dir(root, case_id, candidate_id)
    if not directory.is_dir():
        return {"exists": False, "case_id": case_id, "candidate_id": candidate_id}
    challenge = read_json(directory / "challenge.json") if (directory / "challenge.json").is_file() else None
    if challenge is not None:
        verify_challenge_integrity(challenge)
    return {
        "exists": True,
        "case_id": normalize_id(case_id),
        "candidate_id": normalize_id(candidate_id),
        "challenge": challenge,
        "verified_result": (directory / "verified-result.json").is_file(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root")

    challenge_p = sub.add_parser("challenge", help="freeze one candidate evaluation request")
    root_arg(challenge_p)
    challenge_p.add_argument("--case", required=True)
    challenge_p.add_argument("--candidate", required=True)
    challenge_p.add_argument("--model-profile", required=True)
    challenge_p.add_argument("--adapter", required=True)
    challenge_p.add_argument("--evaluator", required=True)
    challenge_p.add_argument("--budget", required=True)
    challenge_p.add_argument("--challenge-id")

    template_p = sub.add_parser("template", help="show the evaluator result template for an existing challenge")
    root_arg(template_p)
    template_p.add_argument("--case", required=True)
    template_p.add_argument("--candidate", required=True)

    sign_p = sub.add_parser("sign", help="evaluator-only: sign an aggregate result JSON")
    root_arg(sign_p)
    sign_p.add_argument("--input", required=True)
    sign_p.add_argument("--output", required=True)
    sign_p.add_argument("--key-env")

    import_p = sub.add_parser("import", help="verify and import a signed aggregate result")
    root_arg(import_p)
    import_p.add_argument("--case", required=True)
    import_p.add_argument("--candidate", required=True)
    import_p.add_argument("--file", required=True)

    status_p = sub.add_parser("status", help="show one candidate evaluation status")
    root_arg(status_p)
    status_p.add_argument("--case", required=True)
    status_p.add_argument("--candidate", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root_value = getattr(args, "root", None) or getattr(args, "global_root", None)
    try:
        root = find_project_root(explicit=root_value)
        if args.command == "challenge":
            result = create_challenge(
                root,
                case_id=args.case,
                candidate_id=args.candidate,
                model_profile=args.model_profile,
                adapter=args.adapter,
                evaluator=args.evaluator,
                budget=args.budget,
                challenge_id=args.challenge_id,
            )
        elif args.command == "template":
            directory = challenge_dir(root, args.case, args.candidate)
            result = {"template": read_json(directory / "result-template.json")}
        elif args.command == "sign":
            payload = read_json(Path(args.input).expanduser().resolve())
            key, key_id, _ = key_from_environment(root, explicit_env=args.key_env)
            signed = sign_result_payload(payload, key=key, key_id=key_id)
            output = Path(args.output).expanduser().resolve()
            write_json(output, signed)
            result = {"signed": True, "output": str(output), "key_id": key_id}
        elif args.command == "import":
            result = import_result(
                root,
                case_id=args.case,
                candidate_id=args.candidate,
                result_file=Path(args.file),
            )
        elif args.command == "status":
            result = evaluation_status(root, case_id=args.case, candidate_id=args.candidate)
        else:
            raise EvaluationError(f"unsupported command: {args.command}")
    except (EvaluationError, OSError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
