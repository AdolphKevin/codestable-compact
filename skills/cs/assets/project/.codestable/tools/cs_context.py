#!/usr/bin/env python3
"""CodeStable Compact deterministic runtime helper.

The tool deliberately handles only mechanics: work state, context receipts,
small text search and archival. Semantic routing and engineering judgment stay
with the agent and the human.
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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SCHEMA_VERSION = 1
WORK_KINDS = ("feature", "issue", "refactor", "roadmap", "model")
LANES = ("micro", "standard", "high-risk")
VALIDATION_RESULTS = ("not_run", "passed", "failed", "blocked")
DEFAULT_STAGE = {
    "feature": "intake",
    "issue": "intake",
    "refactor": "intake",
    "roadmap": "discover",
    "model": "inspect",
}
STAGE_SECTIONS = {
    "intake": ["Intent and acceptance", "Evidence"],
    "evidence": ["Intent and acceptance", "Evidence"],
    "design": ["Intent and acceptance", "Evidence", "Design or root cause", "Plan"],
    "implement": ["Design or root cause", "Plan", "Changes and decisions"],
    "verify": ["Intent and acceptance", "Changes and decisions", "Verification and review"],
    "accept": ["Intent and acceptance", "Verification and review", "Promotion and closure"],
    "reproduce": ["Intent and acceptance", "Evidence"],
    "analyze": ["Evidence", "Design or root cause", "Plan"],
    "fix": ["Design or root cause", "Plan", "Changes and decisions"],
    "characterize": ["Intent and acceptance", "Evidence"],
    "discover": ["Intent and acceptance", "Evidence"],
    "frame": ["Intent and acceptance", "Evidence", "Design or root cause"],
    "contracts": ["Design or root cause", "Plan"],
    "decompose": ["Design or root cause", "Plan"],
    "review": ["Intent and acceptance", "Design or root cause", "Plan", "Verification and review"],
    "activate": ["Plan", "Changes and decisions", "Promotion and closure"],
    "inspect": ["Intent and acceptance", "Evidence"],
    "edit": ["Evidence", "Changes and decisions"],
    "validate": ["Changes and decisions", "Verification and review"],
    "index": ["Verification and review", "Promotion and closure"],
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


DEFAULT_CONFIG: dict[str, Any] = {'artifacts': {'mode': 'adaptive', 'required_active_files': ['state.json', 'work.md', 'context.json']}, 'context': {'archive_default': 'off', 'excluded_normal_roots': ['.codestable/observations', '.codestable/evolution', '.codestable/evals', '.codestable/harness/versions', '.codestable/meta', '.codestable/feedback'], 'max_attention_lines': 80, 'max_index_lines': 160, 'max_search_hits': 5, 'normal_roots': ['.codestable/model', '.codestable/knowledge', '.codestable/work/active'], 'reuse_unchanged_receipts': True}, 'entry': {'mode': 'auto', 'route_summary': 'compact'}, 'evaluator': {'mode': 'external_signed_aggregate', 'private_holdout_location': 'outside_candidate_workspace', 'require_signed_results': True, 'signing_algorithm': 'hmac-sha256', 'signing_key_env': 'CODESTABLE_EVALUATOR_KEY', 'signing_key_id_env': 'CODESTABLE_EVALUATOR_KEY_ID'}, 'evolution': {'auto_diagnose': False, 'auto_evaluate': False, 'auto_promote': False, 'auto_propose': False, 'enabled': True, 'mode': 'manual', 'promotion_authority': 'owner_checkpoint_by_policy', 'require_fixture_covered_policy': True, 'require_private_holdout': True, 'require_selected_cases': True, 'require_validity_prepass': True, 'run_during_normal_work': False}, 'execution': {'mode': 'continuous_until_gate'}, 'gates': {'pause_on': ['irreversible_or_destructive', 'public_contract_choice', 'security_boundary', 'persistent_data_migration', 'material_cost_or_availability', 'accepted_decision_conflict', 'unobservable_acceptance', 'harness_promotion'], 'policy': 'risk_based'}, 'meta': {'acceptance': {'required_gate_label': 'measured', 'required_quality_gates': ['policy_audit', 'validity_prepass', 'regression', 'package']}, 'budgets': {'max_evaluation_trials': 300, 'max_open_campaigns': 5, 'max_variants_per_campaign': 3}, 'enabled': True, 'normal_runs_may_import_meta': False, 'trigger': {'enabled': True, 'max_campaigns_per_scan': 2, 'max_feedback_per_campaign': 20, 'minimum_matching_signals': 3, 'mode': 'scan_only_by_default'}, 'validity': {'minimum_stochastic_repeats': 5, 'require_calibrated_scorer': True, 'require_committed_hypothesis': True, 'require_context_complete': True, 'require_judge_isolation': True}}, 'observability': {'best_effort': True, 'capture': {'event_metadata': True, 'full_tool_output': False, 'raw_model_responses': False, 'raw_prompts': False, 'source_or_diffs': False, 'user_corrections': True, 'verification_evidence': True}, 'enabled': True, 'limits': {'max_event_payload_bytes': 8192, 'max_events': 500, 'max_run_size_kb': 256, 'max_string_chars': 2048}, 'mode': 'passive', 'read_during_normal_runs': False, 'retention': {'flagged_days': 180, 'max_pending_runs': 200, 'pending_days': 30, 'stale_running_days': 7}}, 'schema_version': 3}



class RuntimeErrorWithHint(RuntimeError):
    """A user-actionable runtime error."""


@dataclass(frozen=True)
class Candidate:
    path: Path
    reason: str
    sections: tuple[str, ...] = ()


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeErrorWithHint(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeErrorWithHint(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeErrorWithHint(f"expected JSON object in {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json_dump(data))


def deep_merge(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in defaults.items():
        if key not in existing:
            result[key] = value
        elif isinstance(value, dict) and isinstance(existing[key], dict):
            result[key] = deep_merge(value, existing[key])
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
    """Preserve user settings while making the control-plane split immutable."""
    merged = deep_merge(DEFAULT_CONFIG, value)
    merged.pop("telemetry", None)
    merged["schema_version"] = 3

    context = merged.setdefault("context", {})
    configured = context.get("excluded_normal_roots")
    exclusions = [str(item) for item in configured] if isinstance(configured, list) else []
    context["excluded_normal_roots"] = list(dict.fromkeys((*MANDATORY_NORMAL_CONTEXT_EXCLUSIONS, *exclusions)))

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
    """Migrate legacy settings, then enforce passive/manual safety invariants."""
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
                "retention": {
                    "pending_days": safe_positive_int(legacy_telemetry.get("retention_days"), 30),
                },
            })
        migrated["observability"] = observation
        old_evolution = migrated.get("evolution")
        enabled = bool(old_evolution.get("enabled", True)) if isinstance(old_evolution, dict) else True
        migrated["evolution"] = {**DEFAULT_CONFIG["evolution"], "enabled": enabled}

    migration = migrated.setdefault("migration", {})
    if isinstance(migration, dict) and isinstance(legacy_telemetry, dict):
        migration.setdefault("legacy_telemetry_config", legacy_telemetry)
    migrated["schema_version"] = 3
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


def ensure_under_root(root: Path, path: Path) -> Path:
    resolved = path.expanduser()
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeErrorWithHint(f"path escapes project root: {path}") from exc
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
    return {
        "sha256": sha256_file(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


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
    slug = "".join(normalized).strip("-")
    if not slug:
        slug = "work"
    return slug[:64].rstrip("-") or "work"


def initial_state(kind: str, title: str, slug: str, lane: str, work_id: str, stage: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "id": work_id,
        "kind": kind,
        "title": title,
        "slug": slug,
        "lane": lane,
        "stage": stage,
        "status": "active",
        "created_at": timestamp,
        "updated_at": timestamp,
        "scope": {"paths": [], "symbols": [], "keywords": []},
        "links": {"model": [], "knowledge": [], "parent": None, "children": []},
        "gate": {"status": "clear", "reasons": [], "question": None},
        "validation": {"commands": [], "last_result": "not_run"},
    }


def work_template(kind: str, title: str, lane: str, work_id: str) -> str:
    kind_prompts = {
        "feature": "Describe the observable capability and compatibility boundary.",
        "issue": "Describe the intended behavior, observed symptom and reproduction signal.",
        "refactor": "Describe the behavior that must remain unchanged and the structural problem.",
        "roadmap": "Describe the outcome, systems involved and why one bounded feature is insufficient.",
        "model": "Describe which current truth or reusable knowledge must be changed.",
    }
    return f"""# {title}

