#!/usr/bin/env python3
"""First-class CodeStable Harness policy inventory and evolvability guard.

The Meta loop may change only policy entries that are explicitly whitelisted and
covered by registered fixtures. This module is deterministic and intentionally
contains no proposal-generation logic.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = 1
POLICY_STATUSES = {"whitelisted", "blocked", "draft", "retired"}
CHANGE_TYPES = {
    "prompt_copy",
    "workflow_routing",
    "retrieval_strategy",
    "workflow_policy",
    "playbook_entry",
    "gate_threshold",
    "artifact_schema",
    "runtime_tool",
}


class PolicyError(RuntimeError):
    """A policy registry, fixture coverage, or proposal invariant failed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, json_dump(value))


def normalize_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    if not normalized:
        raise PolicyError("identifier cannot be empty")
    return normalized[:128]


def normalize_relative(value: str) -> str:
    raw = value.replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise PolicyError(f"path must be a safe project-relative path: {value!r}")
    return path.as_posix()


def normalize_layer(value: Any) -> str:
    """Normalize historical plural aliases to the canonical fixture layer id."""
    layer = str(value).strip().lower()
    aliases = {"contracts": "contract", "routes": "routing", "regressions": "regression"}
    return aliases.get(layer, layer)


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.exists():
            raise PolicyError(f"project root does not exist: {root}")
        return root
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".codestable").is_dir() or (candidate / ".git").exists():
            return candidate
    return current


def cs_dir(root: Path) -> Path:
    return root / ".codestable"


def registry_path(root: Path) -> Path:
    return cs_dir(root) / "meta" / "policy-registry.json"


def fixture_index_path(root: Path) -> Path:
    return cs_dir(root) / "evals" / "fixtures" / "index.json"


def manifest_path(root: Path) -> Path:
    return cs_dir(root) / "harness" / "manifest.json"


def strategy_index_path(root: Path) -> Path:
    return cs_dir(root) / "meta" / "strategy-evidence.jsonl"


def load_registry(root: Path) -> dict[str, Any]:
    registry = read_json(registry_path(root))
    policies = registry.get("policies")
    if not isinstance(policies, list):
        raise PolicyError("policy registry must contain a policies array")
    return registry


def load_fixture_index(root: Path) -> dict[str, Any]:
    index = read_json(fixture_index_path(root))
    fixtures = index.get("fixtures")
    if not isinstance(fixtures, list):
        raise PolicyError("fixture index must contain a fixtures array")
    return index


