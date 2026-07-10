#!/usr/bin/env python3
"""Install or upgrade the project-local CodeStable Compact runtime.

This script is intentionally host-independent and uses only the standard
library. Existing model/work data is never overwritten. With --upgrade,
shipped tools and reference rules are refreshed after a timestamped backup.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


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


def deep_merge(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in defaults.items():
        if key not in existing:
            merged[key] = value
        elif isinstance(value, dict) and isinstance(existing[key], dict):
            merged[key] = deep_merge(value, existing[key])
        else:
            merged[key] = existing[key]
    for key, value in existing.items():
        if key not in merged:
            merged[key] = value
    return merged


MANDATORY_NORMAL_EXCLUSIONS = (
    ".codestable/observations",
    ".codestable/evolution",
    ".codestable/evals",
    ".codestable/harness/versions",
    ".codestable/meta",
)


def safe_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def enforce_safe_boundaries(defaults: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    """Make the normal/maintenance split authoritative on every install.

    User preferences and unknown extension keys are preserved, but no supported
    config can opt normal work into observation reads, background evolution,
    unsigned evaluation, raw transcript capture, or automatic promotion.
    """
    merged = deep_merge(defaults, value)
    merged.pop("telemetry", None)
    merged["schema_version"] = 3

    context = merged.setdefault("context", {})
    configured = context.get("excluded_normal_roots")
    exclusions = [str(item) for item in configured] if isinstance(configured, list) else []
    context["excluded_normal_roots"] = list(dict.fromkeys((*MANDATORY_NORMAL_EXCLUSIONS, *exclusions)))

    observe = merged.setdefault("observability", {})
    observe.update({
        "mode": "passive",
        "best_effort": True,
        "read_during_normal_runs": False,
    })
    capture = observe.setdefault("capture", {})
    capture.update({
        "raw_prompts": False,
        "raw_model_responses": False,
        "source_or_diffs": False,
        "full_tool_output": False,
    })

    evolution = merged.setdefault("evolution", {})
    for obsolete in ("trigger", "campaign", "campaigns", "auto_promotion", "promotion_policy", "require_human_promotion_gate"):
        evolution.pop(obsolete, None)
    evolution.update({
        "mode": "manual",
        "run_during_normal_work": False,
        "auto_diagnose": False,
        "auto_propose": False,
        "auto_evaluate": False,
        "auto_promote": False,
        "require_selected_cases": True,
        "require_private_holdout": True,
        "require_validity_prepass": True,
        "require_fixture_covered_policy": True,
        "promotion_authority": "owner_checkpoint_by_policy",
    })

    meta = merged.setdefault("meta", {})
    meta["normal_runs_may_import_meta"] = False
    trigger = meta.setdefault("trigger", {})
    trigger["mode"] = "scan_only_by_default"
    trigger.setdefault("enabled", True)
    trigger["minimum_matching_signals"] = max(2, safe_positive_int(trigger.get("minimum_matching_signals"), 3))
    trigger["max_campaigns_per_scan"] = safe_positive_int(trigger.get("max_campaigns_per_scan"), 2)
    trigger["max_feedback_per_campaign"] = safe_positive_int(trigger.get("max_feedback_per_campaign"), 20)
    validity = meta.setdefault("validity", {})
    validity["minimum_stochastic_repeats"] = max(5, safe_positive_int(validity.get("minimum_stochastic_repeats"), 5))
    validity.update({
        "require_context_complete": True,
        "require_calibrated_scorer": True,
        "require_committed_hypothesis": True,
        "require_judge_isolation": True,
    })

    evaluator = merged.setdefault("evaluator", {})
    evaluator.update({
        "mode": "external_signed_aggregate",
        "require_signed_results": True,
        "signing_algorithm": "hmac-sha256",
        "private_holdout_location": "outside_candidate_workspace",
    })
    return merged


def migrate_config(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Upgrade legacy settings, then enforce passive/manual safety invariants."""
    migrated = dict(existing)
    try:
        schema_version = int(migrated.get("schema_version", 1))
    except (TypeError, ValueError):
        schema_version = 1

    legacy_telemetry = migrated.pop("telemetry", None)
    if schema_version < 2:
        observation = dict(defaults.get("observability", {}))
        if isinstance(legacy_telemetry, dict):
            observation = deep_merge(observation, {
                "enabled": bool(legacy_telemetry.get("enabled", True)),
                "retention": {
                    "pending_days": safe_positive_int(legacy_telemetry.get("retention_days"), 30),
                },
            })
        migrated["observability"] = observation
        old_evolution = migrated.get("evolution")
        enabled = bool(old_evolution.get("enabled", True)) if isinstance(old_evolution, dict) else True
        migrated["evolution"] = {**defaults.get("evolution", {}), "enabled": enabled}

    migration = migrated.setdefault("migration", {})
    if isinstance(migration, dict) and isinstance(legacy_telemetry, dict):
        migration.setdefault("legacy_telemetry_config", legacy_telemetry)
    migrated["schema_version"] = 3
    return enforce_safe_boundaries(defaults, migrated)