- Work: `{work_id}`
- Kind: `{kind}`
- Lane: `{lane}`

## 1. Intent and acceptance

- Outcome: {kind_prompts[kind]}
- Acceptance:
- Non-goals:

## 2. Evidence

- Repository observations:
- Relevant current model / executable contracts:
- Baseline or reproduction:

## 3. Design or root cause

- Chosen mechanism / root cause:
- Existing path reused:
- Alternatives rejected and why:
- Compatibility / rollback / rollout (when relevant):

## 4. Plan

- [ ]

## 5. Changes and decisions

- Changed:
- Decisions made during execution:

## 6. Verification and review

- Commands and results:
- Observable acceptance evidence:
- Internal review findings and repairs:

## 7. Promotion and closure

- Model updates:
- Knowledge promoted:
- Remaining follow-ups:
- Closure summary:
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


def active_root(root: Path) -> Path:
    return runtime_dir(root) / "work" / "active"


def archived_root(root: Path) -> Path:
    return runtime_dir(root) / "work" / "archive"


def iter_active_dirs(root: Path) -> Iterator[Path]:
    base = active_root(root)
    if not base.exists():
        return
    for child in sorted(base.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            yield child


def load_state(work_dir: Path) -> dict[str, Any]:
    state = read_json(work_dir / "state.json")
    if not state.get("id"):
        raise RuntimeErrorWithHint(f"state missing id: {work_dir / 'state.json'}")
    return state


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
        choices = ", ".join(path.name for path in matches)
        raise RuntimeErrorWithHint(f"work selector is ambiguous: {selector}; matches: {choices}")
    return matches[0]


def unique_work_id(root: Path, slug: str) -> str:
    base = f"{datetime.now().astimezone().date().isoformat()}-{slug}"
    candidate = base
    counter = 2
    while (active_root(root) / candidate).exists() or any(
        (year / candidate).exists() for year in archived_root(root).glob("[0-9][0-9][0-9][0-9]") if year.is_dir()
    ):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def context_path(work_dir: Path) -> Path:
    return work_dir / "context.json"


def load_context(work_dir: Path) -> dict[str, Any]:
    path = context_path(work_dir)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "sessions": {}}
    data = read_json(path)
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("sessions", {})
    if not isinstance(data["sessions"], dict):
        data["sessions"] = {}
    return data