def policy_map(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in load_registry(root)["policies"]:
        if not isinstance(raw, dict):
            raise PolicyError("policy entries must be objects")
        item = dict(raw)
        policy_id = str(item.get("id") or "").strip()
        if not policy_id or policy_id in result:
            raise PolicyError(f"invalid or duplicate policy id: {policy_id!r}")
        item["path"] = normalize_relative(str(item.get("path") or ""))
        result[policy_id] = item
    return result


def fixture_map(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in load_fixture_index(root)["fixtures"]:
        if not isinstance(raw, dict):
            raise PolicyError("fixture index entries must be objects")
        item = dict(raw)
        fixture_id = str(item.get("id") or "").strip()
        if not fixture_id or fixture_id in result:
            raise PolicyError(f"invalid or duplicate fixture id: {fixture_id!r}")
        item["path"] = normalize_relative(str(item.get("path") or ""))
        result[fixture_id] = item
    return result


def manifest_surface_map(root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(manifest_path(root))
    surfaces = manifest.get("editable_surfaces")
    if not isinstance(surfaces, list):
        raise PolicyError("Harness manifest must contain editable_surfaces")
    result: dict[str, dict[str, Any]] = {}
    for raw in surfaces:
        if not isinstance(raw, dict):
            raise PolicyError("Harness surfaces must be objects")
        item = dict(raw)
        surface_id = str(item.get("id") or "").strip()
        if not surface_id or surface_id in result:
            raise PolicyError(f"invalid or duplicate surface id: {surface_id!r}")
        item["path"] = normalize_relative(str(item.get("path") or ""))
        result[surface_id] = item
    return result


def fixture_document(root: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    path = root / normalize_relative(str(fixture.get("path") or ""))
    return read_json(path)


def audit_policies(root: Path) -> dict[str, Any]:
    policies = policy_map(root)
    fixtures = fixture_map(root)
    surfaces = manifest_surface_map(root)
    issues: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}

    for policy_id, policy in sorted(policies.items()):
        status = str(policy.get("status") or "").strip()
        if status not in POLICY_STATUSES:
            issues.append({"severity": "error", "policy_id": policy_id, "code": "invalid_status", "detail": status})
        surface_id = str(policy.get("surface_id") or "").strip()
        surface = surfaces.get(surface_id)
        if surface is None:
            issues.append({"severity": "error", "policy_id": policy_id, "code": "missing_surface", "detail": surface_id})
        elif surface.get("path") != policy.get("path"):
            issues.append({"severity": "error", "policy_id": policy_id, "code": "surface_path_mismatch", "detail": {"registry": policy.get("path"), "manifest": surface.get("path")}})
        if not (root / str(policy["path"])).is_file():
            issues.append({"severity": "error", "policy_id": policy_id, "code": "missing_policy_file", "detail": policy["path"]})

        allowed = policy.get("allowed_change_types")
        if not isinstance(allowed, list) or not allowed:
            issues.append({"severity": "error", "policy_id": policy_id, "code": "missing_change_types"})
            allowed = []
        for change_type in allowed:
            if change_type not in CHANGE_TYPES:
                issues.append({"severity": "error", "policy_id": policy_id, "code": "unknown_change_type", "detail": change_type})
        checkpoints = policy.get("owner_checkpoint")
        if not isinstance(checkpoints, dict):
            issues.append({"severity": "error", "policy_id": policy_id, "code": "missing_owner_checkpoint_map"})
            checkpoints = {}
        for change_type in allowed:
            if change_type not in checkpoints or not isinstance(checkpoints.get(change_type), bool):
                issues.append({"severity": "error", "policy_id": policy_id, "code": "missing_owner_checkpoint_rule", "detail": change_type})

        declared_fixture_ids = policy.get("fixture_ids")
        if not isinstance(declared_fixture_ids, list):
            declared_fixture_ids = []
        valid_fixture_ids: list[str] = []
        covered_layers: set[str] = set()
        for fixture_id in declared_fixture_ids:
            fixture = fixtures.get(str(fixture_id))
            if fixture is None:
                issues.append({"severity": "error", "policy_id": policy_id, "code": "unknown_fixture", "detail": fixture_id})
                continue
            if policy_id not in set(str(value) for value in fixture.get("covers_policies") or []):
                issues.append({"severity": "error", "policy_id": policy_id, "code": "fixture_missing_backlink", "detail": fixture_id})
                continue
            fixture_path = root / str(fixture["path"])
            if not fixture_path.is_file():
                issues.append({"severity": "error", "policy_id": policy_id, "code": "missing_fixture_file", "detail": fixture["path"]})
                continue
            try:
                document = fixture_document(root, fixture)
            except PolicyError as exc:
                issues.append({"severity": "error", "policy_id": policy_id, "code": "invalid_fixture_file", "detail": str(exc)})
                continue
            if document.get("id") != fixture_id:
                issues.append({"severity": "error", "policy_id": policy_id, "code": "fixture_id_mismatch", "detail": fixture_id})
                continue
            if document.get("status") != "active":
                issues.append({"severity": "error", "policy_id": policy_id, "code": "fixture_not_active", "detail": fixture_id})
                continue
            valid_fixture_ids.append(str(fixture_id))
            covered_layers.update(normalize_layer(value) for value in fixture.get("layers") or [])
            covered_layers.update(normalize_layer(value) for value in document.get("layers") or [])

        required_layers = {normalize_layer(value) for value in policy.get("required_layers") or []}
        missing_layers = sorted(required_layers - covered_layers)
        if status == "whitelisted" and not valid_fixture_ids:
            issues.append({"severity": "error", "policy_id": policy_id, "code": "whitelisted_without_fixture"})
        if status == "whitelisted" and missing_layers:
            issues.append({"severity": "error", "policy_id": policy_id, "code": "missing_required_fixture_layers", "detail": missing_layers})
        coverage[policy_id] = {
            "status": status,
            "fixture_ids": sorted(valid_fixture_ids),
            "required_layers": sorted(required_layers),
            "covered_layers": sorted(covered_layers),
            "evolvable": status == "whitelisted" and bool(valid_fixture_ids) and not missing_layers,
        }

    # Every fixture backlink must point to a real policy.
    for fixture_id, fixture in sorted(fixtures.items()):
        for policy_id in fixture.get("covers_policies") or []:
            if str(policy_id) not in policies:
                issues.append({"severity": "error", "fixture_id": fixture_id, "code": "fixture_unknown_policy", "detail": policy_id})

    errors = [item for item in issues if item.get("severity") == "error"]
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": load_registry(root).get("registry_id"),
        "policy_count": len(policies),
        "fixture_count": len(fixtures),
        "coverage": coverage,
        "issues": issues,
        "ok": not errors,
        "policy_registry_sha256": sha256_file(registry_path(root)),
        "fixture_index_sha256": sha256_file(fixture_index_path(root)),
    }


def require_clean_audit(root: Path) -> dict[str, Any]:
    audit = audit_policies(root)
    if not audit["ok"]:
        details = "; ".join(f"{item.get('policy_id') or item.get('fixture_id')}:{item['code']}" for item in audit["issues"][:12])
        raise PolicyError(f"policy/fixture audit failed: {details}")
    return audit


def proposal_requirements(
    root: Path,
    *,
    policy_ids: Sequence[str],
    change_type: str,
    fixture_ids: Sequence[str],
) -> dict[str, Any]:
    audit = require_clean_audit(root)
    policies = policy_map(root)
    fixtures = fixture_map(root)
    selected_policies = list(dict.fromkeys(str(value).strip() for value in policy_ids if str(value).strip()))
    selected_fixtures = list(dict.fromkeys(str(value).strip() for value in fixture_ids if str(value).strip()))
    normalized_change = change_type.strip()
    if normalized_change not in CHANGE_TYPES:
        raise PolicyError(f"unknown proposal change type: {change_type}")
    if not selected_policies:
        raise PolicyError("proposal must declare at least one policy id")
    if not selected_fixtures:
        raise PolicyError("proposal must declare fixture coverage")
    missing_policies = [policy_id for policy_id in selected_policies if policy_id not in policies]
    if missing_policies:
        raise PolicyError(f"unknown policy ids: {missing_policies}")
    missing_fixtures = [fixture_id for fixture_id in selected_fixtures if fixture_id not in fixtures]
    if missing_fixtures:
        raise PolicyError(f"unknown fixture ids: {missing_fixtures}")

    owner_required = False
    surface_ids: list[str] = []
    coverage: dict[str, list[str]] = {}
    for policy_id in selected_policies:
        policy = policies[policy_id]
        if policy.get("status") != "whitelisted" or not audit["coverage"][policy_id]["evolvable"]:
            raise PolicyError(f"policy is not on the evolvable whitelist: {policy_id}")
        if normalized_change not in set(str(value) for value in policy.get("allowed_change_types") or []):
            raise PolicyError(f"change type {normalized_change!r} is not allowed for policy {policy_id}")
        matches = [
            fixture_id for fixture_id in selected_fixtures
            if policy_id in set(str(value) for value in fixtures[fixture_id].get("covers_policies") or [])
        ]
        if not matches:
            raise PolicyError(f"proposal fixture set does not cover policy: {policy_id}")
        required_layers = {normalize_layer(value) for value in policy.get("required_layers") or []}
        proposal_layers: set[str] = set()
        for fixture_id in matches:
            proposal_layers.update(normalize_layer(value) for value in fixtures[fixture_id].get("layers") or [])
        missing_layers = sorted(required_layers - proposal_layers)
        if missing_layers:
            raise PolicyError(
                f"proposal fixture set misses required layers for {policy_id}: {missing_layers}"
            )
        checkpoint_map = policy.get("owner_checkpoint") or {}
        owner_required = owner_required or bool(checkpoint_map.get(normalized_change))
        surface_id = str(policy.get("surface_id") or "")
        if surface_id and surface_id not in surface_ids:
            surface_ids.append(surface_id)
        coverage[policy_id] = sorted(matches)

    return {
        "policy_ids": selected_policies,
        "fixture_ids": selected_fixtures,
        "change_type": normalized_change,
        "surface_ids": surface_ids,
        "owner_checkpoint_required": owner_required,
        "promotion_authority": "owner" if owner_required else "agent",
        "coverage": coverage,
        "policy_registry_sha256": audit["policy_registry_sha256"],
        "fixture_index_sha256": audit["fixture_index_sha256"],
    }


def strategy_event(root: Path, *, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": now_iso(),
        "type": event_type,
        **payload,
    }
    append_jsonl(strategy_index_path(root), event)
    return event


def fixture_set_sha256(root: Path, fixture_ids: Sequence[str]) -> str:
    fixtures = fixture_map(root)
    records: list[dict[str, Any]] = []
    for fixture_id in sorted(set(fixture_ids)):
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            raise PolicyError(f"unknown fixture id: {fixture_id}")
        path = root / str(fixture["path"])
        records.append({"id": fixture_id, "path": fixture["path"], "sha256": sha256_file(path)})
    return sha256_bytes(canonical_json(records))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="audit policy whitelist and fixture coverage")
    audit.add_argument("--root")

    show = sub.add_parser("show", help="show one policy and its coverage")
    show.add_argument("--root")
    show.add_argument("--policy", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root_value = getattr(args, "root", None) or getattr(args, "global_root", None)
    try:
        root = find_project_root(explicit=root_value)
        if args.command == "audit":
            result = audit_policies(root)
        elif args.command == "show":
            policy_id = args.policy
            policies = policy_map(root)
            if policy_id not in policies:
                raise PolicyError(f"unknown policy: {policy_id}")
            audit = audit_policies(root)
            result = {"policy": policies[policy_id], "coverage": audit["coverage"].get(policy_id), "audit_ok": audit["ok"]}
        else:
            raise PolicyError(f"unsupported command: {args.command}")
    except (PolicyError, OSError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