def merge_registry_array(defaults: dict[str, Any], existing: dict[str, Any], field: str) -> dict[str, Any]:
    """Refresh shipped entries by id while preserving project-local extensions."""
    merged = dict(existing)
    default_items = defaults.get(field) if isinstance(defaults.get(field), list) else []
    existing_items = existing.get(field) if isinstance(existing.get(field), list) else []
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in existing_items:
        if isinstance(item, dict) and str(item.get("id") or ""):
            key = str(item["id"])
            by_id[key] = item
            order.append(key)
    for item in default_items:
        if isinstance(item, dict) and str(item.get("id") or ""):
            key = str(item["id"])
            by_id[key] = item
            if key not in order:
                order.append(key)
    shipped_order = [str(item["id"]) for item in default_items if isinstance(item, dict) and str(item.get("id") or "")]
    custom_order = [key for key in order if key not in shipped_order]
    merged[field] = [by_id[key] for key in (*shipped_order, *custom_order)]
    for key, value in defaults.items():
        if key != field:
            merged[key] = value
    return merged


def relative_asset_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "project"


def should_refresh(relative: Path, upgrade: bool) -> bool:
    if not upgrade:
        return False
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == ".codestable" and parts[1] in {"reference", "tools"}:
        return True
    return relative.as_posix() in {
        ".codestable/harness/manifest.json",
        ".codestable/harness/README.md",
        ".codestable/evals/protocol.json",
        ".codestable/evals/README.md",
        ".codestable/evals/fixtures/index.json",
        ".codestable/observations/README.md",
        ".codestable/evolution/README.md",
        ".codestable/meta/README.md",
        ".codestable/meta/policy-registry.json",
        ".codestable/meta/trace.schema.json",
        ".codestable/meta/feedback.schema.json",
        ".codestable/meta/proposal.schema.json",
        ".codestable/meta/campaign.schema.json",
    }


def backup_file(target_root: Path, target: Path, backup_root: Path) -> str:
    relative = target.relative_to(target_root)
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, destination)
    return relative.as_posix()


def install(target_root: Path, upgrade: bool) -> dict[str, Any]:
    source_root = relative_asset_root()
    if not source_root.is_dir():
        raise RuntimeError(f"asset root not found: {source_root}")
    target_root = target_root.expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    backup_root = target_root / ".codestable" / "backups" / now_stamp()

    created: list[str] = []
    updated: list[str] = []
    preserved: list[str] = []
    backed_up: list[str] = []

    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        target = target_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        if relative.as_posix() == ".codestable/config.json" and target.exists():
            defaults = json.loads(source.read_text(encoding="utf-8"))
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    raise ValueError("config root is not an object")
            except (json.JSONDecodeError, ValueError):
                backed_up.append(backup_file(target_root, target, backup_root))
                atomic_write(target, json_dump(defaults))
                updated.append(relative.as_posix())
                continue
            merged = migrate_config(defaults, existing)
            if merged != existing:
                backed_up.append(backup_file(target_root, target, backup_root))
                atomic_write(target, json_dump(merged))
                updated.append(relative.as_posix())
            else:
                preserved.append(relative.as_posix())
            continue

        if relative.as_posix() in {
            ".codestable/evals/fixtures/index.json",
            ".codestable/meta/policy-registry.json",
        } and target.exists():
            defaults = json.loads(source.read_text(encoding="utf-8"))
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    raise ValueError("registry root is not an object")
            except (json.JSONDecodeError, ValueError):
                backed_up.append(backup_file(target_root, target, backup_root))
                atomic_write(target, json_dump(defaults))
                updated.append(relative.as_posix())
                continue
            field = "fixtures" if relative.as_posix().endswith("fixtures/index.json") else "policies"
            merged_registry = merge_registry_array(defaults, existing, field)
            if merged_registry != existing:
                backed_up.append(backup_file(target_root, target, backup_root))
                atomic_write(target, json_dump(merged_registry))
                updated.append(relative.as_posix())
            else:
                preserved.append(relative.as_posix())
            continue

        refresh = should_refresh(relative, upgrade)
        if target.exists() and not refresh:
            preserved.append(relative.as_posix())
            continue
        if target.exists() and refresh:
            backed_up.append(backup_file(target_root, target, backup_root))
            shutil.copy2(source, target)
            updated.append(relative.as_posix())
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            created.append(relative.as_posix())

        if target.suffix == ".py" and "tools" in target.parts:
            current_mode = target.stat().st_mode
            target.chmod(current_mode | stat.S_IXUSR)

    if not backed_up and backup_root.exists():
        shutil.rmtree(backup_root)

    return {
        "root": str(target_root),
        "created": created,
        "updated": updated,
        "preserved": preserved,
        "backup": str(backup_root) if backed_up else None,
        "backed_up": backed_up,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="target project root")
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="refresh shipped .codestable/reference and tools after backing them up",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = install(Path(args.root), args.upgrade)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