def get_session_receipts(context: dict[str, Any], session: str | None) -> dict[str, Any]:
    if not session:
        return {}
    session_data = context.get("sessions", {}).get(session, {})
    receipts = session_data.get("receipts", {}) if isinstance(session_data, dict) else {}
    return receipts if isinstance(receipts, dict) else {}


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
            "use explicit /cs observe or /cs evolve commands instead"
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


def stage_sections(stage: str) -> tuple[str, ...]:
    return tuple(STAGE_SECTIONS.get(stage, ("Intent and acceptance", "Evidence", "Changes and decisions")))


def build_candidates(root: Path, work_dir: Path, state: dict[str, Any], stage: str) -> list[Candidate]:
    candidates: list[Candidate] = [
        Candidate(work_dir / "work.md", "current_work", stage_sections(stage)),
    ]

    attention = runtime_dir(root) / "attention.md"
    if meaningful_attention(attention):
        candidates.append(Candidate(attention, "attention"))

    links = state.get("links", {}) if isinstance(state.get("links"), dict) else {}
    model_links = normalize_linked_paths(root, links.get("model", []))
    knowledge_links = normalize_linked_paths(root, links.get("knowledge", []))
    if model_links:
        candidates.extend(Candidate(path, "linked_model") for path in model_links)
    elif stage in {"intake", "evidence", "design", "discover", "frame", "inspect", "analyze", "characterize"}:
        candidates.append(Candidate(runtime_dir(root) / "model" / "INDEX.md", "model_pointer"))
    candidates.extend(Candidate(path, "linked_knowledge") for path in knowledge_links)

    scope = state.get("scope", {}) if isinstance(state.get("scope"), dict) else {}
    for path in normalize_linked_paths(root, scope.get("paths", [])):
        candidates.append(Candidate(path, "scoped_source"))

    deduplicated: list[Candidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.path)
        if key not in seen:
            seen.add(key)
            deduplicated.append(candidate)
    return deduplicated


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
    # Candidate sets are intentionally small, so verify the digest even when
    # size/mtime match. This avoids a false reuse after metadata-preserving edits.
    return isinstance(expected, str) and expected == sha256_file(path)


