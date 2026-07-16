#!/usr/bin/env python3
"""CodeStable Compact evidence-state control plane.

The Agent chooses its path. This tool owns deterministic task state, side-effect
boundaries, proof capture, risk-adaptive completion rules, context receipts and
archival. It does not prescribe a fixed software-development stage sequence.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

TASK_SCHEMA_VERSION = 2
CONTEXT_SCHEMA_VERSION = 2
EVIDENCE_SCHEMA_VERSION = 2
EVIDENCE_BINDING_SCHEMA_VERSION = 1
WORK_KINDS = ("feature", "issue", "refactor", "roadmap", "model")
ACTIONS = ("inspect", "propose", "execute", "verify", "learn")
RISK_LEVELS = (0, 1, 2, 3)
RISK_NAMES = {0: "trivial", 1: "local", 2: "cross_module", 3: "critical"}
WORK_STATUSES = ("active", "blocked", "partial", "done", "cancelled", "archived")
EVIDENCE_STATUSES = ("PASS", "FAIL", "BLOCKED", "PARTIAL")
LEDGER_KINDS = ("fact", "assumption", "risk", "change", "blocker")
RISK_SEVERITIES = ("low", "medium", "high", "critical")
STATE_BACKED_EVIDENCE = {
    "scope_inspect",
    "audit_ledger",
    "full_audit",
    "proposal",
    "invariant_contract",
}
ACCEPTANCE_SCOPED_EVIDENCE = {
    "targeted_test",
    "lightweight_review",
    "integration_test",
    "independent_review",
    "live_validation",
    "regression_fixture",
}
CORE_EVIDENCE_BINDINGS = (
    "source_snapshot_sha256",
    "registered_changes_sha256",
    "relevant_state_sha256",
    "proposal_sha256",
    "invariants_sha256",
    "acceptance_contract_sha256",
)
BINDING_DETAILS = {
    "source_snapshot_sha256": "an earlier source snapshot",
    "registered_changes_sha256": "an earlier registered change set",
    "relevant_state_sha256": "an earlier task-state snapshot",
    "proposal_sha256": "an earlier proposal",
    "invariants_sha256": "an earlier invariant contract",
    "acceptance_contract_sha256": "an earlier acceptance contract",
    "reviewed_diff_sha256": "an earlier reviewed diff",
    "artifact_set_sha256": "an earlier external artifact snapshot",
}
CRITICAL_SIDE_EFFECTS = {
    "destructive",
    "security",
    "permission",
    "persistent_data",
    "financial",
    "live_llm",
    "public_contract",
}
CODE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".c", ".h", ".cc", ".cpp", ".hpp", ".sh",
    ".sql", ".proto",
}
TEXT_SUFFIXES = {
    ".md", ".mdx", ".txt", ".rst", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".go", ".rs", ".java", ".kt", ".kts", ".rb", ".php", ".cs",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".sh", ".bash", ".zsh",
    ".fish", ".sql", ".graphql", ".proto", ".xml", ".html", ".css",
    ".scss", ".vue", ".svelte",
}
MANDATORY_NORMAL_CONTEXT_EXCLUSIONS = (
    ".codestable/observations",
    ".codestable/evolution",
    ".codestable/evals",
    ".codestable/harness/versions",
    ".codestable/meta",
)

RISK_REQUIREMENTS: dict[int, tuple[str, ...]] = {
    0: ("diff_check", "format_check"),
    1: ("scope_inspect", "targeted_test", "lightweight_review"),
    2: ("audit_ledger", "proposal", "integration_test", "independent_review", "proof"),
    3: (
        "full_audit",
        "invariant_contract",
        "live_validation",
        "rollback_proof",
        "independent_review",
        "regression_fixture",
    ),
}

REQUIRED_EVIDENCE_SOURCES: dict[str, frozenset[str]] = {
    "diff_check": frozenset({"command_execution"}),
    "format_check": frozenset({"command_execution"}),
    "scope_inspect": frozenset({"state_snapshot"}),
    "targeted_test": frozenset({"command_execution"}),
    "lightweight_review": frozenset({"artifact_record"}),
    "audit_ledger": frozenset({"state_snapshot"}),
    "proposal": frozenset({"state_snapshot"}),
    "integration_test": frozenset({"command_execution"}),
    "independent_review": frozenset({"artifact_record"}),
    "proof": frozenset({"proof_assembly"}),
    "full_audit": frozenset({"state_snapshot"}),
    "invariant_contract": frozenset({"state_snapshot"}),
    "live_validation": frozenset({"command_execution"}),
    "rollback_proof": frozenset({"artifact_record", "command_execution"}),
    "regression_fixture": frozenset({"command_execution"}),
}

RUNTIME_CONTROL_PREFIXES = (
    ".codestable/work/active/",
    ".codestable/work/archive/",
    ".codestable/observations/",
)
RUNTIME_CONTROL_FILES = {".codestable/work/archive-index.jsonl"}

ACTION_SECTIONS: dict[str, tuple[str, ...]] = {
    "inspect": ("Task contract", "Facts, assumptions and unknowns", "Risks and side effects"),
    "propose": ("Task contract", "Facts, assumptions and unknowns", "Proposed change"),
    "execute": ("Task contract", "Risks and side effects", "Changes"),
    "verify": ("Task contract", "Changes", "Evidence and completion"),
    "learn": ("Evidence and completion", "Learning"),
}

DEFAULT_CONFIG: dict[str, Any] = {
    "artifacts": {
        "mode": "evidence_state",
        "required_active_files": ["state.json", "work.md", "context.json", "evidence.jsonl"],
    },
    "control_plane": {
        "state_model": "evidence",
        "actions": list(ACTIONS),
        "responsibilities": ["owner", "harness", "reviewer"],
        "completion_authority": "harness",
        "risk_levels": {
            str(level): {
                "name": RISK_NAMES[level],
                "required_evidence": list(RISK_REQUIREMENTS[level]),
                "independent_reviewer": level >= 2,
                "rollback_required": level == 3,
            }
            for level in RISK_LEVELS
        },
    },
    "context": {
        "archive_default": "off",
        "excluded_normal_roots": [
            ".codestable/observations",
            ".codestable/evolution",
            ".codestable/evals",
            ".codestable/harness/versions",
            ".codestable/meta",
            ".codestable/feedback",
        ],
        "max_attention_lines": 80,
        "max_index_lines": 160,
        "max_search_hits": 5,
        "normal_roots": [".codestable/model", ".codestable/knowledge", ".codestable/work/active"],
        "reuse_unchanged_receipts": True,
    },
    "entry": {"mode": "auto", "route_summary": "compact"},
    "evaluator": {
        "mode": "external_signed_aggregate",
        "private_holdout_location": "outside_candidate_workspace",
        "require_signed_results": True,
        "signing_algorithm": "hmac-sha256",
        "signing_key_env": "CODESTABLE_EVALUATOR_KEY",
        "signing_key_id_env": "CODESTABLE_EVALUATOR_KEY_ID",
    },
    "evolution": {
        "auto_diagnose": False,
        "auto_evaluate": False,
        "auto_promote": False,
        "auto_propose": False,
        "enabled": True,
        "mode": "manual",
        "promotion_authority": "owner_checkpoint_by_policy",
        "require_fixture_covered_policy": True,
        "require_private_holdout": True,
        "require_selected_cases": True,
        "require_validity_prepass": True,
        "run_during_normal_work": False,
    },
    "execution": {
        "mode": "evidence_convergence",
        "path_control": "agent_autonomous_with_harness_boundaries",
    },
    "gates": {
        "pause_on": [
            "irreversible_or_destructive",
            "public_contract_choice",
            "security_boundary",
            "persistent_data_migration",
            "material_cost_or_availability",
            "accepted_decision_conflict",
            "unobservable_acceptance",
            "harness_promotion",
        ],
        "policy": "risk_and_evidence",
    },
    "meta": {
        "acceptance": {
            "required_gate_label": "measured",
            "required_quality_gates": ["policy_audit", "validity_prepass", "regression", "package"],
        },
        "budgets": {"max_evaluation_trials": 300, "max_open_campaigns": 5, "max_variants_per_campaign": 3},
        "enabled": True,
        "normal_runs_may_import_meta": False,
        "trigger": {
            "enabled": True,
            "max_campaigns_per_scan": 2,
            "max_feedback_per_campaign": 20,
            "minimum_matching_signals": 3,
            "mode": "scan_only_by_default",
        },
        "validity": {
            "minimum_stochastic_repeats": 5,
            "require_calibrated_scorer": True,
            "require_committed_hypothesis": True,
            "require_context_complete": True,
            "require_judge_isolation": True,
        },
    },
    "observability": {
        "best_effort": True,
        "capture": {
            "event_metadata": True,
            "full_tool_output": False,
            "raw_model_responses": False,
            "raw_prompts": False,
            "source_or_diffs": False,
            "user_corrections": True,
            "verification_evidence": True,
        },
        "enabled": True,
        "limits": {
            "max_event_payload_bytes": 8192,
            "max_events": 500,
            "max_run_size_kb": 256,
            "max_string_chars": 2048,
        },
        "mode": "passive",
        "read_during_normal_runs": False,
        "retention": {
            "flagged_days": 180,
            "max_pending_runs": 200,
            "pending_days": 30,
            "stale_running_days": 7,
        },
    },
    "schema_version": 3,
}


class RuntimeErrorWithHint(RuntimeError):
    """A deterministic control-plane invariant was violated."""


@dataclass(frozen=True)
class Candidate:
    path: Path
    reason: str
    sections: tuple[str, ...] = ()


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        raise RuntimeErrorWithHint(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeErrorWithHint(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeErrorWithHint(f"expected JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, json_dump(value))


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def deep_merge(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, default in defaults.items():
        if key not in existing:
            result[key] = default
        elif isinstance(default, dict) and isinstance(existing[key], dict):
            result[key] = deep_merge(default, existing[key])
        else:
            result[key] = existing[key]
    for key, value in existing.items():
        if key not in result:
            result[key] = value
    return result


def safe_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def enforce_safe_boundaries(value: dict[str, Any]) -> dict[str, Any]:
    """Preserve project preferences while restoring non-bypassable control boundaries."""
    merged = deep_merge(DEFAULT_CONFIG, value)
    merged.pop("telemetry", None)
    merged["schema_version"] = 3

    artifacts = merged.setdefault("artifacts", {})
    artifacts["mode"] = "evidence_state"
    configured_files = artifacts.get("required_active_files")
    required_files = list(configured_files) if isinstance(configured_files, list) else []
    artifacts["required_active_files"] = list(dict.fromkeys(
        ("state.json", "work.md", "context.json", "evidence.jsonl", *[str(item) for item in required_files])
    ))

    control = merged.setdefault("control_plane", {})
    control["state_model"] = "evidence"
    control["actions"] = list(ACTIONS)
    control["responsibilities"] = ["owner", "harness", "reviewer"]
    control["completion_authority"] = "harness"
    configured_levels = control.setdefault("risk_levels", {})
    for level in RISK_LEVELS:
        key = str(level)
        policy = configured_levels.setdefault(key, {})
        policy["name"] = RISK_NAMES[level]
        policy["required_evidence"] = list(RISK_REQUIREMENTS[level])
        if level >= 2:
            policy["independent_reviewer"] = True
        else:
            policy.setdefault("independent_reviewer", False)
        if level == 3:
            policy["rollback_required"] = True
        else:
            policy.setdefault("rollback_required", False)

    context = merged.setdefault("context", {})
    configured = context.get("excluded_normal_roots")
    exclusions = [str(item) for item in configured] if isinstance(configured, list) else []
    context["excluded_normal_roots"] = list(dict.fromkeys((*MANDATORY_NORMAL_CONTEXT_EXCLUSIONS, *exclusions)))
    context["archive_default"] = "off"

    execution = merged.setdefault("execution", {})
    execution["mode"] = "evidence_convergence"
    execution["path_control"] = "agent_autonomous_with_harness_boundaries"
    gates = merged.setdefault("gates", {})
    gates["policy"] = "risk_and_evidence"

    observe = merged.setdefault("observability", {})
    observe.update({"mode": "passive", "best_effort": True, "read_during_normal_runs": False})
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


def migrate_config(existing: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(existing)
    try:
        schema_version = int(migrated.get("schema_version", 1))
    except (TypeError, ValueError):
        schema_version = 1
    legacy_telemetry = migrated.pop("telemetry", None)
    if schema_version < 2:
        observation = dict(DEFAULT_CONFIG["observability"])
        if isinstance(legacy_telemetry, dict):
            observation = deep_merge(observation, {
                "enabled": bool(legacy_telemetry.get("enabled", True)),
                "retention": {"pending_days": safe_positive_int(legacy_telemetry.get("retention_days"), 30)},
            })
        migrated["observability"] = observation
        old_evolution = migrated.get("evolution")
        enabled = bool(old_evolution.get("enabled", True)) if isinstance(old_evolution, dict) else True
        migrated["evolution"] = {**DEFAULT_CONFIG["evolution"], "enabled": enabled}
    migration = migrated.setdefault("migration", {})
    if isinstance(migration, dict) and isinstance(legacy_telemetry, dict):
        migration.setdefault("legacy_telemetry_config", legacy_telemetry)
    return enforce_safe_boundaries(migrated)


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".codestable").is_dir():
            return candidate
    raise RuntimeErrorWithHint(
        "no .codestable directory found; run `cs_context.py init --root <project>` or `/cs init`"
    )


def runtime_dir(root: Path) -> Path:
    return root / ".codestable"


def active_root(root: Path) -> Path:
    return runtime_dir(root) / "work" / "active"


def archived_root(root: Path) -> Path:
    return runtime_dir(root) / "work" / "archive"


def ensure_under_root(root: Path, value: Path) -> Path:
    path = value.expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeErrorWithHint(f"path escapes project root: {value}") from exc
    return resolved


def rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"sha256": sha256_file(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def artifact_fingerprint(root: Path, raw: str) -> dict[str, Any]:
    path = ensure_under_root(root, Path(raw))
    relative = rel(root, path)
    if path.is_file():
        return {"path": relative, "kind": "file", **file_fingerprint(path)}
    if path.is_dir():
        records = []
        for child in sorted(path.rglob("*")):
            if child.is_file():
                records.append({"path": rel(root, child), "sha256": sha256_file(child), "size": child.stat().st_size})
        return {
            "path": relative,
            "kind": "directory",
            "files": len(records),
            "sha256": sha256_bytes(canonical_json(records)),
        }
    return {"path": relative, "kind": "missing", "sha256": None}


def slugify(value: str) -> str:
    normalized: list[str] = []
    previous_dash = False
    for char in value.strip().lower():
        if char.isalnum():
            normalized.append(char)
            previous_dash = False
        elif char in {"-", "_", " ", ".", "/", ":"}:
            if normalized and not previous_dash:
                normalized.append("-")
                previous_dash = True
    slug = "".join(normalized).strip("-") or "work"
    return slug[:64].rstrip("-") or "work"


def normalize_risk(value: Any) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeErrorWithHint(f"risk level must be 0, 1, 2 or 3: {value!r}") from exc
    if level not in RISK_LEVELS:
        raise RuntimeErrorWithHint(f"risk level must be 0, 1, 2 or 3: {value!r}")
    return level


def required_evidence(level: int) -> list[dict[str, Any]]:
    return [
        {"type": evidence_type, "minimum_pass": 1, "status": "missing", "evidence_ids": []}
        for evidence_type in RISK_REQUIREMENTS[level]
    ]


def initial_state(
    kind: str,
    title: str,
    slug: str,
    risk_level: int,
    work_id: str,
    *,
    owner_id: str = "owner",
    allowed_paths: Sequence[str] = (),
    no_writes: bool = False,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "id": work_id,
        "kind": kind,
        "title": title,
        "slug": slug,
        "status": "active",
        "current_action": "inspect",
        "created_at": timestamp,
        "updated_at": timestamp,
        "actors": {"owner_id": owner_id, "reviewer_ids": []},
        "goal": {
            "objective": "",
            "constraints": [],
            "non_goals": [],
            "invariants": [],
            "acceptance": [],
            "acceptance_scope": [],
        },
        "proposal": {
            "status": "not_required" if risk_level < 2 else "missing",
            "summary": "",
            "rationale": "",
            "non_changes": [],
            "evidence_required": [],
        },
        "risk": {
            "level": risk_level,
            "name": RISK_NAMES[risk_level],
            "reasons": [],
            "escalations": [],
        },
        "scope": {"paths": [], "symbols": [], "keywords": []},
        "side_effects": {
            "allowed_paths": list(dict.fromkeys(str(item) for item in allowed_paths if str(item).strip())),
            "forbidden_paths": [],
            "categories": [],
            "requires_authorization": [],
            "rollback_required": risk_level == 3,
            "no_writes": bool(no_writes),
            "git_baseline": {"available": False, "head": None, "paths": {}, "captured_at": None},
        },
        "ledger": {
            "facts": [],
            "assumptions": [],
            "risks": [],
            "changes": [],
        },
        "blockers": [],
        "links": {"model": [], "knowledge": [], "parent": None, "children": []},
        "evidence": {
            "required": required_evidence(risk_level),
            "summary": {status: 0 for status in EVIDENCE_STATUSES},
            "last_sequence": 0,
            "head_sha256": None,
            "integrity": "valid",
        },
        "completion": {
            "status": "INELIGIBLE",
            "eligible": False,
            "missing": [],
            "open_risks": [],
            "open_assumptions": [],
            "blockers": [],
            "checked_at": timestamp,
            "completed_at": None,
        },
    }


def work_template(kind: str, title: str, risk_level: int, work_id: str) -> str:
    prompt = {
        "feature": "Describe the observable capability and compatibility boundary.",
        "issue": "Describe intended behavior, observed symptom and reproduction signal.",
        "refactor": "Describe behavior that must remain stable and the structural problem.",
        "roadmap": "Describe the multi-system outcome and why one bounded change is insufficient.",
        "model": "Describe which current truth or reusable knowledge must change.",
    }[kind]
    return f"""# {title}