def candidate_payload(root: Path, candidate: Candidate, status: str, detail: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": rel(root, candidate.path) if candidate.path.exists() else str(candidate.path.relative_to(root)),
        "reason": candidate.reason,
    }
    if candidate.sections:
        payload["sections"] = list(candidate.sections)
    if detail:
        payload["detail"] = detail
    payload["status"] = status
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
    stage = args.stage or DEFAULT_STAGE[args.kind]
    state = initial_state(args.kind, args.title, slug, args.lane, work_id, stage)
    write_json(work_dir / "state.json", state)
    atomic_write(work_dir / "work.md", work_template(args.kind, args.title, args.lane, work_id))
    write_json(work_dir / "context.json", {"schema_version": SCHEMA_VERSION, "sessions": {}})
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
                "lane": state.get("lane"),
                "stage": state.get("stage"),
                "status": state.get("status"),
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
    return {
        "path": rel(root, work_dir),
        "state": load_state(work_dir),
        "context": load_context(work_dir) if args.with_context else None,
    }


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    stage = args.stage or str(state.get("stage") or DEFAULT_STAGE.get(str(state.get("kind")), "intake"))
    context = load_context(work_dir)
    receipts = get_session_receipts(context, args.session)

    result: dict[str, Any] = {
        "work": state.get("id"),
        "kind": state.get("kind"),
        "lane": state.get("lane"),
        "stage": stage,
        "session": args.session,
        "always": [{"path": rel(root, work_dir / "state.json"), "reason": "control_state", "status": "read"}],
        "read": [],
        "reuse": [],
        "missing": [],
        "notes": [],
        "archive_search": False,
    }
    if not args.session:
        result["notes"].append(
            "No --session key supplied: unchanged receipts are not reused. Use one stable key only within the current conversation."
        )

    for candidate in build_candidates(root, work_dir, state, stage):
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
            detail = "new_or_changed" if args.session else "cold_context"
            result["read"].append(candidate_payload(root, candidate, "read", detail))

    scope = state.get("scope", {}) if isinstance(state.get("scope"), dict) else {}
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
        entry = {
            **file_fingerprint(path),
            "read_at": now_iso(),
            "stage": args.stage,
            "reason": args.reason,
        }
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
        write_json(work_dir / "state.json", state)
    return {"work": work_dir.name, "changed": changed, "state": state}