- Work: `{work_id}`
- Kind: `{kind}`
- Risk: `L{risk_level} {RISK_NAMES[risk_level]}`

## Task contract

- Objective: {prompt}
- Constraints:
- Non-goals:
- Invariants:
- Acceptance:

## Facts, assumptions and unknowns

- Facts:
- Assumptions:
- Unknowns:

## Risks and side effects

- Open risks:
- Allowed write scope:
- Forbidden operations:
- Authorization / rollback:

## Proposed change

- Change:
- Why:
- Intentionally unchanged:
- Evidence required:

## Changes

- Changed paths and behavior:
- Decisions made while executing:

## Evidence and completion

- Harness evidence IDs:
- Reviewer challenges:
- Open blockers:
- Completion claim:

## Learning

- Reusable failure signature / fixture / invariant / checker:
- No durable learning required because:
"""


def minimal_runtime_files(root: Path) -> dict[Path, str]:
    cs = runtime_dir(root)
    return {
        cs / "config.json": json_dump(DEFAULT_CONFIG),
        cs / "attention.md": "# Attention\n\n仅记录当前且跨任务必须反复看到的短期提醒。\n",
        cs / "model" / "INDEX.md": "# Current model index\n\n按任务需要链接当前 truth；不要复制正文。\n",
        cs / "model" / "vision.md": "# Vision\n\n## System purpose\n\n待填写。\n",
        cs / "model" / "domain.md": "# Domain language\n\n| Term | Meaning | Invariants / aliases |\n|---|---|---|\n",
        cs / "knowledge" / "INDEX.md": "# Knowledge index\n\n仅索引已提炼、可复用的知识。\n",
        cs / "work" / "archive-index.jsonl": "",
    }


def init_runtime(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    cs = runtime_dir(root)
    directories = [
        cs / "model" / "requirements",
        cs / "model" / "contracts",
        cs / "model" / "decisions",
        cs / "model" / "roadmaps",
        cs / "knowledge" / "notes",
        cs / "work" / "active",
        cs / "work" / "archive",
        cs / "reference",
        cs / "tools",
        cs / "harness" / "versions",
        cs / "observations" / "pending",
        cs / "observations" / "flagged",
        cs / "observations" / "selected",
        cs / "evolution" / "cases",
        cs / "evolution" / "rejected",
        cs / "evals" / "public",
        cs / "evals" / "fixtures" / "contracts",
        cs / "evals" / "fixtures" / "routing",
        cs / "evals" / "fixtures" / "e2e",
        cs / "evals" / "fixtures" / "regression",
        cs / "meta" / "campaigns",
        cs / "meta" / "feedback" / "items",
        cs / "meta" / "hypotheses",
        cs / "meta" / "variants",
        cs / "meta" / "results",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    preserved: list[str] = []
    for path, content in minimal_runtime_files(root).items():
        if path.exists():
            preserved.append(rel(root, path))
        else:
            atomic_write(path, content)
            created.append(rel(root, path))

    config_path = cs / "config.json"
    existing = read_json(config_path)
    merged = migrate_config(existing)
    if merged != existing:
        write_json(config_path, merged)
    return {"root": str(root), "created": created, "preserved": preserved}


def iter_active_dirs(root: Path) -> Iterator[Path]:
    base = active_root(root)
    if not base.exists():
        return
    for child in sorted(base.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            yield child


def unique_work_id(root: Path, slug: str) -> str:
    base = f"{datetime.now().astimezone().date().isoformat()}-{slug}"
    candidate = base
    counter = 2
    while (active_root(root) / candidate).exists() or any(
        (year / candidate).exists()
        for year in archived_root(root).glob("[0-9][0-9][0-9][0-9]")
        if year.is_dir()
    ):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def evidence_path(work_dir: Path) -> Path:
    return work_dir / "evidence.jsonl"


def context_path(work_dir: Path) -> Path:
    return work_dir / "context.json"


def legacy_action(stage: Any) -> str:
    value = str(stage or "").strip().casefold()
    if value in {"design", "frame", "contracts", "decompose", "analyze"}:
        return "propose"
    if value in {"implement", "fix", "edit", "activate"}:
        return "execute"
    if value in {"verify", "validate", "review", "accept", "index"}:
        return "verify"
    return "inspect"


def legacy_risk(lane: Any) -> int:
    value = str(lane or "").strip().casefold()
    return {"micro": 0, "standard": 1, "high-risk": 3}.get(value, 1)


def migrate_state(raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if int(raw.get("schema_version", 0) or 0) >= TASK_SCHEMA_VERSION and "stage" not in raw and "lane" not in raw:
        return raw, False
    if not raw.get("id"):
        raise RuntimeErrorWithHint("legacy state is missing id")
    risk_level = legacy_risk(raw.get("lane"))
    state = initial_state(
        str(raw.get("kind") or "feature"),
        str(raw.get("title") or raw.get("id")),
        str(raw.get("slug") or slugify(str(raw.get("title") or raw.get("id")))),
        risk_level,
        str(raw["id"]),
    )
    state["created_at"] = raw.get("created_at") or state["created_at"]
    state["updated_at"] = now_iso()
    old_status = str(raw.get("status") or "active")
    state["status"] = old_status if old_status in WORK_STATUSES else "active"
    state["current_action"] = legacy_action(raw.get("stage"))
    for field in ("scope", "links"):
        if isinstance(raw.get(field), dict):
            state[field] = deep_merge(state[field], raw[field])
    gate = raw.get("gate") if isinstance(raw.get("gate"), dict) else {}
    if gate.get("status") in {"required", "rejected"}:
        state["blockers"].append({
            "id": "blocker-001",
            "text": str(gate.get("question") or "legacy gate remains unresolved"),
            "status": "open",
            "created_at": now_iso(),
            "source": "legacy_gate",
        })
    state["migration"] = {
        "from": "stage_state_v1",
        "migrated_at": now_iso(),
        "legacy_stage": raw.get("stage"),
        "legacy_lane": raw.get("lane"),
        "legacy_validation": raw.get("validation"),
        "note": "Legacy validation was not converted into proof because evidence must be re-observed.",
    }
    return state, True


def read_evidence(work_dir: Path, *, strict: bool = True) -> list[dict[str, Any]]:
    path = evidence_path(work_dir)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    previous: str | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeErrorWithHint(f"invalid evidence JSONL at line {number}: {exc}") from exc
        if not isinstance(entry, dict):
            raise RuntimeErrorWithHint(f"evidence line {number} must be an object")
        stored = str(entry.get("entry_sha256") or "")
        payload = dict(entry)
        payload.pop("entry_sha256", None)
        calculated = sha256_bytes(canonical_json(payload))
        if strict and stored != calculated:
            raise RuntimeErrorWithHint(f"evidence integrity failure at line {number}: entry hash mismatch")
        if strict and payload.get("previous_sha256") != previous:
            raise RuntimeErrorWithHint(f"evidence integrity failure at line {number}: chain mismatch")
        previous = stored or calculated
        entries.append(entry)
    return entries


def evidence_summary(entries: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {status: sum(1 for item in entries if item.get("status") == status) for status in EVIDENCE_STATUSES}


def normalize_scope_value(value: Any) -> str:
    normalized = "-".join(str(value).strip().casefold().split())
    if not normalized:
        raise RuntimeErrorWithHint("evidence scope cannot be empty")
    if len(normalized) > 256:
        raise RuntimeErrorWithHint("evidence scope is too long")
    return normalized


def normalize_evidence_scope(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = normalize_scope_value(value)
        if normalized not in result:
            result.append(normalized)
    return result


def normalize_acceptance_scope(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = normalize_scope_value(value)
        if "=" in normalized:
            evidence_type, scope = normalized.split("=", 1)
            if not evidence_type or not scope:
                raise RuntimeErrorWithHint(
                    "acceptance scope must use [evidence_type=]scope, for example live_validation=scenario:*"
                )
        else:
            evidence_type, scope = "*", normalized
        item = f"{evidence_type}={scope}"
        if item not in result:
            result.append(item)
    return result


def acceptance_scope_contract(state: dict[str, Any]) -> list[str]:
    goal = state.get("goal") if isinstance(state.get("goal"), dict) else {}
    declared = goal.get("acceptance_scope") if isinstance(goal.get("acceptance_scope"), list) else []
    values = normalize_acceptance_scope([str(item) for item in declared if str(item).strip()])
    acceptance = goal.get("acceptance") if isinstance(goal.get("acceptance"), list) else []
    for condition in acceptance:
        for match in re.findall(r"\[scope:([^\]]+)\]", str(condition), flags=re.IGNORECASE):
            for item in normalize_acceptance_scope([match]):
                if item not in values:
                    values.append(item)
    return values


def acceptance_scope_requirements(state: dict[str, Any], evidence_type: str) -> list[str]:
    normalized_type = evidence_type.strip().casefold()
    requirements: list[str] = []
    for item in acceptance_scope_contract(state):
        target, scope = item.split("=", 1)
        applies = target == normalized_type or (
            target == "*" and normalized_type in ACCEPTANCE_SCOPED_EVIDENCE
        )
        if applies and scope not in requirements:
            requirements.append(scope)
    return requirements


def scope_token_covers(coverage: str, requirement: str) -> bool:
    if coverage == "*" or coverage == requirement:
        return True
    if coverage.endswith("*"):
        return requirement.startswith(coverage[:-1])
    return False


def missing_scope_requirements(required: Sequence[str], coverage: Sequence[str]) -> list[str]:
    normalized_coverage = normalize_evidence_scope([str(item) for item in coverage if str(item).strip()])
    return [
        requirement
        for requirement in required
        if not any(scope_token_covers(item, requirement) for item in normalized_coverage)
    ]


def stable_projection(value: Any) -> Any:
    volatile = {"created_at", "updated_at", "resolved_at", "captured_at", "checked_at", "completed_at", "at"}
    if isinstance(value, dict):
        return {
            str(key): stable_projection(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in volatile
        }
    if isinstance(value, list):
        return [stable_projection(item) for item in value]
    return value


def registered_change_projection(state: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = state.get("ledger") if isinstance(state.get("ledger"), dict) else {}
    changes = ledger.get("changes") if isinstance(ledger.get("changes"), list) else []
    result: list[dict[str, Any]] = []
    for item in changes:
        if not isinstance(item, dict):
            continue
        result.append(stable_projection({
            "id": item.get("id"),
            "text": item.get("text"),
            "status": item.get("status"),
            "source": item.get("source"),
            "paths": [str(path) for path in item.get("paths", []) if str(path).strip()],
            "rollback": item.get("rollback"),
        }))
    return result


def registered_change_paths(state: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(
        str(path)
        for item in registered_change_projection(state)
        for path in item.get("paths", [])
        if str(path).strip()
    ))


def relevant_state_projection(state: dict[str, Any]) -> dict[str, Any]:
    goal = state.get("goal") if isinstance(state.get("goal"), dict) else {}
    ledger = state.get("ledger") if isinstance(state.get("ledger"), dict) else {}
    side = state.get("side_effects") if isinstance(state.get("side_effects"), dict) else {}
    risk = state.get("risk") if isinstance(state.get("risk"), dict) else {}
    return stable_projection({
        "kind": state.get("kind"),
        "goal_context": {
            "objective": goal.get("objective"),
            "constraints": goal.get("constraints") or [],
            "non_goals": goal.get("non_goals") or [],
        },
        "risk": {
            "level": risk.get("level"),
            "name": risk.get("name"),
        },
        "scope": state.get("scope") or {},
        "links": state.get("links") or {},
        "side_effects": {
            "allowed_paths": side.get("allowed_paths") or [],
            "forbidden_paths": side.get("forbidden_paths") or [],
            "categories": side.get("categories") or [],
            "requires_authorization": side.get("requires_authorization") or [],
            "rollback_required": side.get("rollback_required") is True,
            "no_writes": side.get("no_writes") is True,
        },
        "ledger": {
            "facts": ledger.get("facts") or [],
            "assumptions": ledger.get("assumptions") or [],
            "risks": ledger.get("risks") or [],
        },
        "blockers": state.get("blockers") or [],
    })


def proposal_projection(state: dict[str, Any]) -> dict[str, Any]:
    proposal = state.get("proposal") if isinstance(state.get("proposal"), dict) else {}
    return stable_projection({
        "status": proposal.get("status"),
        "summary": proposal.get("summary"),
        "rationale": proposal.get("rationale"),
        "non_changes": proposal.get("non_changes") or [],
        "evidence_required": proposal.get("evidence_required") or [],
    })


def invariant_projection(state: dict[str, Any]) -> list[str]:
    goal = state.get("goal") if isinstance(state.get("goal"), dict) else {}
    return [str(item) for item in goal.get("invariants", []) if str(item).strip()]


def acceptance_contract_projection(state: dict[str, Any]) -> dict[str, Any]:
    goal = state.get("goal") if isinstance(state.get("goal"), dict) else {}
    return stable_projection({
        "objective": goal.get("objective"),
        "constraints": goal.get("constraints") or [],
        "non_goals": goal.get("non_goals") or [],
        "acceptance": goal.get("acceptance") or [],
        "acceptance_scope": acceptance_scope_contract(state),
    })


def semantic_artifact_fingerprint(artifact: dict[str, Any]) -> dict[str, Any]:
    fields = ("path", "kind", "sha256", "size", "mode", "files")
    return {field: artifact.get(field) for field in fields if field in artifact}


def artifact_set_sha256(artifacts: Sequence[dict[str, Any]]) -> str:
    normalized = sorted(
        (semantic_artifact_fingerprint(item) for item in artifacts if isinstance(item, dict)),
        key=lambda item: str(item.get("path") or ""),
    )
    return sha256_bytes(canonical_json(normalized))


def current_artifact_fingerprints(root: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    stored = entry.get("artifacts") if isinstance(entry.get("artifacts"), list) else []
    current: list[dict[str, Any]] = []
    for artifact in stored:
        if not isinstance(artifact, dict) or not str(artifact.get("path") or "").strip():
            continue
        try:
            current.append(artifact_fingerprint(root, str(artifact["path"])))
        except (OSError, RuntimeErrorWithHint):
            current.append({"path": str(artifact["path"]), "kind": "missing", "sha256": None})
    return current


def evidence_artifact_patterns(
    state: dict[str, Any],
    entries: Sequence[dict[str, Any]],
    pending_artifacts: Sequence[dict[str, Any]] = (),
) -> list[str]:
    registered = registered_change_paths(state)
    patterns: list[str] = []
    for entry in (*entries, {"artifacts": list(pending_artifacts)}):
        artifacts = entry.get("artifacts") if isinstance(entry, dict) and isinstance(entry.get("artifacts"), list) else []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path") or "").strip()
            if not path:
                continue
            overlaps_registered = any(
                path_matches(path, registered_path) or path_matches(registered_path, path)
                for registered_path in registered
            )
            if not overlaps_registered and path not in patterns:
                patterns.append(path)
    return patterns


def source_snapshot(
    root: Path,
    state: dict[str, Any],
    entries: Sequence[dict[str, Any]],
    pending_artifacts: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    changed, git_error = task_git_changes(root, state)
    evidence_artifacts = evidence_artifact_patterns(state, entries, pending_artifacts)
    source_paths = [
        path for path in changed
        if not any(path_matches(path, pattern) for pattern in evidence_artifacts)
    ]
    records = [
        {"path": path, "fingerprint": git_path_fingerprint(root, path)}
        for path in sorted(source_paths)
    ]
    baseline = (state.get("side_effects") or {}).get("git_baseline")
    return {
        "baseline_head": baseline.get("head") if isinstance(baseline, dict) else None,
        "current_head": git_head(root),
        "git_error": git_error,
        "paths": records,
    }


def current_evidence_bindings(
    root: Path,
    state: dict[str, Any],
    entries: Sequence[dict[str, Any]],
    pending_artifacts: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    source = source_snapshot(root, state, entries, pending_artifacts)
    return {
        "schema_version": EVIDENCE_BINDING_SCHEMA_VERSION,
        "source_snapshot_sha256": sha256_bytes(canonical_json(source)),
        "registered_changes_sha256": sha256_bytes(canonical_json(registered_change_projection(state))),
        "relevant_state_sha256": sha256_bytes(canonical_json(relevant_state_projection(state))),
        "proposal_sha256": sha256_bytes(canonical_json(proposal_projection(state))),
        "invariants_sha256": sha256_bytes(canonical_json(invariant_projection(state))),
        "acceptance_contract_sha256": sha256_bytes(canonical_json(acceptance_contract_projection(state))),
        "artifact_set_sha256": artifact_set_sha256(pending_artifacts) if pending_artifacts else None,
        "git_head": source.get("current_head"),
        "source_paths": [str(item.get("path")) for item in source.get("paths", [])],
    }


def independent_review_is_valid(state: dict[str, Any], entry: dict[str, Any]) -> bool:
    owner = str((state.get("actors") or {}).get("owner_id") or "owner")
    producer = str(entry.get("producer") or "")
    artifacts = entry.get("artifacts") if isinstance(entry.get("artifacts"), list) else []
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    return bool(
        producer
        and producer != owner
        and artifacts
        and metadata.get("verdict") == "PASS"
        and metadata.get("identity_assurance") == "declarative"
    )


def evidence_is_structurally_valid(
    state: dict[str, Any], entry: dict[str, Any], evidence_type: str
) -> bool:
    if entry.get("type") != evidence_type or entry.get("status") != "PASS":
        return False
    source = str(entry.get("source") or "")
    if source not in REQUIRED_EVIDENCE_SOURCES[evidence_type]:
        return False
    if source == "command_execution" and (not entry.get("command") or entry.get("exit_code") != 0):
        return False
    if source in {"state_snapshot", "proof_assembly"} and entry.get("producer") != "harness":
        return False
    if source == "artifact_record" and not entry.get("artifacts"):
        return False
    return evidence_type != "independent_review" or independent_review_is_valid(state, entry)


def evidence_applicability(
    root: Path,
    state: dict[str, Any],
    entry: dict[str, Any],
    evidence_type: str,
    current_bindings: dict[str, Any],
) -> dict[str, Any]:
    bindings = entry.get("bindings") if isinstance(entry.get("bindings"), dict) else {}
    stale_reasons: list[dict[str, str]] = []
    if int(entry.get("schema_version", 0) or 0) < EVIDENCE_SCHEMA_VERSION or not bindings:
        stale_reasons.append({
            "binding": "provenance",
            "detail": "does not contain deterministic provenance bindings",
        })
    else:
        for binding in CORE_EVIDENCE_BINDINGS:
            if not bindings.get(binding) or bindings.get(binding) != current_bindings.get(binding):
                stale_reasons.append({
                    "binding": binding,
                    "detail": f"was recorded for {BINDING_DETAILS[binding]}",
                })
        if evidence_type == "independent_review":
            reviewed = bindings.get("reviewed_diff_sha256")
            if not reviewed or reviewed != current_bindings.get("source_snapshot_sha256"):
                stale_reasons.append({
                    "binding": "reviewed_diff_sha256",
                    "detail": f"was recorded for {BINDING_DETAILS['reviewed_diff_sha256']}",
                })
        artifacts = entry.get("artifacts") if isinstance(entry.get("artifacts"), list) else []
        if artifacts and str(entry.get("source") or "") != "state_snapshot":
            current_artifacts = current_artifact_fingerprints(root, entry)
            if (
                not bindings.get("artifact_set_sha256")
                or bindings.get("artifact_set_sha256") != artifact_set_sha256(current_artifacts)
            ):
                stale_reasons.append({
                    "binding": "artifact_set_sha256",
                    "detail": f"was recorded for {BINDING_DETAILS['artifact_set_sha256']}",
                })
    if stale_reasons:
        return {"status": "stale", "reasons": stale_reasons}

    required_scope = acceptance_scope_requirements(state, evidence_type)
    scope = entry.get("scope") if isinstance(entry.get("scope"), dict) else {}
    coverage = scope.get("coverage") if isinstance(scope.get("coverage"), list) else []
    missing_scope = missing_scope_requirements(required_scope, coverage)
    if missing_scope:
        return {
            "status": "scope_mismatch",
            "required_scope": required_scope,
            "coverage": normalize_evidence_scope([str(item) for item in coverage if str(item).strip()]),
            "missing_scope": missing_scope,
        }
    return {"status": "current", "required_scope": required_scope, "coverage": coverage}


def evidence_satisfies_requirement(
    state: dict[str, Any],
    entry: dict[str, Any],
    evidence_type: str,
    *,
    root: Path | None = None,
    current_bindings: dict[str, Any] | None = None,
) -> bool:
    if not evidence_is_structurally_valid(state, entry, evidence_type):
        return False
    if root is None or current_bindings is None:
        return False
    return evidence_applicability(root, state, entry, evidence_type, current_bindings).get("status") == "current"

def completion_snapshot(
    work_dir: Path,
    state: dict[str, Any],
    entries: Sequence[dict[str, Any]],
    *,
    integrity_error: str | None = None,
) -> dict[str, Any]:
    root = find_project_root(start=work_dir)
    level = normalize_risk((state.get("risk") or {}).get("level", 1))
    missing: list[dict[str, Any]] = []
    goal = state.get("goal") if isinstance(state.get("goal"), dict) else {}
    if not str(goal.get("objective") or "").strip():
        missing.append({"code": "goal.objective", "detail": "objective is not set"})
    acceptance = goal.get("acceptance") if isinstance(goal.get("acceptance"), list) else []
    if not [item for item in acceptance if str(item).strip()]:
        missing.append({"code": "goal.acceptance", "detail": "at least one acceptance condition is required"})
    if level >= 2 and not [item for item in goal.get("invariants", []) if str(item).strip()]:
        missing.append({"code": "goal.invariants", "detail": "L2/L3 work requires explicit invariants"})

    side_effects = state.get("side_effects") if isinstance(state.get("side_effects"), dict) else {}
    allowed = side_effects.get("allowed_paths") if isinstance(side_effects.get("allowed_paths"), list) else []
    no_writes = side_effects.get("no_writes") is True
    if not no_writes and not allowed:
        missing.append({"code": "side_effects.allowed_paths", "detail": "write scope is not bounded"})
    if level == 3 and side_effects.get("rollback_required") is not True:
        missing.append({"code": "side_effects.rollback_required", "detail": "L3 work requires rollback"})

    ledger = state.get("ledger") if isinstance(state.get("ledger"), dict) else {}
    facts = ledger.get("facts") if isinstance(ledger.get("facts"), list) else []
    changes = ledger.get("changes") if isinstance(ledger.get("changes"), list) else []
    if level >= 1 and not facts:
        missing.append({"code": "ledger.facts", "detail": "inspection has not established a fact"})
    if not no_writes and not changes:
        missing.append({"code": "ledger.changes", "detail": "no changed path is registered"})

    actual_paths, git_error = task_git_changes(root, state)
    if git_error:
        missing.append({"code": "side_effects.git_baseline", "detail": git_error})
    elif no_writes and actual_paths:
        missing.append({
            "code": "side_effects.no_writes",
            "detail": "Git-visible changes exist in a no-writes task: " + ", ".join(actual_paths[:12]),
        })
    elif not no_writes:
        registered = [
            str(path)
            for change in changes
            if isinstance(change, dict)
            for path in change.get("paths", [])
        ]
        registered.extend(
            str(artifact.get("path"))
            for entry in entries
            for artifact in (entry.get("artifacts") or [])
            if isinstance(artifact, dict) and artifact.get("path")
        )
        unregistered = [
            path for path in actual_paths
            if not any(path_matches(path, pattern) for pattern in registered)
        ]
        outside = [path for path in actual_paths if not path_allowed(state, path)]
        if unregistered:
            missing.append({
                "code": "side_effects.unregistered_paths",
                "detail": "Git-visible changes are not registered: " + ", ".join(unregistered[:12]),
            })
        if outside:
            missing.append({
                "code": "side_effects.outside_boundary",
                "detail": "Git-visible changes escape the side-effect boundary: " + ", ".join(outside[:12]),
            })

    proposal = state.get("proposal") if isinstance(state.get("proposal"), dict) else {}
    if level >= 2 and proposal.get("status") != "ready":
        missing.append({"code": "proposal", "detail": "L2/L3 proposal is not ready"})

    assumptions = ledger.get("assumptions") if isinstance(ledger.get("assumptions"), list) else []
    open_assumptions = [
        item for item in assumptions
        if item.get("status", "open") == "open" and item.get("blocking", level >= 2) is True
    ]
    risks = ledger.get("risks") if isinstance(ledger.get("risks"), list) else []
    open_risks = [
        item for item in risks
        if item.get("status", "open") == "open"
        and (item.get("blocking") is True or str(item.get("severity")) in {"high", "critical"})
    ]
    blockers = state.get("blockers") if isinstance(state.get("blockers"), list) else []
    open_blockers = [item for item in blockers if item.get("status", "open") == "open"]

    requirements: list[dict[str, Any]] = []
    current_bindings = current_evidence_bindings(root, state, entries)
    for evidence_type in RISK_REQUIREMENTS[level]:
        candidates = [
            item for item in entries
            if evidence_is_structurally_valid(state, item, evidence_type)
        ]
        assessed = [
            (item, evidence_applicability(root, state, item, evidence_type, current_bindings))
            for item in candidates
        ]
        passing = [item for item, result in assessed if result.get("status") == "current"]
        stale = [
            {
                "id": str(item.get("id")),
                "reasons": result.get("reasons") or [],
            }
            for item, result in assessed if result.get("status") == "stale"
        ]
        scope_mismatches = [
            {
                "id": str(item.get("id")),
                "coverage": result.get("coverage") or [],
                "required_scope": result.get("required_scope") or [],
                "missing_scope": result.get("missing_scope") or [],
            }
            for item, result in assessed if result.get("status") == "scope_mismatch"
        ]
        if passing:
            status = "satisfied"
        elif scope_mismatches:
            status = "scope_mismatch"
        elif stale:
            status = "stale"
        else:
            status = "missing"
        requirement = {
            "type": evidence_type,
            "minimum_pass": 1,
            "status": status,
            "evidence_ids": [str(item.get("id")) for item in passing],
            "stale_evidence": stale,
            "scope_mismatches": scope_mismatches,
            "required_scope": acceptance_scope_requirements(state, evidence_type),
        }
        requirements.append(requirement)
        if status == "scope_mismatch":
            latest = scope_mismatches[-1]
            missing.append({
                "code": f"evidence.{evidence_type}.scope",
                "detail": (
                    f"PASS evidence {latest['id']} covers {latest['coverage'] or ['<unspecified>']} "
                    f"but acceptance requires {latest['required_scope']}"
                ),
            })
        elif status == "stale":
            latest = stale[-1]
            reasons = latest.get("reasons") or []
            detail = str(reasons[0].get("detail")) if reasons else "is not bound to the current task state"
            missing.append({
                "code": f"evidence.{evidence_type}.stale",
                "detail": f"PASS evidence {latest['id']} {detail}",
            })
        elif status == "missing":
            missing.append({"code": f"evidence.{evidence_type}", "detail": f"missing PASS evidence: {evidence_type}"})

    if integrity_error:
        missing.append({"code": "evidence.integrity", "detail": integrity_error})
    eligible = not missing and not open_assumptions and not open_risks and not open_blockers
    return {
        "status": "ELIGIBLE" if eligible else "INELIGIBLE",
        "eligible": eligible,
        "missing": missing,
        "open_risks": open_risks,
        "open_assumptions": open_assumptions,
        "blockers": open_blockers,
        "required_evidence": requirements,
        "checked_at": now_iso(),
        "completed_at": (state.get("completion") or {}).get("completed_at"),
    }


def recommend_actions(state: dict[str, Any], completion: dict[str, Any]) -> list[str]:
    codes = {str(item.get("code")) for item in completion.get("missing", []) if isinstance(item, dict)}
    recommendations: list[str] = []
    if any(code.startswith("goal.") or code.startswith("ledger.facts") or code.startswith("side_effects") for code in codes):
        recommendations.append("inspect")
    if "proposal" in codes or "evidence.proposal" in codes or "evidence.invariant_contract" in codes:
        recommendations.append("propose")
    if "ledger.changes" in codes:
        recommendations.append("execute")
    if any(code.startswith("evidence.") for code in codes) or completion.get("open_risks") or completion.get("blockers"):
        recommendations.append("verify")
    if "evidence.regression_fixture" in codes:
        recommendations.append("learn")
    if completion.get("eligible"):
        recommendations.append("complete")
    return list(dict.fromkeys(recommendations)) or [str(state.get("current_action") or "inspect")]


def refresh_state(work_dir: Path, state: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
    integrity_error = None
    try:
        entries = read_evidence(work_dir)
    except RuntimeErrorWithHint as exc:
        entries = []
        integrity_error = str(exc)
    state.setdefault("evidence", {})
    state["evidence"]["summary"] = evidence_summary(entries)
    state["evidence"]["last_sequence"] = len(entries)
    state["evidence"]["head_sha256"] = entries[-1].get("entry_sha256") if entries else None
    state["evidence"]["integrity"] = "invalid" if integrity_error else "valid"
    actual_paths, git_error = task_git_changes(find_project_root(start=work_dir), state)
    if not git_error:
        floor, reasons = path_risk_floor(actual_paths)
        escalate_risk(state, floor, reasons, source="git_change_scan")
    prior_completion = state.get("completion") if isinstance(state.get("completion"), dict) else {}
    snapshot = completion_snapshot(work_dir, state, entries, integrity_error=integrity_error)
    state["evidence"]["required"] = snapshot.pop("required_evidence")
    if state.get("status") == "done" and prior_completion.get("status") == "COMPLETED":
        snapshot["status"] = "COMPLETED"
        snapshot["completed_at"] = prior_completion.get("completed_at")
        snapshot["reason"] = prior_completion.get("reason")
    elif state.get("status") == "blocked":
        snapshot["status"] = "BLOCKED"
        snapshot["reason"] = prior_completion.get("reason")
    elif state.get("status") == "partial":
        snapshot["status"] = "PARTIAL"
        snapshot["reason"] = prior_completion.get("reason")
    elif state.get("status") == "cancelled":
        snapshot["status"] = "CANCELLED"
        snapshot["reason"] = prior_completion.get("reason")
    state["completion"] = snapshot
    state["completion"]["next_actions"] = (
        [] if state["completion"]["status"] == "CANCELLED" or (
            state["completion"]["status"] == "COMPLETED" and state["completion"]["eligible"]
        )
        else recommend_actions(state, state["completion"])
    )
    if persist:
        write_json(work_dir / "state.json", state)
    return state


def load_state(work_dir: Path, *, persist_migration: bool = True) -> dict[str, Any]:
    raw = read_json(work_dir / "state.json")
    if not raw.get("id"):
        raise RuntimeErrorWithHint(f"state missing id: {work_dir / 'state.json'}")
    state, migrated = migrate_state(raw)
    goal = state.setdefault("goal", {})
    raw_acceptance_scope = goal.get("acceptance_scope")
    if isinstance(raw_acceptance_scope, list):
        goal["acceptance_scope"] = normalize_acceptance_scope(
            [str(item) for item in raw_acceptance_scope if str(item).strip()]
        )
    else:
        goal["acceptance_scope"] = []
    side_effects = state.setdefault("side_effects", {})
    baseline = side_effects.get("git_baseline")
    if not isinstance(baseline, dict) or not baseline.get("captured_at"):
        side_effects["git_baseline"] = capture_git_baseline(find_project_root(start=work_dir))
    if not evidence_path(work_dir).exists():
        atomic_write(evidence_path(work_dir), "")
    if migrated and persist_migration:
        write_json(work_dir / "state.json", state)
    return refresh_state(work_dir, state, persist=persist_migration)


def load_context(work_dir: Path) -> dict[str, Any]:
    path = context_path(work_dir)
    if not path.exists():
        return {"schema_version": CONTEXT_SCHEMA_VERSION, "sessions": {}}
    value = read_json(path)
    value["schema_version"] = CONTEXT_SCHEMA_VERSION
    value.setdefault("sessions", {})
    if not isinstance(value["sessions"], dict):
        value["sessions"] = {}
    return value


def resolve_work(root: Path, selector: str) -> Path:
    exact = active_root(root) / selector
    if exact.is_dir():
        return exact
    matches: list[Path] = []
    for directory in iter_active_dirs(root):
        try:
            state = load_state(directory)
        except RuntimeErrorWithHint:
            continue
        searchable = {directory.name, str(state.get("id", "")), str(state.get("slug", ""))}
        if selector in searchable or any(value.endswith(selector) for value in searchable if value):
            matches.append(directory)
    if not matches:
        raise RuntimeErrorWithHint(f"active work not found: {selector}")
    if len(matches) > 1:
        raise RuntimeErrorWithHint(
            f"work selector is ambiguous: {selector}; matches: {', '.join(path.name for path in matches)}"
        )
    return matches[0]


def append_evidence(
    work_dir: Path,
    state: dict[str, Any],
    *,
    evidence_type: str,
    status: str,
    producer: str,
    source: str,
    summary: str = "",
    command: Sequence[str] | None = None,
    cwd: str | None = None,
    exit_code: int | None = None,
    duration_ms: int | None = None,
    artifacts: Sequence[dict[str, Any]] = (),
    stdout_tail: str = "",
    stderr_tail: str = "",
    metadata: dict[str, Any] | None = None,
    scope: Sequence[str] = (),
    reviewed_diff_sha256: str | None = None,
) -> dict[str, Any]:
    normalized_status = status.strip().upper()
    if normalized_status not in EVIDENCE_STATUSES:
        raise RuntimeErrorWithHint(f"evidence status must be one of {', '.join(EVIDENCE_STATUSES)}")
    normalized_type = evidence_type.strip().casefold()
    normalized_artifacts = list(artifacts)
    normalized_scope = normalize_evidence_scope([str(item) for item in scope if str(item).strip()])
    entries = read_evidence(work_dir)
    root = find_project_root(start=work_dir)
    bindings = current_evidence_bindings(root, state, entries, normalized_artifacts)
    metadata_payload = dict(metadata or {})
    if normalized_type == "independent_review":
        current_diff = str(bindings["source_snapshot_sha256"])
        declared_diff = str(reviewed_diff_sha256 or "").strip()
        if declared_diff and declared_diff != current_diff:
            raise RuntimeErrorWithHint(
                "independent_review reviewed diff does not match the current source snapshot"
            )
        bindings["reviewed_diff_sha256"] = current_diff
        metadata_payload["reviewed_diff_sha256"] = current_diff
    sequence = len(entries) + 1
    previous = entries[-1].get("entry_sha256") if entries else None
    payload: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "id": f"ev-{sequence:04d}",
        "sequence": sequence,
        "recorded_at": now_iso(),
        "type": normalized_type,
        "status": normalized_status,
        "producer": producer.strip() or "harness",
        "source": source.strip() or "harness",
        "summary": summary.strip()[:4096],
        "command": list(command or []),
        "cwd": cwd,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "artifacts": normalized_artifacts,
        "scope": {"coverage": normalized_scope},
        "bindings": bindings,
        "stdout_tail": stdout_tail[-4000:],
        "stderr_tail": stderr_tail[-4000:],
        "metadata": metadata_payload,
        "previous_sha256": previous,
    }
    payload["entry_sha256"] = sha256_bytes(canonical_json(payload))
    append_jsonl(evidence_path(work_dir), payload)
    state["updated_at"] = now_iso()
    refresh_state(work_dir, state)
    return payload

def normalize_patterns(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        raw = str(value).replace("\\", "/").strip()
        while raw.startswith("./"):
            raw = raw[2:]
        if not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
            raise RuntimeErrorWithHint(f"unsafe path pattern: {value!r}")
        if raw not in result:
            result.append(raw)
    return result


def path_matches(relative: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return relative == prefix or relative.startswith(prefix + "/")
    if not any(char in pattern for char in "*?["):
        return relative == pattern or relative.startswith(pattern.rstrip("/") + "/")
    return False


def path_allowed(state: dict[str, Any], relative: str) -> bool:
    side = state.get("side_effects") if isinstance(state.get("side_effects"), dict) else {}
    allowed = [str(item) for item in side.get("allowed_paths", []) if str(item).strip()]
    forbidden = [str(item) for item in side.get("forbidden_paths", []) if str(item).strip()]
    return any(path_matches(relative, pattern) for pattern in allowed) and not any(
        path_matches(relative, pattern) for pattern in forbidden
    )


def path_risk_floor(paths: Sequence[str]) -> tuple[int, list[str]]:
    if not paths:
        return 0, []
    reasons: list[str] = []
    floor = 0
    if any(Path(path).suffix.casefold() in CODE_SUFFIXES for path in paths):
        floor = max(floor, 1)
        reasons.append("source_code_change")
    top_level = {Path(path).parts[0] for path in paths if Path(path).parts}
    if len(top_level) >= 2 or len(paths) >= 4:
        floor = max(floor, 2)
        reasons.append("cross_module_change")
    critical_tokens = ("auth", "permission", "security", "payment", "billing", "migration", "schema", "state", "delete", "rollback")
    critical_directories = {"auth", "security", "permissions", "payments", "billing", "migrations", "schemas"}
    critical_signal = False
    for raw_path in paths:
        path = Path(raw_path)
        lowered_parts = {part.casefold() for part in path.parts}
        is_executable_surface = path.suffix.casefold() in CODE_SUFFIXES or path.suffix.casefold() in {".sql", ".proto"}
        if is_executable_surface and (
            (lowered_parts & critical_directories)
            or any(token in raw_path.casefold() for token in critical_tokens)
        ):
            critical_signal = True
            break
    if critical_signal:
        floor = max(floor, 3)
        reasons.append("critical_path_signal")
    return floor, list(dict.fromkeys(reasons))


def escalate_risk(state: dict[str, Any], level: int, reasons: Sequence[str], *, source: str) -> bool:
    current = normalize_risk((state.get("risk") or {}).get("level", 1))
    target = max(current, normalize_risk(level))
    if target == current:
        risk_reasons = state.setdefault("risk", {}).setdefault("reasons", [])
        for reason in reasons:
            if reason and reason not in risk_reasons:
                risk_reasons.append(reason)
        return False
    timestamp = now_iso()
    risk = state.setdefault("risk", {})
    risk["level"] = target
    risk["name"] = RISK_NAMES[target]
    risk.setdefault("reasons", [])
    for reason in reasons:
        if reason and reason not in risk["reasons"]:
            risk["reasons"].append(reason)
    risk.setdefault("escalations", []).append({
        "from": current,
        "to": target,
        "reasons": list(reasons),
        "source": source,
        "at": timestamp,
    })
    if target >= 2 and state.get("proposal", {}).get("status") == "not_required":
        state["proposal"]["status"] = "missing"
    if target == 3:
        state.setdefault("side_effects", {})["rollback_required"] = True
    state["updated_at"] = timestamp
    return True


def next_ledger_id(items: Sequence[dict[str, Any]], prefix: str) -> str:
    return f"{prefix}-{len(items) + 1:03d}"


def collect_git_changes(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeErrorWithHint(completed.stderr.decode("utf-8", errors="replace")[-2000:] or "git status failed")
    fields = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        if len(field) < 4:
            continue
        status = field[:2]
        path = field[3:]
        candidates = [path]
        if "R" in status or "C" in status:
            if index < len(fields) and fields[index]:
                candidates.append(fields[index])
                index += 1
        for candidate in candidates:
            normalized = Path(candidate).as_posix()
            if normalized not in paths:
                paths.append(normalized)
    return paths


def is_runtime_control_path(relative: str) -> bool:
    return relative in RUNTIME_CONTROL_FILES or relative.startswith(RUNTIME_CONTROL_PREFIXES)


def git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def git_path_fingerprint(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if path.is_symlink():
        target = os.readlink(path)
        return {"kind": "symlink", "sha256": sha256_bytes(target.encode("utf-8"))}
    if path.is_file():
        stat = path.stat()
        return {"kind": "file", "sha256": sha256_file(path), "size": stat.st_size, "mode": stat.st_mode & 0o7777}
    if path.is_dir():
        records = [
            {"path": rel(root, child), "sha256": sha256_file(child)}
            for child in sorted(path.rglob("*")) if child.is_file()
        ]
        return {"kind": "directory", "sha256": sha256_bytes(canonical_json(records))}
    return {"kind": "missing", "sha256": None}


def capture_git_baseline(root: Path) -> dict[str, Any]:
    try:
        paths = [path for path in collect_git_changes(root) if not is_runtime_control_path(path)]
    except RuntimeErrorWithHint as exc:
        return {"available": False, "head": None, "paths": {}, "captured_at": now_iso(), "error": str(exc)}
    return {
        "available": True,
        "head": git_head(root),
        "paths": {path: git_path_fingerprint(root, path) for path in paths},
        "captured_at": now_iso(),
    }


def task_git_changes(root: Path, state: dict[str, Any]) -> tuple[list[str], str | None]:
    baseline = (state.get("side_effects") or {}).get("git_baseline")
    if not isinstance(baseline, dict) or baseline.get("available") is not True:
        detail = str((baseline or {}).get("error") or "Git baseline is unavailable")
        return [], detail
    if git_head(root) != baseline.get("head"):
        return [], "repository HEAD changed after the task baseline was captured"
    try:
        current = [path for path in collect_git_changes(root) if not is_runtime_control_path(path)]
    except RuntimeErrorWithHint as exc:
        return [], str(exc)
    before = baseline.get("paths") if isinstance(baseline.get("paths"), dict) else {}
    changed = [
        path
        for path in sorted(set(current) | set(before))
        if git_path_fingerprint(root, path) != before.get(path)
    ]
    return changed, None


def expand_change_paths(root: Path, paths: Sequence[str]) -> list[str]:
    expanded: list[str] = []
    for relative in paths:
        path = root / relative
        children = [rel(root, child) for child in sorted(path.rglob("*")) if child.is_file()] if path.is_dir() else []
        for item in children or [relative]:
            if item not in expanded:
                expanded.append(item)
    return expanded


def normal_context_exclusions(root: Path) -> tuple[str, ...]:
    configured: list[str] = []
    try:
        raw = read_json(runtime_dir(root) / "config.json").get("context", {}).get("excluded_normal_roots", [])
        if isinstance(raw, list):
            configured = [str(value).replace("\\", "/").rstrip("/") for value in raw if str(value).strip()]
    except RuntimeErrorWithHint:
        configured = []
    return tuple(dict.fromkeys((*MANDATORY_NORMAL_CONTEXT_EXCLUSIONS, *configured)))


def is_normal_context_excluded(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return True
    return any(relative == prefix or relative.startswith(prefix + "/") for prefix in normal_context_exclusions(root))


def ensure_normal_context_path(root: Path, value: Path) -> Path:
    path = ensure_under_root(root, value)
    if is_normal_context_excluded(root, path):
        raise RuntimeErrorWithHint(
            f"normal task context may not link or receipt excluded control-plane data: {rel(root, path)}; "
            "use explicit /cs observe or /cs meta commands instead"
        )
    return path


def normalize_linked_paths(root: Path, values: Any) -> list[Path]:
    if not isinstance(values, list):
        return []
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            path = ensure_normal_context_path(root, Path(value))
        except RuntimeErrorWithHint:
            continue
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def meaningful_attention(path: Path) -> bool:
    if not path.exists():
        return False
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    content = [line for line in lines if line and not line.startswith("#")]
    boilerplate = {
        "仅记录当前、短期、跨任务都必须反复看到的提醒。建议不超过 80 行；过期后删除或提升到 model/knowledge。",
        "仅记录当前且跨任务必须反复看到的短期提醒。",
    }
    return any(line not in boilerplate for line in content)


def build_candidates(root: Path, work_dir: Path, state: dict[str, Any], action: str) -> list[Candidate]:
    candidates = [Candidate(work_dir / "work.md", "current_work", ACTION_SECTIONS[action])]
    if action in {"verify", "learn"}:
        candidates.append(Candidate(evidence_path(work_dir), "current_evidence"))
    attention = runtime_dir(root) / "attention.md"
    if meaningful_attention(attention):
        candidates.append(Candidate(attention, "attention"))
    links = state.get("links") if isinstance(state.get("links"), dict) else {}
    model_links = normalize_linked_paths(root, links.get("model", []))
    knowledge_links = normalize_linked_paths(root, links.get("knowledge", []))
    if model_links:
        candidates.extend(Candidate(path, "linked_model") for path in model_links)
    elif action in {"inspect", "propose"}:
        candidates.append(Candidate(runtime_dir(root) / "model" / "INDEX.md", "model_pointer"))
    candidates.extend(Candidate(path, "linked_knowledge") for path in knowledge_links)
    scope = state.get("scope") if isinstance(state.get("scope"), dict) else {}
    for path in normalize_linked_paths(root, scope.get("paths", [])):
        candidates.append(Candidate(path, "scoped_source"))
    deduped: list[Candidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.path)
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def receipt_matches(path: Path, receipt: Any) -> bool:
    if not path.is_file() or not isinstance(receipt, dict):
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if receipt.get("size") != stat.st_size:
        return False
    expected = receipt.get("sha256")
    return isinstance(expected, str) and expected == sha256_file(path)


def candidate_payload(root: Path, candidate: Candidate, status: str, detail: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": rel(root, candidate.path) if candidate.path.exists() else str(candidate.path.relative_to(root)),
        "reason": candidate.reason,
        "status": status,
    }
    if candidate.sections:
        payload["sections"] = list(candidate.sections)
    if detail:
        payload["detail"] = detail
    return payload


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root) if args.root else Path.cwd().resolve()
    return init_runtime(root)


def command_new(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    init_runtime(root)
    slug = slugify(args.slug or args.title)
    work_id = unique_work_id(root, slug)
    work_dir = active_root(root) / work_id
    work_dir.mkdir(parents=True, exist_ok=False)
    level = normalize_risk(args.risk)
    allowed = normalize_patterns(args.allow_path or [])
    state = initial_state(
        args.kind,
        args.title,
        slug,
        level,
        work_id,
        owner_id=args.owner,
        allowed_paths=allowed,
        no_writes=args.no_writes,
    )
    state["side_effects"]["git_baseline"] = capture_git_baseline(root)
    write_json(work_dir / "state.json", state)
    atomic_write(work_dir / "work.md", work_template(args.kind, args.title, level, work_id))
    write_json(work_dir / "context.json", {"schema_version": CONTEXT_SCHEMA_VERSION, "sessions": {}})
    atomic_write(evidence_path(work_dir), "")
    refresh_state(work_dir, state)
    return {"id": work_id, "path": rel(root, work_dir), "state": state}


def command_list(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for directory in iter_active_dirs(root):
        try:
            state = load_state(directory)
            items.append({
                "id": state.get("id"),
                "kind": state.get("kind"),
                "title": state.get("title"),
                "risk": state.get("risk"),
                "current_action": state.get("current_action"),
                "status": state.get("status"),
                "completion": state.get("completion"),
                "updated_at": state.get("updated_at"),
                "path": rel(root, directory),
                "scope": state.get("scope", {}),
            })
        except RuntimeErrorWithHint as exc:
            errors.append({"path": rel(root, directory), "error": str(exc)})
    items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {"active": items, "errors": errors}


def command_show(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    result: dict[str, Any] = {"path": rel(root, work_dir), "state": state}
    if args.with_context:
        result["context"] = load_context(work_dir)
    if args.with_evidence:
        entries = read_evidence(work_dir)
        result["evidence"] = entries[-max(0, args.evidence_limit):] if args.evidence_limit else []
    return result


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    action = str(args.action or state.get("current_action") or "inspect").strip().casefold()
    if action not in ACTIONS:
        raise RuntimeErrorWithHint(f"action must be one of {', '.join(ACTIONS)}")
    context = load_context(work_dir)
    sessions = context.get("sessions", {}) if isinstance(context.get("sessions"), dict) else {}
    session_data = sessions.get(args.session, {}) if args.session else {}
    receipts = session_data.get("receipts", {}) if isinstance(session_data, dict) else {}
    receipts = receipts if isinstance(receipts, dict) else {}
    result: dict[str, Any] = {
        "work": state.get("id"),
        "kind": state.get("kind"),
        "risk": state.get("risk"),
        "action": action,
        "session": args.session,
        "always": [{"path": rel(root, work_dir / "state.json"), "reason": "control_state", "status": "read"}],
        "read": [],
        "reuse": [],
        "missing": [],
        "notes": [],
        "archive_search": False,
        "completion": state.get("completion"),
        "next_actions": (state.get("completion") or {}).get("next_actions", []),
    }
    if not args.session:
        result["notes"].append(
            "No --session key supplied: unchanged receipts are not reused. Use one stable key only within the current conversation."
        )
    for candidate in build_candidates(root, work_dir, state, action):
        path = candidate.path
        try:
            relative = rel(root, path)
        except (ValueError, OSError):
            result["missing"].append({"path": str(path), "reason": candidate.reason, "status": "missing"})
            continue
        if not path.is_file():
            result["missing"].append({"path": relative, "reason": candidate.reason, "status": "missing"})
            continue
        receipt = receipts.get(relative)
        if args.session and receipt_matches(path, receipt):
            result["reuse"].append(candidate_payload(root, candidate, "unchanged_in_session"))
        else:
            result["read"].append(candidate_payload(root, candidate, "read", "new_or_changed" if args.session else "cold_context"))
    scope = state.get("scope") if isinstance(state.get("scope"), dict) else {}
    keywords = [value for value in scope.get("keywords", []) if isinstance(value, str)] if isinstance(scope.get("keywords"), list) else []
    symbols = [value for value in scope.get("symbols", []) if isinstance(value, str)] if isinstance(scope.get("symbols"), list) else []
    if keywords or symbols:
        result["suggested_search"] = {
            "scope": "current",
            "query": " ".join((*symbols, *keywords)),
            "limit": min(5, int(read_json(runtime_dir(root) / "config.json").get("context", {}).get("max_search_hits", 5))),
        }
    return result


def prune_sessions(context: dict[str, Any], keep: int = 4) -> None:
    sessions = context.get("sessions", {})
    if not isinstance(sessions, dict) or len(sessions) <= keep:
        return
    ranked = sorted(
        sessions.items(),
        key=lambda item: str(item[1].get("updated_at", "")) if isinstance(item[1], dict) else "",
        reverse=True,
    )
    context["sessions"] = dict(ranked[:keep])


def command_receipt(args: argparse.Namespace) -> dict[str, Any]:
    if not args.session:
        raise RuntimeErrorWithHint("receipt requires --session; a receipt is reusable only within that live conversation")
    action = str(args.action).strip().casefold()
    if action not in ACTIONS:
        raise RuntimeErrorWithHint(f"action must be one of {', '.join(ACTIONS)}")
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    context = load_context(work_dir)
    sessions = context.setdefault("sessions", {})
    session_data = sessions.setdefault(args.session, {"created_at": now_iso(), "receipts": {}})
    if not isinstance(session_data, dict):
        session_data = {"created_at": now_iso(), "receipts": {}}
        sessions[args.session] = session_data
    receipts = session_data.setdefault("receipts", {})
    if not isinstance(receipts, dict):
        receipts = {}
        session_data["receipts"] = receipts
    recorded: list[dict[str, Any]] = []
    for raw in args.paths:
        path = ensure_normal_context_path(root, Path(raw))
        if not path.is_file():
            raise RuntimeErrorWithHint(f"receipt path is not a file: {raw}")
        relative = rel(root, path)
        entry = {**file_fingerprint(path), "read_at": now_iso(), "action": action, "reason": args.reason}
        receipts[relative] = entry
        recorded.append({"path": relative, **entry})
    session_data["updated_at"] = now_iso()
    prune_sessions(context)
    write_json(context_path(work_dir), context)
    return {"work": work_dir.name, "session": args.session, "recorded": recorded}


def unique_append(items: list[Any], values: Iterable[Any]) -> bool:
    changed = False
    for value in values:
        if value not in items:
            items.append(value)
            changed = True
    return changed


def command_link(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    changed = False
    state.setdefault("scope", {"paths": [], "symbols": [], "keywords": []})
    state.setdefault("links", {"model": [], "knowledge": [], "parent": None, "children": []})
    for field, values in (("model", args.model), ("knowledge", args.knowledge)):
        target = state["links"].setdefault(field, [])
        normalized = [rel(root, ensure_normal_context_path(root, Path(value))) for value in values]
        changed |= unique_append(target, normalized)
    normalized_paths = [rel(root, ensure_normal_context_path(root, Path(value))) for value in args.path]
    changed |= unique_append(state["scope"].setdefault("paths", []), normalized_paths)
    changed |= unique_append(state["scope"].setdefault("symbols", []), args.symbol)
    changed |= unique_append(state["scope"].setdefault("keywords", []), args.keyword)
    changed |= unique_append(state["links"].setdefault("children", []), args.child)
    if args.parent is not None and state["links"].get("parent") != args.parent:
        state["links"]["parent"] = args.parent
        changed = True
    if changed:
        state["updated_at"] = now_iso()
        refresh_state(work_dir, state)
    return {"work": work_dir.name, "changed": changed, "state": state}


def command_contract(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    goal = state.setdefault("goal", {})
    if args.objective is not None:
        goal["objective"] = args.objective.strip()
    for field, values in (
        ("constraints", args.constraint),
        ("non_goals", args.non_goal),
        ("invariants", args.invariant),
        ("acceptance", args.acceptance),
    ):
        target = goal.setdefault(field, [])
        if args.replace:
            target.clear()
        unique_append(target, [str(item).strip() for item in values if str(item).strip()])
    scope_target = goal.setdefault("acceptance_scope", [])
    if args.replace:
        scope_target.clear()
    unique_append(
        scope_target,
        normalize_acceptance_scope([
            str(item) for item in getattr(args, "acceptance_scope", []) if str(item).strip()
        ]),
    )
    state["updated_at"] = now_iso()
    refresh_state(work_dir, state)
    return {"work": work_dir.name, "goal": goal, "completion": state["completion"]}


def command_boundary(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    side = state.setdefault("side_effects", {})
    for field, values in (("allowed_paths", args.allow_path), ("forbidden_paths", args.forbid_path)):
        normalized = normalize_patterns(values)
        target = side.setdefault(field, [])
        if args.replace:
            target.clear()
        unique_append(target, normalized)
    categories = [str(item).strip().casefold() for item in args.category if str(item).strip()]
    unique_append(side.setdefault("categories", []), categories)
    unique_append(side.setdefault("requires_authorization", []), [str(item).strip() for item in args.authorization if str(item).strip()])
    if args.no_writes:
        side["no_writes"] = True
    if args.writes:
        side["no_writes"] = False
    if args.rollback_required:
        side["rollback_required"] = True
    if args.rollback_not_required and normalize_risk(state["risk"]["level"]) < 3:
        side["rollback_required"] = False
    if set(categories) & CRITICAL_SIDE_EFFECTS:
        escalate_risk(state, 3, sorted(set(categories) & CRITICAL_SIDE_EFFECTS), source="side_effect_boundary")
    state["updated_at"] = now_iso()
    refresh_state(work_dir, state)
    return {"work": work_dir.name, "side_effects": side, "risk": state["risk"], "completion": state["completion"]}


def command_action(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    action = args.name.strip().casefold()
    if action not in ACTIONS:
        raise RuntimeErrorWithHint(f"action must be one of {', '.join(ACTIONS)}")
    state["current_action"] = action
    if state.get("status") in {"blocked", "partial"}:
        state["status"] = "active"
    state["updated_at"] = now_iso()
    refresh_state(work_dir, state)
    return {"work": work_dir.name, "current_action": action, "next_actions": state["completion"]["next_actions"]}


def command_risk(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    target = normalize_risk(args.level)
    current = normalize_risk(state["risk"]["level"])
    if target < current:
        raise RuntimeErrorWithHint("risk may only increase during execution; create a new task contract to lower it")
    escalate_risk(state, target, args.reason or ["agent_assessment"], source=args.source)
    refresh_state(work_dir, state)
    return {"work": work_dir.name, "risk": state["risk"], "required_evidence": state["evidence"]["required"]}


def command_ledger_add(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    kind = args.kind
    timestamp = now_iso()
    if kind == "blocker":
        items = state.setdefault("blockers", [])
        entry = {
            "id": next_ledger_id(items, "blocker"),
            "text": args.text.strip(),
            "status": "open",
            "created_at": timestamp,
            "source": args.source,
        }
        items.append(entry)
    else:
        field = {"fact": "facts", "assumption": "assumptions", "risk": "risks", "change": "changes"}[kind]
        items = state.setdefault("ledger", {}).setdefault(field, [])
        entry = {
            "id": next_ledger_id(items, kind),
            "text": args.text.strip(),
            "status": "open" if kind in {"assumption", "risk"} else "recorded",
            "created_at": timestamp,
            "source": args.source,
        }
        if kind == "fact":
            entry["status"] = "confirmed"
        elif kind == "assumption":
            entry["blocking"] = not args.non_blocking
        elif kind == "risk":
            entry["severity"] = args.severity
            entry["blocking"] = args.blocking or args.severity in {"high", "critical"}
            entry["mitigation"] = args.mitigation
        elif kind == "change":
            paths = collect_git_changes(root) if args.from_git else normalize_patterns(args.path)
            paths = expand_change_paths(root, paths)
            if not paths:
                raise RuntimeErrorWithHint("change evidence requires --path or --from-git")
            violations = [path for path in paths if not path_allowed(state, path)]
            if violations:
                raise RuntimeErrorWithHint(
                    "change escapes side-effect boundary: " + ", ".join(violations)
                )
            entry["paths"] = paths
            entry["rollback"] = args.rollback
            entry["artifacts"] = [artifact_fingerprint(root, path) for path in paths]
            floor, reasons = path_risk_floor(paths)
            escalate_risk(state, floor, reasons, source="registered_change")
        items.append(entry)
    state["updated_at"] = timestamp
    refresh_state(work_dir, state)
    return {"work": work_dir.name, "entry": entry, "risk": state["risk"], "completion": state["completion"]}


def find_ledger_item(state: dict[str, Any], item_id: str) -> dict[str, Any]:
    for collection in (
        *((state.get("ledger") or {}).get(field, []) for field in ("facts", "assumptions", "risks", "changes")),
        state.get("blockers", []),
    ):
        if isinstance(collection, list):
            for item in collection:
                if isinstance(item, dict) and item.get("id") == item_id:
                    return item
    raise RuntimeErrorWithHint(f"ledger item not found: {item_id}")


def command_ledger_resolve(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    item = find_ledger_item(state, args.id)
    item["status"] = args.status
    item["resolution"] = args.resolution
    item["evidence_ids"] = list(dict.fromkeys(args.evidence_id))
    item["resolved_at"] = now_iso()
    state["updated_at"] = now_iso()
    refresh_state(work_dir, state)
    return {"work": work_dir.name, "item": item, "completion": state["completion"]}


def command_proposal(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    proposal = state.setdefault("proposal", {})
    proposal.update({
        "status": "ready",
        "summary": args.summary.strip(),
        "rationale": args.rationale.strip(),
        "non_changes": list(dict.fromkeys(str(item).strip() for item in args.non_change if str(item).strip())),
        "evidence_required": list(dict.fromkeys(str(item).strip().casefold() for item in args.evidence_required if str(item).strip())),
        "updated_at": now_iso(),
    })
    state["updated_at"] = now_iso()
    refresh_state(work_dir, state)
    return {"work": work_dir.name, "proposal": proposal, "completion": state["completion"]}


def command_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    evidence_type = args.type.strip().casefold()
    if evidence_type not in STATE_BACKED_EVIDENCE:
        raise RuntimeErrorWithHint(
            f"state snapshot type must be one of {', '.join(sorted(STATE_BACKED_EVIDENCE))}"
        )
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    goal = state.get("goal") or {}
    ledger = state.get("ledger") or {}
    side = state.get("side_effects") or {}
    failures: list[str] = []
    if evidence_type == "scope_inspect":
        if not ledger.get("facts"):
            failures.append("no confirmed facts")
        if side.get("no_writes") is not True and not side.get("allowed_paths"):
            failures.append("write scope is not bounded")
    elif evidence_type == "audit_ledger":
        if not ledger.get("facts"):
            failures.append("facts are empty")
        if "assumptions" not in ledger or "risks" not in ledger:
            failures.append("assumption/risk ledgers are missing")
    elif evidence_type == "full_audit":
        if not ledger.get("facts"):
            failures.append("facts are empty")
        if not goal.get("invariants"):
            failures.append("invariants are empty")
        if not side.get("categories") and side.get("no_writes") is not True:
            failures.append("side-effect categories are not classified")
    elif evidence_type == "proposal":
        if (state.get("proposal") or {}).get("status") != "ready":
            failures.append("proposal is not ready")
    elif evidence_type == "invariant_contract":
        if not goal.get("invariants"):
            failures.append("invariants are empty")
    status = "PASS" if not failures else "FAIL"
    snapshot = {
        "task_state_sha256": sha256_file(work_dir / "state.json"),
        "facts": len(ledger.get("facts") or []),
        "assumptions": len(ledger.get("assumptions") or []),
        "risks": len(ledger.get("risks") or []),
        "changes": len(ledger.get("changes") or []),
        "allowed_paths": list(side.get("allowed_paths") or []),
        "failures": failures,
    }
    entry = append_evidence(
        work_dir,
        state,
        evidence_type=evidence_type,
        status=status,
        producer="harness",
        source="state_snapshot",
        summary=args.summary or ("state snapshot satisfied" if not failures else "; ".join(failures)),
        artifacts=[artifact_fingerprint(root, rel(root, work_dir / "state.json"))],
        metadata=snapshot,
    )
    return {"work": work_dir.name, "evidence": entry, "completion": load_state(work_dir)["completion"]}


def command_record(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    artifacts = [artifact_fingerprint(root, item) for item in args.artifact]
    if not artifacts:
        raise RuntimeErrorWithHint("recorded evidence requires at least one existing artifact path")
    if any(item.get("kind") == "missing" for item in artifacts):
        missing = [str(item.get("path")) for item in artifacts if item.get("kind") == "missing"]
        raise RuntimeErrorWithHint("evidence artifact is missing: " + ", ".join(missing))
    evidence_type = args.type.strip().casefold()
    producer = args.producer.strip()
    if evidence_type == "independent_review":
        owner = str((state.get("actors") or {}).get("owner_id") or "owner")
        if not producer or producer == owner:
            raise RuntimeErrorWithHint("independent_review producer must differ from task owner")
        reviewers = state.setdefault("actors", {}).setdefault("reviewer_ids", [])
        if producer not in reviewers:
            reviewers.append(producer)
    metadata = {"verdict": args.verdict}
    if evidence_type == "independent_review":
        metadata["identity_assurance"] = "declarative"
    entry = append_evidence(
        work_dir,
        state,
        evidence_type=evidence_type,
        status=args.status,
        producer=producer,
        source="artifact_record",
        summary=args.summary,
        artifacts=artifacts,
        metadata=metadata,
        scope=getattr(args, "scope", []),
        reviewed_diff_sha256=getattr(args, "reviewed_diff_sha256", None),
    )
    return {"work": work_dir.name, "evidence": entry, "completion": load_state(work_dir)["completion"]}


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise RuntimeErrorWithHint("verify requires a command after `--`")
    cwd = ensure_under_root(root, Path(args.cwd or "."))
    started = time.monotonic()
    status = "BLOCKED"
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    reason = ""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=args.timeout,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        status = "PASS" if completed.returncode == 0 else "FAIL"
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        reason = f"command timed out after {args.timeout}s"
        status = "BLOCKED"
    except FileNotFoundError as exc:
        reason = str(exc)
        status = "BLOCKED"
    duration_ms = int((time.monotonic() - started) * 1000)
    artifacts = [artifact_fingerprint(root, item) for item in args.artifact]
    entry = append_evidence(
        work_dir,
        state,
        evidence_type=args.type.strip().casefold(),
        status=status,
        producer="harness",
        source="command_execution",
        summary=args.summary or reason,
        command=command,
        cwd=rel(root, cwd),
        exit_code=exit_code,
        duration_ms=duration_ms,
        artifacts=artifacts,
        stdout_tail=stdout,
        stderr_tail=stderr,
        metadata={"timeout_seconds": args.timeout, "blocked_reason": reason or None},
        scope=getattr(args, "scope", []),
    )
    return {"work": work_dir.name, "evidence": entry, "completion": load_state(work_dir)["completion"]}


def command_proof(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    entries = read_evidence(work_dir)
    level = normalize_risk(state["risk"]["level"])
    prerequisite_types = [item for item in RISK_REQUIREMENTS[level] if item != "proof"]
    current_bindings = current_evidence_bindings(root, state, entries)
    missing = []
    for evidence_type in prerequisite_types:
        passing = [
            item for item in entries
            if evidence_satisfies_requirement(
                state, item, evidence_type, root=root, current_bindings=current_bindings
            )
        ]
        if not passing:
            missing.append(evidence_type)
    current_passing = [
        item for item in entries
        if str(item.get("type") or "") in REQUIRED_EVIDENCE_SOURCES
        and evidence_satisfies_requirement(
            state,
            item,
            str(item.get("type")),
            root=root,
            current_bindings=current_bindings,
        )
    ]
    changes = (state.get("ledger") or {}).get("changes", [])
    proof = {
        "schema_version": 1,
        "work_id": state["id"],
        "generated_at": now_iso(),
        "risk": state["risk"],
        "goal": state["goal"],
        "side_effects": state["side_effects"],
        "changes": changes,
        "evidence_head_sha256": entries[-1].get("entry_sha256") if entries else None,
        "passing_evidence": [
            {"id": item.get("id"), "type": item.get("type"), "entry_sha256": item.get("entry_sha256")}
            for item in current_passing
        ],
        "missing_prerequisites": missing,
    }
    proof_path = work_dir / "proof.json"
    write_json(proof_path, proof)
    entry = append_evidence(
        work_dir,
        state,
        evidence_type="proof",
        status="PASS" if not missing else "FAIL",
        producer="harness",
        source="proof_assembly",
        summary=args.summary or ("proof assembled" if not missing else f"missing prerequisites: {', '.join(missing)}"),
        artifacts=[artifact_fingerprint(root, rel(root, proof_path))],
        metadata={"missing_prerequisites": missing},
    )
    return {
        "work": work_dir.name,
        "proof": rel(root, proof_path),
        "evidence": entry,
        "completion": load_state(work_dir)["completion"],
    }


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    return {
        "work": work_dir.name,
        "risk": state["risk"],
        "completion": state["completion"],
        "evidence": state["evidence"],
    }


def command_complete(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    result = args.result
    if result == "done":
        if not state["completion"].get("eligible"):
            details = "; ".join(item.get("detail", "") for item in state["completion"].get("missing", [])[:8])
            raise RuntimeErrorWithHint(f"completion denied: {details or 'open risks, assumptions or blockers remain'}")
        state["status"] = "done"
        state["completion"]["status"] = "COMPLETED"
        state["completion"]["completed_at"] = now_iso()
    elif result == "blocked":
        if not state["completion"].get("blockers") and not args.reason:
            raise RuntimeErrorWithHint("blocked result requires an open blocker or --reason")
        state["status"] = "blocked"
        state["completion"]["status"] = "BLOCKED"
    elif result == "partial":
        if not args.reason:
            raise RuntimeErrorWithHint("partial result requires --reason")
        state["status"] = "partial"
        state["completion"]["status"] = "PARTIAL"
    elif result == "cancelled":
        state["status"] = "cancelled"
        state["completion"]["status"] = "CANCELLED"
    state["completion"]["reason"] = args.reason or None
    state["updated_at"] = now_iso()
    write_json(work_dir / "state.json", state)
    return {"work": work_dir.name, "status": state["status"], "completion": state["completion"]}


def query_terms(query: str) -> list[str]:
    normalized = query.casefold().strip()
    words = re.findall(r"[\w.-]+", normalized, flags=re.UNICODE)
    terms: list[str] = []
    for word in words:
        if word not in terms:
            terms.append(word)
        cjk = "".join(char for char in word if "\u3400" <= char <= "\u9fff")
        if len(cjk) >= 4:
            for index in range(len(cjk) - 1):
                gram = cjk[index:index + 2]
                if gram not in terms:
                    terms.append(gram)
    return terms or [normalized]


def iter_text_files(base: Path) -> Iterator[Path]:
    if not base.exists():
        return
    if base.is_file():
        if base.suffix.casefold() in TEXT_SUFFIXES and base.stat().st_size <= 1024 * 1024:
            yield base
        return
    for path in base.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if any(part in {".git", "node_modules", "vendor", "dist", "build", "__pycache__"} for part in path.parts):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= 1024 * 1024 and path.suffix.casefold() in TEXT_SUFFIXES:
            yield path


def search_bases(root: Path, scope: str, deep_archive: bool = False) -> list[Path]:
    cs = runtime_dir(root)
    archive_source = cs / "work" / "archive" if deep_archive else cs / "work" / "archive-index.jsonl"
    return {
        "model": [cs / "model"],
        "knowledge": [cs / "knowledge"],
        "active": [cs / "work" / "active"],
        "archive": [archive_source],
        "current": [cs / "model", cs / "knowledge"],
        "all": [cs / "model", cs / "knowledge", cs / "work" / "active", archive_source],
    }[scope]


def first_snippet(text: str, terms: Sequence[str], width: int = 240) -> str:
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if term and folded.find(term) >= 0]
    position = min(positions) if positions else 0
    start = max(0, position - width // 3)
    end = min(len(text), start + width)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if start:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


def score_text(path: Path, text: str, query: str, terms: Sequence[str]) -> int:
    folded = text.casefold()
    path_text = path.as_posix().casefold()
    score = 0
    phrase = query.casefold().strip()
    if phrase and phrase in folded:
        score += 20
    if phrase and phrase in path_text:
        score += 30
    for term in terms:
        if not term:
            continue
        score += min(folded.count(term), 8) * 2
        if term in path_text:
            score += 8
    return score


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    deep_archive = bool(getattr(args, "deep", False))
    if args.scope == "archive" and not args.reason:
        raise RuntimeErrorWithHint("archive search requires --reason so historical retrieval is deliberate")
    if args.scope == "all" and not args.reason:
        raise RuntimeErrorWithHint("all-scope search includes archive and requires --reason")
    if deep_archive and args.scope not in {"archive", "all"}:
        raise RuntimeErrorWithHint("--deep is only valid for archive/all scopes")
    terms = query_terms(args.query)
    ranked: list[tuple[int, Path, str]] = []
    for base in search_bases(root, args.scope, deep_archive):
        for path in iter_text_files(base):
            if is_normal_context_excluded(root, path) and args.scope not in {"archive", "all"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            score = score_text(path, text, args.query, terms)
            if score > 0:
                ranked.append((score, path, first_snippet(text, terms)))
    ranked.sort(key=lambda item: (-item[0], item[1].as_posix()))
    limit = max(0, min(args.limit, 50))
    results = [{"score": score, "path": rel(root, path), "snippet": snippet} for score, path, snippet in ranked[:limit]]
    return {
        "query": args.query,
        "scope": args.scope,
        "reason": args.reason,
        "results": results,
        "searched_archive": args.scope in {"archive", "all"},
        "deep_archive": deep_archive,
        "note": (
            "archive index only; open a matched work path or rerun with --deep when content archaeology is necessary"
            if args.scope in {"archive", "all"} and not deep_archive else None
        ),
    }


def command_archive(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    status = str(state.get("status"))
    if status not in {"done", "cancelled"}:
        raise RuntimeErrorWithHint(
            f"work status is {status!r}; only evidence-completed or cancelled work may be archived"
        )
    if status == "done" and state.get("completion", {}).get("status") != "COMPLETED":
        raise RuntimeErrorWithHint("done work lacks a Harness completion verdict")
    if status == "done" and state.get("evidence", {}).get("integrity") != "valid":
        raise RuntimeErrorWithHint("completed work has invalid evidence integrity")
    if status == "done" and state.get("completion", {}).get("eligible") is not True:
        raise RuntimeErrorWithHint("completed work is no longer archive-eligible")
    completed_at = state.get("completion", {}).get("completed_at") or now_iso()
    original_state = (work_dir / "state.json").read_text(encoding="utf-8")
    state["status"] = "archived"
    state["updated_at"] = now_iso()
    year = str(completed_at)[:4]
    destination_parent = archived_root(root) / year
    destination_parent.mkdir(parents=True, exist_ok=True)
    destination = destination_parent / work_dir.name
    if destination.exists():
        raise RuntimeErrorWithHint(f"archive destination already exists: {destination}")
    write_json(work_dir / "state.json", state)
    try:
        shutil.move(str(work_dir), str(destination))
    except OSError:
        if work_dir.exists():
            atomic_write(work_dir / "state.json", original_state)
        raise
    index_entry = {
        "id": state.get("id"),
        "kind": state.get("kind"),
        "title": state.get("title"),
        "slug": state.get("slug"),
        "risk": state.get("risk"),
        "completion": state.get("completion"),
        "completed_at": completed_at,
        "summary": args.summary or "",
        "scope": state.get("scope", {}),
        "path": rel(root, destination),
    }
    index_path = runtime_dir(root) / "work" / "archive-index.jsonl"
    append_jsonl(index_path, index_entry)
    return {"archived": index_entry}


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    cs = runtime_dir(root)
    findings: list[dict[str, str]] = []
    required_dirs = [cs / "model", cs / "knowledge", cs / "work" / "active", cs / "work" / "archive", cs / "reference", cs / "tools"]
    try:
        config = read_json(cs / "config.json")
        observability_enabled = bool(config.get("observability", {}).get("enabled", False))
        evolution_enabled = bool(config.get("evolution", {}).get("enabled", False))
    except RuntimeErrorWithHint:
        config = {}
        observability_enabled = False
        evolution_enabled = False
    if observability_enabled:
        required_dirs.extend([cs / "observations" / "pending", cs / "observations" / "flagged", cs / "observations" / "selected"])
    if evolution_enabled:
        required_dirs.extend([cs / "harness", cs / "evolution" / "cases", cs / "evals", cs / "meta" / "campaigns", cs / "meta" / "feedback" / "items"])
    for directory in required_dirs:
        if not directory.is_dir():
            findings.append({"level": "error", "message": f"missing directory: {rel(root, directory)}"})

    try:
        if config.get("artifacts", {}).get("mode") != "evidence_state":
            findings.append({"level": "error", "message": "artifacts.mode must be evidence_state"})
        required_files = set(config.get("artifacts", {}).get("required_active_files") or [])
        for required in ("state.json", "work.md", "context.json", "evidence.jsonl"):
            if required not in required_files:
                findings.append({"level": "error", "message": f"required active artifact missing from config: {required}"})
        control = config.get("control_plane", {})
        if control.get("state_model") != "evidence":
            findings.append({"level": "error", "message": "control_plane.state_model must be evidence"})
        if control.get("actions") != list(ACTIONS):
            findings.append({"level": "error", "message": "control_plane.actions must be Inspect/Propose/Execute/Verify/Learn"})
        if control.get("completion_authority") != "harness":
            findings.append({"level": "error", "message": "completion authority must be harness"})
        for level in RISK_LEVELS:
            policy = (control.get("risk_levels") or {}).get(str(level), {})
            missing = set(RISK_REQUIREMENTS[level]) - set(policy.get("required_evidence") or [])
            if missing:
                findings.append({"level": "error", "message": f"risk L{level} missing evidence requirements: {sorted(missing)}"})
            if level >= 2 and policy.get("independent_reviewer") is not True:
                findings.append({"level": "error", "message": f"risk L{level} must require independent reviewer"})
            if level == 3 and policy.get("rollback_required") is not True:
                findings.append({"level": "error", "message": "risk L3 must require rollback"})
        if config.get("execution", {}).get("mode") != "evidence_convergence":
            findings.append({"level": "error", "message": "execution.mode must be evidence_convergence"})
        if config.get("gates", {}).get("policy") != "risk_and_evidence":
            findings.append({"level": "error", "message": "gates.policy must be risk_and_evidence"})
        exclusions = set(config.get("context", {}).get("excluded_normal_roots") or [])
        missing_exclusions = set(MANDATORY_NORMAL_CONTEXT_EXCLUSIONS) - exclusions
        if missing_exclusions:
            findings.append({"level": "error", "message": f"normal context is missing protected exclusions: {sorted(missing_exclusions)}"})
        observability = config.get("observability", {})
        if observability.get("mode") != "passive" or observability.get("best_effort") is not True:
            findings.append({"level": "error", "message": "observability must be passive and best-effort"})
        if observability.get("read_during_normal_runs") is not False:
            findings.append({"level": "error", "message": "normal runs must not read observations"})
        capture = observability.get("capture", {})
        for field in ("raw_prompts", "raw_model_responses", "source_or_diffs", "full_tool_output"):
            if capture.get(field) is not False:
                findings.append({"level": "error", "message": f"observability.capture.{field} must be false"})
        evolution = config.get("evolution", {})
        if evolution.get("mode") != "manual" or evolution.get("run_during_normal_work") is not False:
            findings.append({"level": "error", "message": "evolution must be manual and disabled during normal work"})
        for field in ("auto_diagnose", "auto_propose", "auto_evaluate", "auto_promote"):
            if evolution.get(field) is not False:
                findings.append({"level": "error", "message": f"evolution.{field} must be false"})
        if evolution.get("require_selected_cases") is not True or evolution.get("require_private_holdout") is not True:
            findings.append({"level": "error", "message": "Harness evolution requires selected cases and private holdout"})
        if evolution.get("require_validity_prepass") is not True or evolution.get("require_fixture_covered_policy") is not True:
            findings.append({"level": "error", "message": "Harness evolution requires validity and fixture coverage"})
        if evolution.get("promotion_authority") != "owner_checkpoint_by_policy":
            findings.append({"level": "error", "message": "Harness promotion authority must be policy-scoped"})
        meta = config.get("meta", {})
        if meta.get("normal_runs_may_import_meta") is not False:
            findings.append({"level": "error", "message": "normal runs must not import the Meta control plane"})
        if (meta.get("trigger") or {}).get("mode") != "scan_only_by_default":
            findings.append({"level": "error", "message": "Meta trigger may only scan/open campaigns by default"})
        if int((meta.get("validity") or {}).get("minimum_stochastic_repeats", 0)) < 5:
            findings.append({"level": "error", "message": "stochastic Meta verdicts require k>=5"})
        evaluator = config.get("evaluator", {})
        if evaluator.get("mode") != "external_signed_aggregate" or evaluator.get("require_signed_results") is not True:
            findings.append({"level": "error", "message": "trusted evaluator must use signed external aggregates"})
        if evaluator.get("signing_algorithm") != "hmac-sha256":
            findings.append({"level": "error", "message": "evaluator.signing_algorithm must be hmac-sha256"})
        if evaluator.get("private_holdout_location") != "outside_candidate_workspace":
            findings.append({"level": "error", "message": "private holdout must stay outside candidate workspace"})
    except (RuntimeErrorWithHint, TypeError, ValueError) as exc:
        findings.append({"level": "error", "message": str(exc)})

    attention = cs / "attention.md"
    if attention.exists():
        line_count = len(attention.read_text(encoding="utf-8", errors="replace").splitlines())
        max_lines = int(config.get("context", {}).get("max_attention_lines", 80)) if config else 80
        if line_count > max_lines:
            findings.append({"level": "warning", "message": f"attention.md has {line_count} lines (limit {max_lines})"})
    max_index_lines = int(config.get("context", {}).get("max_index_lines", 160)) if config else 160
    for index_path in (cs / "model" / "INDEX.md", cs / "knowledge" / "INDEX.md"):
        if index_path.exists():
            line_count = len(index_path.read_text(encoding="utf-8", errors="replace").splitlines())
            if line_count > max_index_lines:
                findings.append({"level": "warning", "message": f"{rel(root, index_path)} has {line_count} lines (limit {max_index_lines})"})

    ids: set[str] = set()
    for directory in iter_active_dirs(root):
        for required in ("state.json", "work.md", "context.json", "evidence.jsonl"):
            if not (directory / required).is_file():
                findings.append({"level": "error", "message": f"{rel(root, directory)} missing {required}"})
        try:
            state = load_state(directory)
            work_id = str(state.get("id"))
            if work_id in ids:
                findings.append({"level": "error", "message": f"duplicate active work id: {work_id}"})
            ids.add(work_id)
            if work_id != directory.name:
                findings.append({"level": "warning", "message": f"directory/id mismatch: {directory.name} != {work_id}"})
            if state.get("kind") not in WORK_KINDS:
                findings.append({"level": "error", "message": f"unknown kind in {work_id}: {state.get('kind')}"})
            if state.get("current_action") not in ACTIONS:
                findings.append({"level": "error", "message": f"unknown action in {work_id}: {state.get('current_action')}"})
            normalize_risk((state.get("risk") or {}).get("level"))
            if state.get("evidence", {}).get("integrity") != "valid":
                findings.append({"level": "error", "message": f"evidence integrity failure in {work_id}"})
        except RuntimeErrorWithHint as exc:
            findings.append({"level": "error", "message": str(exc)})
    errors = sum(1 for item in findings if item["level"] == "error")
    warnings = sum(1 for item in findings if item["level"] == "warning")
    return {"root": str(root), "ok": errors == 0, "errors": errors, "warnings": warnings, "findings": findings}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root", help="project root (also accepted after the subcommand)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_root(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root", help="project root; otherwise discover from current directory")

    init_p = sub.add_parser("init", help="create the minimal runtime without overwriting project data")
    add_root(init_p); init_p.set_defaults(func=command_init)

    new_p = sub.add_parser("new", help="create an evidence-state task")
    add_root(new_p)
    new_p.add_argument("kind", choices=WORK_KINDS)
    new_p.add_argument("title")
    new_p.add_argument("--slug")
    new_p.add_argument("--risk", type=int, choices=RISK_LEVELS, default=1)
    new_p.add_argument("--owner", default="owner")
    new_p.add_argument("--allow-path", action="append", default=[])
    new_p.add_argument("--no-writes", action="store_true")
    new_p.set_defaults(func=command_new)

    list_p = sub.add_parser("list", help="list active work using evidence-state metadata only")
    add_root(list_p); list_p.set_defaults(func=command_list)

    show_p = sub.add_parser("show", help="show one task state")
    add_root(show_p)
    show_p.add_argument("--work", required=True)
    show_p.add_argument("--with-context", action="store_true")
    show_p.add_argument("--with-evidence", action="store_true")
    show_p.add_argument("--evidence-limit", type=int, default=20)
    show_p.set_defaults(func=command_show)

    plan_p = sub.add_parser("plan", help="plan action-specific reads from missing facts/evidence; never scans archive")
    add_root(plan_p)
    plan_p.add_argument("--work", required=True)
    plan_p.add_argument("--action", choices=ACTIONS)
    plan_p.add_argument("--session")
    plan_p.set_defaults(func=command_plan)

    receipt_p = sub.add_parser("receipt", help="record file versions read in the current conversation")
    add_root(receipt_p)
    receipt_p.add_argument("--work", required=True)
    receipt_p.add_argument("--session", required=True)
    receipt_p.add_argument("--action", choices=ACTIONS, required=True)
    receipt_p.add_argument("--reason", required=True)
    receipt_p.add_argument("paths", nargs="+")
    receipt_p.set_defaults(func=command_receipt)

    link_p = sub.add_parser("link", help="add current model/knowledge links and scope hints")
    add_root(link_p)
    link_p.add_argument("--work", required=True)
    link_p.add_argument("--model", action="append", default=[])
    link_p.add_argument("--knowledge", action="append", default=[])
    link_p.add_argument("--path", action="append", default=[])
    link_p.add_argument("--symbol", action="append", default=[])
    link_p.add_argument("--keyword", action="append", default=[])
    link_p.add_argument("--parent")
    link_p.add_argument("--child", action="append", default=[])
    link_p.set_defaults(func=command_link)

    contract_p = sub.add_parser("contract", help="set objective, constraints, non-goals, invariants and acceptance")
    add_root(contract_p)
    contract_p.add_argument("--work", required=True)
    contract_p.add_argument("--objective")
    contract_p.add_argument("--constraint", action="append", default=[])
    contract_p.add_argument("--non-goal", action="append", default=[])
    contract_p.add_argument("--invariant", action="append", default=[])
    contract_p.add_argument("--acceptance", action="append", default=[])
    contract_p.add_argument(
        "--acceptance-scope",
        action="append",
        default=[],
        help="bind acceptance to [evidence_type=]scope, e.g. live_validation=scenario:*",
    )
    contract_p.add_argument("--replace", action="store_true")
    contract_p.set_defaults(func=command_contract)

    boundary_p = sub.add_parser("boundary", help="declare side-effect and authorization boundaries")
    add_root(boundary_p)
    boundary_p.add_argument("--work", required=True)
    boundary_p.add_argument("--allow-path", action="append", default=[])
    boundary_p.add_argument("--forbid-path", action="append", default=[])
    boundary_p.add_argument("--category", action="append", default=[])
    boundary_p.add_argument("--authorization", action="append", default=[])
    boundary_p.add_argument("--rollback-required", action="store_true")
    boundary_p.add_argument("--rollback-not-required", action="store_true")
    boundary_p.add_argument("--no-writes", action="store_true")
    boundary_p.add_argument("--writes", action="store_true")
    boundary_p.add_argument("--replace", action="store_true")
    boundary_p.set_defaults(func=command_boundary)

    action_p = sub.add_parser("action", help="record the Agent's current control action; actions may repeat or reorder")
    add_root(action_p)
    action_p.add_argument("--work", required=True)
    action_p.add_argument("--name", choices=ACTIONS, required=True)
    action_p.set_defaults(func=command_action)

    risk_p = sub.add_parser("risk", help="monotonically increase task risk and evidence requirements")
    add_root(risk_p)
    risk_p.add_argument("--work", required=True)
    risk_p.add_argument("--level", type=int, choices=RISK_LEVELS, required=True)
    risk_p.add_argument("--reason", action="append", default=[])
    risk_p.add_argument("--source", default="agent_assessment")
    risk_p.set_defaults(func=command_risk)

    ledger_add = sub.add_parser("ledger-add", help="add a fact, assumption, risk, change or blocker")
    add_root(ledger_add)
    ledger_add.add_argument("--work", required=True)
    ledger_add.add_argument("kind", choices=LEDGER_KINDS)
    ledger_add.add_argument("text")
    ledger_add.add_argument("--source", default="agent")
    ledger_add.add_argument("--non-blocking", action="store_true")
    ledger_add.add_argument("--severity", choices=RISK_SEVERITIES, default="medium")
    ledger_add.add_argument("--blocking", action="store_true")
    ledger_add.add_argument("--mitigation", default="")
    ledger_add.add_argument("--path", action="append", default=[])
    ledger_add.add_argument("--from-git", action="store_true")
    ledger_add.add_argument("--rollback", default="")
    ledger_add.set_defaults(func=command_ledger_add)

    ledger_resolve = sub.add_parser("ledger-resolve", help="resolve an assumption, risk or blocker with evidence links")
    add_root(ledger_resolve)
    ledger_resolve.add_argument("--work", required=True)
    ledger_resolve.add_argument("--id", required=True)
    ledger_resolve.add_argument("--status", choices=("confirmed", "rejected", "closed", "accepted"), required=True)
    ledger_resolve.add_argument("--resolution", required=True)
    ledger_resolve.add_argument("--evidence-id", action="append", default=[])
    ledger_resolve.set_defaults(func=command_ledger_resolve)

    proposal_p = sub.add_parser("proposal", help="record a bounded, testable proposed change")
    add_root(proposal_p)
    proposal_p.add_argument("--work", required=True)
    proposal_p.add_argument("--summary", required=True)
    proposal_p.add_argument("--rationale", required=True)
    proposal_p.add_argument("--non-change", action="append", default=[])
    proposal_p.add_argument("--evidence-required", action="append", default=[])
    proposal_p.set_defaults(func=command_proposal)

    snapshot_p = sub.add_parser("snapshot", help="derive state-backed evidence; the Agent cannot self-assert it")
    add_root(snapshot_p)
    snapshot_p.add_argument("--work", required=True)
    snapshot_p.add_argument("--type", choices=sorted(STATE_BACKED_EVIDENCE), required=True)
    snapshot_p.add_argument("--summary", default="")
    snapshot_p.set_defaults(func=command_snapshot)

    record_p = sub.add_parser("record", help="record fingerprinted external artifact evidence")
    add_root(record_p)
    record_p.add_argument("--work", required=True)
    record_p.add_argument("--type", required=True)
    record_p.add_argument("--status", choices=EVIDENCE_STATUSES, required=True)
    record_p.add_argument("--producer", required=True)
    record_p.add_argument("--artifact", action="append", required=True)
    record_p.add_argument("--summary", default="")
    record_p.add_argument("--verdict", choices=EVIDENCE_STATUSES)
    record_p.add_argument("--scope", action="append", default=[])
    record_p.add_argument(
        "--reviewed-diff-sha256",
        help="optional reviewer-declared source snapshot; must equal the current diff binding",
    )
    record_p.set_defaults(func=command_record)

    verify_p = sub.add_parser("verify", help="execute a real command and append immutable evidence")
    add_root(verify_p)
    verify_p.add_argument("--work", required=True)
    verify_p.add_argument("--type", required=True)
    verify_p.add_argument("--cwd", default=".")
    verify_p.add_argument("--timeout", type=int, default=300)
    verify_p.add_argument("--artifact", action="append", default=[])
    verify_p.add_argument("--scope", action="append", default=[])
    verify_p.add_argument("--summary", default="")
    verify_p.add_argument("command", nargs=argparse.REMAINDER)
    verify_p.set_defaults(func=command_verify)

    proof_p = sub.add_parser("proof", help="assemble a machine-generated proof artifact from recorded evidence")
    add_root(proof_p)
    proof_p.add_argument("--work", required=True)
    proof_p.add_argument("--summary", default="")
    proof_p.set_defaults(func=command_proof)

    check_p = sub.add_parser("check", help="show missing evidence, open risks and completion eligibility")
    add_root(check_p)
    check_p.add_argument("--work", required=True)
    check_p.set_defaults(func=command_check)

    complete_p = sub.add_parser("complete", help="claim done/partial/blocked/cancelled under the Harness gate")
    add_root(complete_p)
    complete_p.add_argument("--work", required=True)
    complete_p.add_argument("--result", choices=("done", "partial", "blocked", "cancelled"), required=True)
    complete_p.add_argument("--reason")
    complete_p.set_defaults(func=command_complete)

    search_p = sub.add_parser("search", help="search current model/knowledge; archive requires explicit reason")
    add_root(search_p)
    search_p.add_argument("query")
    search_p.add_argument("--scope", choices=("current", "model", "knowledge", "active", "archive", "all"), default="current")
    search_p.add_argument("--limit", type=int, default=5)
    search_p.add_argument("--reason")
    search_p.add_argument("--deep", action="store_true")
    search_p.set_defaults(func=command_search)

    archive_p = sub.add_parser("archive", help="archive only evidence-completed or cancelled work")
    add_root(archive_p)
    archive_p.add_argument("--work", required=True)
    archive_p.add_argument("--summary")
    archive_p.set_defaults(func=command_archive)

    doctor_p = sub.add_parser("doctor", help="validate runtime, task schema, evidence integrity and completion policy")
    add_root(doctor_p); doctor_p.set_defaults(func=command_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "root", None):
        args.root = getattr(args, "global_root", None)
    try:
        result = args.func(args)
    except RuntimeErrorWithHint as exc:
        print(json_dump({"ok": False, "error": str(exc)}), file=sys.stderr, end="")
        return 2
    except KeyboardInterrupt:
        print(json_dump({"ok": False, "error": "interrupted"}), file=sys.stderr, end="")
        return 130
    print(json_dump(result), end="")
    if args.command == "doctor" and not result.get("ok", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