def command_set(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    work_dir = resolve_work(root, args.work)
    state = load_state(work_dir)
    changes: dict[str, Any] = {}
    for field in ("stage", "status", "lane"):
        value = getattr(args, field)
        if value is not None and state.get(field) != value:
            state[field] = value
            changes[field] = value
    gate = state.setdefault("gate", {"status": "clear", "reasons": [], "question": None})
    if args.gate_status is not None and gate.get("status") != args.gate_status:
        gate["status"] = args.gate_status
        changes["gate.status"] = args.gate_status
    if args.gate_reason:
        gate["reasons"] = list(dict.fromkeys(args.gate_reason))
        changes["gate.reasons"] = gate["reasons"]
    if args.gate_question is not None:
        gate["question"] = args.gate_question or None
        changes["gate.question"] = gate["question"]
    validation = state.setdefault("validation", {"commands": [], "last_result": "not_run"})
    if args.validation_command:
        validation["commands"] = list(dict.fromkeys(args.validation_command))
        changes["validation.commands"] = validation["commands"]
    if args.validation_result is not None:
        normalized_validation = str(args.validation_result).strip().casefold()
        if normalized_validation not in VALIDATION_RESULTS:
            raise RuntimeErrorWithHint(
                f"validation result must be one of {', '.join(VALIDATION_RESULTS)}"
            )
        validation["last_result"] = normalized_validation
        changes["validation.last_result"] = normalized_validation
    if changes:
        state["updated_at"] = now_iso()
        write_json(work_dir / "state.json", state)
    return {"work": work_dir.name, "changes": changes, "state": state}


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
        if size > 1024 * 1024:
            continue
        if path.suffix.casefold() in TEXT_SUFFIXES:
            yield path


def search_bases(root: Path, scope: str, deep_archive: bool = False) -> list[Path]:
    cs = runtime_dir(root)
    archive_source = cs / "work" / "archive" if deep_archive else cs / "work" / "archive-index.jsonl"
    mapping = {
        "model": [cs / "model"],
        "knowledge": [cs / "knowledge"],
        "active": [cs / "work" / "active"],
        "archive": [archive_source],
        "current": [cs / "model", cs / "knowledge"],
        "all": [cs / "model", cs / "knowledge", cs / "work" / "active", archive_source],
    }
    return mapping[scope]


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
        count = folded.count(term)
        score += min(count, 8) * 2
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
    seen: set[str] = set()
    for base in search_bases(root, args.scope, deep_archive=deep_archive):
        for path in iter_text_files(base):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            score = score_text(path, text, args.query, terms)
            if score > 0:
                ranked.append((score, path, first_snippet(text, terms)))
    ranked.sort(key=lambda item: (-item[0], rel(root, item[1])))
    limit = max(1, min(args.limit, 50))
    results = [
        {"score": score, "path": rel(root, path), "snippet": snippet}
        for score, path, snippet in ranked[:limit]
    ]
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
    if status not in {"done", "cancelled"} and not args.force:
        raise RuntimeErrorWithHint(
            f"work status is {status!r}; set it to done/cancelled before archive, or use --force deliberately"
        )
    validation = state.get("validation", {}) if isinstance(state.get("validation"), dict) else {}
    validation_result = str(validation.get("last_result", "not_run")).strip().casefold()
    if status == "done" and validation_result != "passed" and not args.force:
        raise RuntimeErrorWithHint(
            "completed work cannot be archived unless validation.last_result is exactly 'passed'; "
            "record task-verifier evidence or use --force deliberately"
        )
    completed_at = now_iso()
    original_state_text = (work_dir / "state.json").read_text(encoding="utf-8")
    state["status"] = "archived"
    state["updated_at"] = completed_at
    state["completed_at"] = completed_at

    year = completed_at[:4]
    destination_parent = archived_root(root) / year
    destination_parent.mkdir(parents=True, exist_ok=True)
    destination = destination_parent / work_dir.name
    if destination.exists():
        raise RuntimeErrorWithHint(f"archive destination already exists: {destination}")

    write_json(work_dir / "state.json", state)
    try:
        shutil.move(str(work_dir), str(destination))
    except OSError:
        # Keep active work internally consistent if the filesystem move fails.
        if work_dir.exists():
            atomic_write(work_dir / "state.json", original_state_text)
        raise

    index_entry = {
        "id": state.get("id"),
        "kind": state.get("kind"),
        "title": state.get("title"),
        "slug": state.get("slug"),
        "lane": state.get("lane"),
        "completed_at": completed_at,
        "summary": args.summary or "",
        "scope": state.get("scope", {}),
        "path": rel(root, destination),
    }
    index_path = runtime_dir(root) / "work" / "archive-index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(index_entry, ensure_ascii=False) + "\n")
    return {"archived": index_entry}


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project_root(explicit=args.root)
    cs = runtime_dir(root)
    findings: list[dict[str, str]] = []
    required_dirs = [
        cs / "model", cs / "knowledge", cs / "work" / "active", cs / "work" / "archive", cs / "reference", cs / "tools"
    ]
    try:
        directory_config = read_json(cs / "config.json")
        observability_enabled = bool(directory_config.get("observability", {}).get("enabled", False))
        evolution_enabled = bool(directory_config.get("evolution", {}).get("enabled", False))
    except RuntimeErrorWithHint:
        observability_enabled = False
        evolution_enabled = False
    if observability_enabled:
        required_dirs.extend([
            cs / "observations" / "pending",
            cs / "observations" / "flagged",
            cs / "observations" / "selected",
        ])
    if evolution_enabled:
        required_dirs.extend([
            cs / "harness",
            cs / "evolution" / "cases",
            cs / "evals",
            cs / "meta" / "campaigns",
            cs / "meta" / "feedback" / "items",
        ])
    for directory in required_dirs:
        if not directory.is_dir():
            findings.append({"level": "error", "message": f"missing directory: {rel(root, directory)}"})
    try:
        config = read_json(cs / "config.json")
        if config.get("context", {}).get("archive_default") != "off":
            findings.append({"level": "warning", "message": "context.archive_default should normally be 'off'"})
        if config.get("entry", {}).get("mode") not in {"auto", "route"}:
            findings.append({"level": "error", "message": "entry.mode must be 'auto' or 'route'"})
        exclusions = set(config.get("context", {}).get("excluded_normal_roots") or [])
        missing_exclusions = set(MANDATORY_NORMAL_CONTEXT_EXCLUSIONS) - exclusions
        if missing_exclusions:
            findings.append({
                "level": "error",
                "message": f"normal context is missing protected exclusions: {sorted(missing_exclusions)}",
            })
        observability = config.get("observability", {})
        if observability.get("mode") != "passive":
            findings.append({"level": "error", "message": "observability.mode must be 'passive'"})
        if observability.get("best_effort") is not True:
            findings.append({"level": "error", "message": "passive observation writes must be best-effort"})
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
        if evolution.get("require_selected_cases") is not True:
            findings.append({"level": "error", "message": "Harness evolution must require explicitly selected cases"})
        if evolution.get("promotion_authority") != "owner_checkpoint_by_policy":
            findings.append({"level": "error", "message": "Harness promotion authority must be policy-scoped"})
        if evolution.get("require_validity_prepass") is not True:
            findings.append({"level": "error", "message": "Harness evaluation must require a validity pre-pass"})
        if evolution.get("require_fixture_covered_policy") is not True:
            findings.append({"level": "error", "message": "Harness evolution must require fixture-covered policy"})
        meta = config.get("meta", {})
        if meta.get("normal_runs_may_import_meta") is not False:
            findings.append({"level": "error", "message": "normal runs must not import the Meta control plane"})
        if (meta.get("trigger") or {}).get("mode") != "scan_only_by_default":
            findings.append({"level": "error", "message": "Meta trigger may only scan/open campaigns by default"})
        if int((meta.get("validity") or {}).get("minimum_stochastic_repeats", 0)) < 5:
            findings.append({"level": "error", "message": "stochastic Meta verdicts require k>=5"})
        if evolution.get("require_private_holdout") is not True:
            findings.append({"level": "error", "message": "Harness evaluation must require a private holdout"})
        evaluator = config.get("evaluator", {})
        if evaluator.get("mode") != "external_signed_aggregate":
            findings.append({"level": "error", "message": "evaluator.mode must be external_signed_aggregate"})
        if evaluator.get("require_signed_results") is not True:
            findings.append({"level": "error", "message": "trusted evaluator results must be signed"})
        if evaluator.get("signing_algorithm") != "hmac-sha256":
            findings.append({"level": "error", "message": "evaluator.signing_algorithm must be hmac-sha256"})
        if evaluator.get("private_holdout_location") != "outside_candidate_workspace":
            findings.append({"level": "error", "message": "private holdout must stay outside candidate workspace"})
    except RuntimeErrorWithHint as exc:
        findings.append({"level": "error", "message": str(exc)})

    attention = cs / "attention.md"
    if attention.exists():
        line_count = len(attention.read_text(encoding="utf-8", errors="replace").splitlines())
        try:
            max_lines = int(read_json(cs / "config.json").get("context", {}).get("max_attention_lines", 80))
        except (RuntimeErrorWithHint, TypeError, ValueError):
            max_lines = 80
        if line_count > max_lines:
            findings.append({"level": "warning", "message": f"attention.md has {line_count} lines (limit {max_lines})"})

    try:
        max_index_lines = int(read_json(cs / "config.json").get("context", {}).get("max_index_lines", 160))
    except (RuntimeErrorWithHint, TypeError, ValueError):
        max_index_lines = 160
    for index_path in (cs / "model" / "INDEX.md", cs / "knowledge" / "INDEX.md"):
        if index_path.exists():
            line_count = len(index_path.read_text(encoding="utf-8", errors="replace").splitlines())
            if line_count > max_index_lines:
                findings.append({
                    "level": "warning",
                    "message": f"{rel(root, index_path)} has {line_count} lines (limit {max_index_lines}); shard by domain/context",
                })

    ids: set[str] = set()
    for directory in iter_active_dirs(root):
        for required in ("state.json", "work.md", "context.json"):
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
            if state.get("lane") not in LANES:
                findings.append({"level": "error", "message": f"unknown lane in {work_id}: {state.get('lane')}"})
        except RuntimeErrorWithHint as exc:
            findings.append({"level": "error", "message": str(exc)})

    errors = sum(1 for item in findings if item["level"] == "error")
    warnings = sum(1 for item in findings if item["level"] == "warning")
    return {
        "root": str(root),
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", dest="global_root",
        help="project root (also accepted after the subcommand)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_root(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--root",
            help="project root; otherwise discover from current directory",
        )

    init_parser = subparsers.add_parser("init", help="create the minimal runtime without overwriting project data")
    add_root(init_parser)
    init_parser.set_defaults(func=command_init)

    new_parser = subparsers.add_parser("new", help="create an active work aggregate")
    add_root(new_parser)
    new_parser.add_argument("kind", choices=WORK_KINDS)
    new_parser.add_argument("title")
    new_parser.add_argument("--slug")
    new_parser.add_argument("--lane", choices=LANES, default="standard")
    new_parser.add_argument("--stage")
    new_parser.set_defaults(func=command_new)

    list_parser = subparsers.add_parser("list", help="list active work using state metadata only")
    add_root(list_parser)
    list_parser.set_defaults(func=command_list)

    show_parser = subparsers.add_parser("show", help="show one active work state")
    add_root(show_parser)
    show_parser.add_argument("--work", required=True)
    show_parser.add_argument("--with-context", action="store_true")
    show_parser.set_defaults(func=command_show)

    plan_parser = subparsers.add_parser("plan", help="plan stage-specific reads; never scans archive")
    add_root(plan_parser)
    plan_parser.add_argument("--work", required=True)
    plan_parser.add_argument("--stage")
    plan_parser.add_argument("--session", help="stable key for this live conversation; omit for a cold read plan")
    plan_parser.set_defaults(func=command_plan)

    receipt_parser = subparsers.add_parser("receipt", help="record file versions read in the current conversation")
    add_root(receipt_parser)
    receipt_parser.add_argument("--work", required=True)
    receipt_parser.add_argument("--session", required=True)
    receipt_parser.add_argument("--stage", required=True)
    receipt_parser.add_argument("--reason", required=True)
    receipt_parser.add_argument("paths", nargs="+")
    receipt_parser.set_defaults(func=command_receipt)

    link_parser = subparsers.add_parser("link", help="add explicit task links and scope hints")
    add_root(link_parser)
    link_parser.add_argument("--work", required=True)
    link_parser.add_argument("--model", action="append", default=[])
    link_parser.add_argument("--knowledge", action="append", default=[])
    link_parser.add_argument("--path", action="append", default=[])
    link_parser.add_argument("--symbol", action="append", default=[])
    link_parser.add_argument("--keyword", action="append", default=[])
    link_parser.add_argument("--parent")
    link_parser.add_argument("--child", action="append", default=[])
    link_parser.set_defaults(func=command_link)

    set_parser = subparsers.add_parser("set", help="update deterministic work state")
    add_root(set_parser)
    set_parser.add_argument("--work", required=True)
    set_parser.add_argument("--stage")
    set_parser.add_argument("--status", choices=("active", "blocked", "done", "cancelled"))
    set_parser.add_argument("--lane", choices=LANES)
    set_parser.add_argument("--gate-status", choices=("clear", "required", "approved", "rejected"))
    set_parser.add_argument("--gate-reason", action="append", default=[])
    set_parser.add_argument("--gate-question")
    set_parser.add_argument("--validation-command", action="append", default=[])
    set_parser.add_argument("--validation-result", choices=VALIDATION_RESULTS)
    set_parser.set_defaults(func=command_set)

    search_parser = subparsers.add_parser("search", help="search current model/knowledge; archive requires explicit scope and reason")
    add_root(search_parser)
    search_parser.add_argument("query")
    search_parser.add_argument("--scope", choices=("current", "model", "knowledge", "active", "archive", "all"), default="current")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--reason")
    search_parser.add_argument(
        "--deep", action="store_true",
        help="scan archived work content; without it archive scope searches metadata index only",
    )
    search_parser.set_defaults(func=command_search)

    archive_parser = subparsers.add_parser("archive", help="move completed work out of default retrieval")
    add_root(archive_parser)
    archive_parser.add_argument("--work", required=True)
    archive_parser.add_argument("--summary")
    archive_parser.add_argument("--force", action="store_true")
    archive_parser.set_defaults(func=command_archive)

    doctor_parser = subparsers.add_parser("doctor", help="validate runtime structure and active state")
    add_root(doctor_parser)
    doctor_parser.set_defaults(func=command_doctor)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
