#!/usr/bin/env python3
"""CodeStable Meta loop: observe signals, validate proposals, evaluate, accept, rollback.

This is an explicit/offline control plane. Normal `/cs` work never imports or
calls it. Creative changes are agent-authored files; this tool only validates,
locks, measures, records, and enforces budgets/authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cs_eval  # type: ignore
import cs_evolve  # type: ignore
import cs_feedback  # type: ignore
import cs_policy  # type: ignore

SCHEMA_VERSION = 1
CAMPAIGN_STATUSES = {
    "diagnose",
    "proposal",
    "validity_blocked",
    "validity_passed",
    "evaluation",
    "quality_gates",
    "accepted_pending_agent",
    "accepted_pending_owner",
    "promoted",
    "rejected",
    "closed",
}
QUALITY_GATE_STATUSES = {"passed", "failed", "blocked", "not_run"}
MEASUREMENT_LABELS = {"measured", "soft", "underpowered"}

DEFAULT_META: dict[str, Any] = {
    "enabled": True,
    "normal_runs_may_import_meta": False,
    "trigger": {
        "enabled": True,
        "mode": "scan_only_by_default",
        "minimum_matching_signals": 3,
        "max_campaigns_per_scan": 2,
        "max_feedback_per_campaign": 20,
    },
    "budgets": {
        "max_open_campaigns": 5,
        "max_variants_per_campaign": 3,
        "max_evaluation_trials": 300,
    },
    "validity": {
        "minimum_stochastic_repeats": 5,
        "require_context_complete": True,
        "require_calibrated_scorer": True,
        "require_committed_hypothesis": True,
        "require_judge_isolation": True,
    },
    "acceptance": {
        "required_quality_gates": ["policy_audit", "validity_prepass", "regression", "package"],
        "required_gate_label": "measured",
    },
}


class MetaError(RuntimeError):
    """A Meta-loop state, validity, budget, or authority invariant failed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return cs_policy.sha256_file(path)


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
        raise MetaError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MetaError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MetaError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, json_dump(value))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_id(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    if not result:
        raise MetaError("identifier cannot be empty")
    return result[:128]


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    try:
        return cs_policy.find_project_root(start=start, explicit=explicit)
    except cs_policy.PolicyError as exc:
        raise MetaError(str(exc)) from exc


def cs_dir(root: Path) -> Path:
    return root / ".codestable"


def meta_dir(root: Path) -> Path:
    return cs_dir(root) / "meta"


def campaign_dir(root: Path, campaign_id: str, *, require: bool = True) -> Path:
    path = meta_dir(root) / "campaigns" / normalize_id(campaign_id)
    if require and not path.is_dir():
        raise MetaError(f"unknown Meta campaign: {campaign_id}")
    return path


def campaign_path(root: Path, campaign_id: str) -> Path:
    return campaign_dir(root, campaign_id) / "campaign.json"


def load_campaign(root: Path, campaign_id: str) -> dict[str, Any]:
    return read_json(campaign_path(root, campaign_id))


def save_campaign(root: Path, campaign: dict[str, Any]) -> None:
    campaign["updated_at"] = now_iso()
    write_json(campaign_path(root, str(campaign["campaign_id"])), campaign)


def append_index(root: Path, action: str, campaign_id: str, **extra: Any) -> None:
    append_jsonl(
        meta_dir(root) / "index.jsonl",
        {"schema_version": SCHEMA_VERSION, "timestamp": now_iso(), "action": action, "campaign_id": campaign_id, **extra},
    )


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


def load_meta_config(root: Path) -> dict[str, Any]:
    config_path = cs_dir(root) / "config.json"
    if not config_path.is_file():
        return json.loads(json.dumps(DEFAULT_META))
    config = read_json(config_path)
    section = config.get("meta") if isinstance(config.get("meta"), dict) else {}
    return deep_merge(DEFAULT_META, section)


def init_runtime(root: Path) -> dict[str, Any]:
    directories = [
        meta_dir(root) / "campaigns",
        meta_dir(root) / "hypotheses",
        meta_dir(root) / "variants",
        meta_dir(root) / "results",
        meta_dir(root) / "feedback" / "items",
    ]
    created: list[str] = []
    preserved: list[str] = []
    for directory in directories:
        if directory.is_dir():
            preserved.append(directory.relative_to(root).as_posix())
        else:
            directory.mkdir(parents=True, exist_ok=True)
            created.append(directory.relative_to(root).as_posix())
    for path, default in (
        (meta_dir(root) / "index.jsonl", ""),
        (meta_dir(root) / "strategy-evidence.jsonl", ""),
        (
            meta_dir(root) / "trigger-state.json",
            json_dump({"schema_version": 1, "last_scan_at": None, "day": None, "campaigns_opened_today": 0, "consumed_feedback_ids": []}),
        ),
    ):
        if path.exists():
            preserved.append(path.relative_to(root).as_posix())
        else:
            atomic_write(path, default)
            created.append(path.relative_to(root).as_posix())
    cs_feedback.init_runtime(root)
    audit = cs_policy.audit_policies(root)
    return {"created": created, "preserved": preserved, "policy_audit": audit}


def open_campaigns(root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    base = meta_dir(root) / "campaigns"
    if not base.is_dir():
        return []
    for path in sorted(base.glob("*/campaign.json")):
        try:
            item = read_json(path)
        except MetaError:
            continue
        if item.get("status") not in {"promoted", "rejected", "closed"}:
            results.append(item)
    return results


def create_campaign(
    root: Path,
    *,
    title: str,
    feedback_ids: Sequence[str],
    signal: str,
    policy_ids: Sequence[str],
    runtime_profiles: Sequence[str],
    budget_id: str,
    source: str,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    init_runtime(root)
    config = load_meta_config(root)
    if config.get("enabled") is not True:
        raise MetaError("Meta loop is disabled")
    max_open = int(config.get("budgets", {}).get("max_open_campaigns", 5))
    if len(open_campaigns(root)) >= max_open:
        raise MetaError(f"Meta open-campaign budget exceeded: {max_open}")
    selected_feedback = list(dict.fromkeys(str(value) for value in feedback_ids if str(value).strip()))
    if not selected_feedback:
        raise MetaError("campaign requires classified feedback")
    items = [cs_feedback.load_feedback(root, feedback_id) for feedback_id in selected_feedback]
    if any(item.get("classification") != "harness_policy" for item in items):
        raise MetaError("only Harness-policy feedback can open a Harness Meta campaign")
    if any(item.get("campaign_ids") for item in items):
        raise MetaError("campaign feedback must be unassigned")
    normalized_signal = str(signal).strip().casefold()
    if any(item.get("signal") != normalized_signal for item in items):
        raise MetaError("campaign feedback must share one signal")
    declared_policies = list(dict.fromkeys(str(value) for value in policy_ids if str(value).strip()))
    if not declared_policies:
        raise MetaError("campaign must declare affected policies")
    for item in items:
        if not set(declared_policies).intersection(str(value) for value in item.get("policy_ids") or []):
            raise MetaError(f"feedback {item['feedback_id']} does not support the declared policies")
    policies = cs_policy.policy_map(root)
    unknown = [policy_id for policy_id in declared_policies if policy_id not in policies]
    if unknown:
        raise MetaError(f"unknown campaign policies: {unknown}")
    profiles = list(dict.fromkeys(str(value).strip() for value in runtime_profiles if str(value).strip()))
    if not profiles:
        raise MetaError("campaign must bind at least one runtime profile")
    if not title.strip() or not budget_id.strip():
        raise MetaError("campaign title and budget id are required")

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    identifier = normalize_id(campaign_id or f"meta-{timestamp}-{normalized_signal}")
    directory = campaign_dir(root, identifier, require=False)
    if directory.exists():
        raise MetaError(f"Meta campaign already exists: {identifier}")
    for child in ("hypothesis", "proposals", "quality-gates", "results"):
        (directory / child).mkdir(parents=True, exist_ok=True)

    # Reuse the deterministic evolution case for baseline identity and selected evidence.
    run_ids = [str(item["run_id"]) for item in items]
    case_id = f"case-{identifier}"
    try:
        evolution = cs_evolve.create_case(root, title=title, run_ids=run_ids, case_id=case_id)
    except cs_evolve.EvolutionError as exc:
        raise MetaError(str(exc)) from exc
    campaign = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": identifier,
        "title": title.strip(),
        "source": source,
        "status": "diagnose",
        "signal": normalized_signal,
        "feedback_ids": selected_feedback,
        "run_ids": run_ids,
        "policy_ids": declared_policies,
        "runtime_profiles": profiles,
        "budget": {"id": budget_id.strip(), "max_variants": int(config.get("budgets", {}).get("max_variants_per_campaign", 3)), "max_trials": int(config.get("budgets", {}).get("max_evaluation_trials", 300))},
        "case_id": case_id,
        "baseline_version": evolution["case"]["baseline_version"],
        "baseline_content_sha256": evolution["case"]["baseline_content_sha256"],
        "hypothesis": None,
        "candidate_ids": [],
        "quality_gates": {},
        "validity": {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    write_json(directory / "campaign.json", campaign)
    cs_feedback.assign_campaign(root, selected_feedback, identifier)
    append_index(root, "campaign_created", identifier, source=source, signal=normalized_signal, feedback_ids=selected_feedback, case_id=case_id)
    return campaign


def trigger_state(root: Path) -> dict[str, Any]:
    path = meta_dir(root) / "trigger-state.json"
    state = read_json(path)
    today = date.today().isoformat()
    if state.get("day") != today:
        state["day"] = today
        state["campaigns_opened_today"] = 0
    return state


def save_trigger_state(root: Path, state: dict[str, Any]) -> None:
    write_json(meta_dir(root) / "trigger-state.json", state)


def trigger_scan(root: Path, *, apply: bool) -> dict[str, Any]:
    init_runtime(root)
    config = load_meta_config(root)
    trigger = config.get("trigger", {})
    if trigger.get("enabled") is not True:
        return {"enabled": False, "apply": apply, "eligible": [], "created": []}
    minimum = int(trigger.get("minimum_matching_signals", 3))
    max_campaigns = int(trigger.get("max_campaigns_per_scan", 2))
    max_feedback = int(trigger.get("max_feedback_per_campaign", 20))
    queue = cs_feedback.queue_summary(root)["groups"]
    eligible = [group for group in queue if int(group.get("count", 0)) >= minimum]
    eligible = eligible[:max_campaigns]
    created: list[dict[str, Any]] = []
    state = trigger_state(root)
    if apply:
        remaining = max(0, max_campaigns - int(state.get("campaigns_opened_today", 0)))
        for group in eligible[:remaining]:
            profile = group.get("runtime_profile") or {}
            profile_id = f"{profile.get('adapter')}/{profile.get('model_profile')}"
            campaign = create_campaign(
                root,
                title=f"Repeated production signal: {group['signal']}",
                feedback_ids=list(group["feedback_ids"][:max_feedback]),
                signal=str(group["signal"]),
                policy_ids=list(group.get("policy_ids") or []),
                runtime_profiles=[profile_id],
                budget_id="signal-trigger-default",
                source="signal_trigger",
            )
            created.append(campaign)
            state["campaigns_opened_today"] = int(state.get("campaigns_opened_today", 0)) + 1
            state.setdefault("consumed_feedback_ids", []).extend(campaign["feedback_ids"])
    state["last_scan_at"] = now_iso()
    save_trigger_state(root, state)
    return {
        "enabled": True,
        "apply": apply,
        "minimum_matching_signals": minimum,
        "eligible": eligible,
        "created": created,
        "guard": "scan only opens a campaign; it never proposes, evaluates, or promotes",
        "state": state,
    }


def git_output(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise MetaError(completed.stderr.decode("utf-8", errors="replace").strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def freeze_hypothesis(
    root: Path,
    *,
    campaign_id: str,
    hypothesis_file: Path,
    actor: str,
    commit: str | None = None,
) -> dict[str, Any]:
    campaign = load_campaign(root, campaign_id)
    if campaign.get("hypothesis"):
        raise MetaError("campaign hypothesis is already frozen")
    if not actor.strip():
        raise MetaError("hypothesis freeze requires an actor")
    source = hypothesis_file.expanduser().resolve()
    try:
        relative = source.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise MetaError("hypothesis file must be inside the project repository") from exc
    if not source.is_file():
        raise MetaError(f"hypothesis file not found: {source}")
    revision = (commit or git_output(root, "rev-parse", "HEAD").decode().strip()).strip()
    resolved = git_output(root, "rev-parse", f"{revision}^{{commit}}").decode().strip()
    committed_bytes = git_output(root, "show", f"{resolved}:{relative}")
    live_bytes = source.read_bytes()
    if committed_bytes != live_bytes:
        raise MetaError("hypothesis must be committed unchanged before it is frozen")
    destination = campaign_dir(root, campaign_id) / "hypothesis" / "hypothesis.md"
    atomic_write(destination, live_bytes.decode("utf-8"))
    record = {
        "schema_version": SCHEMA_VERSION,
        "source_path": relative,
        "frozen_path": destination.relative_to(root).as_posix(),
        "sha256": sha256_bytes(live_bytes),
        "provenance_commit": resolved,
        "frozen_by": actor.strip(),
        "frozen_at": now_iso(),
    }
    write_json(campaign_dir(root, campaign_id) / "hypothesis" / "hypothesis.json", record)
    campaign["hypothesis"] = record
    campaign["status"] = "proposal"
    save_campaign(root, campaign)
    append_index(root, "hypothesis_frozen", campaign["campaign_id"], sha256=record["sha256"], commit=resolved)
    return record


def validate_agent_proposal(
    root: Path,
    *,
    campaign: dict[str, Any],
    proposal: dict[str, Any],
    proposal_file: Path,
) -> dict[str, Any]:
    required = (
        "schema_version",
        "campaign_id",
        "case_id",
        "candidate_id",
        "authorship",
        "title",
        "target_metric",
        "policy_ids",
        "change_type",
        "fixture_ids",
        "expected_effect",
        "regression_risks",
        "hypothesis",
        "variant_document",
    )
    missing = [field for field in required if field not in proposal]
    if missing:
        raise MetaError(f"proposal is missing fields: {missing}")
    checks = {
        "campaign_id": (proposal.get("campaign_id"), campaign.get("campaign_id")),
        "case_id": (proposal.get("case_id"), campaign.get("case_id")),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise MetaError(f"proposal {label} does not match campaign")
    authorship = proposal.get("authorship")
    if not isinstance(authorship, dict) or authorship.get("kind") != "agent":
        raise MetaError("proposal authorship.kind must be 'agent'; scripts may not invent policy changes")
    if not str(authorship.get("agent_id") or "").strip():
        raise MetaError("proposal must identify the authoring agent")
    target_metric = proposal.get("target_metric")
    if not isinstance(target_metric, dict) or not str(target_metric.get("id") or "").strip():
        raise MetaError("proposal target_metric.id is required")
    if str(target_metric.get("label") or "") not in MEASUREMENT_LABELS:
        raise MetaError("proposal target_metric.label must be measured, soft, or underpowered")
    if not str(proposal.get("title") or "").strip() or not str(proposal.get("expected_effect") or "").strip():
        raise MetaError("proposal title and expected effect are required")
    if not isinstance(proposal.get("regression_risks"), list):
        raise MetaError("proposal regression_risks must be an array")
    hypothesis = proposal.get("hypothesis")
    frozen = campaign.get("hypothesis")
    if not isinstance(hypothesis, dict) or not isinstance(frozen, dict):
        raise MetaError("proposal requires a frozen campaign hypothesis")
    for field in ("sha256", "provenance_commit"):
        if hypothesis.get(field) != frozen.get(field):
            raise MetaError(f"proposal hypothesis {field} does not match the frozen hypothesis")

    requirements = cs_policy.proposal_requirements(
        root,
        policy_ids=[str(value) for value in proposal.get("policy_ids") or []],
        change_type=str(proposal.get("change_type") or ""),
        fixture_ids=[str(value) for value in proposal.get("fixture_ids") or []],
    )
    if not set(requirements["policy_ids"]).issubset(set(campaign.get("policy_ids") or [])):
        raise MetaError("proposal policy ids exceed the campaign scope")
    variant_value = str(proposal.get("variant_document") or "")
    variant_path = Path(variant_value)
    if not variant_path.is_absolute():
        variant_path = (proposal_file.parent / variant_path).resolve()
    if not variant_path.is_file():
        raise MetaError(f"agent-authored variant document is missing: {variant_path}")
    return {
        **requirements,
        "candidate_id": normalize_id(str(proposal["candidate_id"])),
        "proposal_sha256": sha256_file(proposal_file),
        "variant_sha256": sha256_file(variant_path),
        "variant_path": variant_path,
        "target_metric": target_metric,
        "authorship": authorship,
    }


def register_proposal(
    root: Path,
    *,
    campaign_id: str,
    proposal_file: Path,
    overlay: Path,
) -> dict[str, Any]:
    campaign = load_campaign(root, campaign_id)
    if campaign.get("status") not in {"proposal", "validity_blocked"}:
        raise MetaError(f"campaign is not accepting proposals: {campaign.get('status')}")
    max_variants = int(campaign.get("budget", {}).get("max_variants", 3))
    if len(campaign.get("candidate_ids") or []) >= max_variants:
        raise MetaError(f"campaign variant budget exceeded: {max_variants}")
    source = proposal_file.expanduser().resolve()
    proposal = read_json(source)
    try:
        validated = validate_agent_proposal(root, campaign=campaign, proposal=proposal, proposal_file=source)
    except cs_policy.PolicyError as exc:
        raise MetaError(str(exc)) from exc
    metadata = {
        "campaign_id": campaign["campaign_id"],
        "policy_ids": validated["policy_ids"],
        "fixture_ids": validated["fixture_ids"],
        "change_type": validated["change_type"],
        "target_metric": validated["target_metric"],
        "authorship": validated["authorship"],
        "proposal_sha256": validated["proposal_sha256"],
        "variant_sha256": validated["variant_sha256"],
        "owner_checkpoint_required": validated["owner_checkpoint_required"],
        "promotion_authority": validated["promotion_authority"],
        "policy_registry_sha256": validated["policy_registry_sha256"],
        "fixture_index_sha256": validated["fixture_index_sha256"],
        "runtime_profiles": list(campaign.get("runtime_profiles") or []),
        "evidence_scope": {"project": "current", "runtime_profiles": list(campaign.get("runtime_profiles") or [])},
        "hypothesis": campaign["hypothesis"],
    }
    try:
        manifest = cs_evolve.add_candidate(
            root,
            str(campaign["case_id"]),
            candidate_id=validated["candidate_id"],
            title=str(proposal["title"]),
            surface_ids=validated["surface_ids"],
            overlay=overlay.expanduser().resolve(),
            expected_effect=str(proposal["expected_effect"]),
            regression_risks=[str(value) for value in proposal.get("regression_risks") or []],
            proposal_metadata=metadata,
            proposal_file=source,
            variant_file=validated["variant_path"],
        )
    except (cs_evolve.EvolutionError, cs_policy.PolicyError) as exc:
        raise MetaError(str(exc)) from exc
    campaign.setdefault("candidate_ids", []).append(validated["candidate_id"])
    campaign["status"] = "proposal"
    save_campaign(root, campaign)
    append_index(root, "proposal_registered", campaign["campaign_id"], candidate_id=validated["candidate_id"], authority=validated["promotion_authority"])
    return {"campaign": campaign, "candidate": manifest, "requirements": validated}


def fixture_validity_checks(
    root: Path,
    *,
    fixture_ids: Sequence[str],
    repeats: int,
    tested_profiles: Sequence[str],
    judge_profile: str | None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    config = load_meta_config(root).get("validity", {})
    minimum_stochastic = int(config.get("minimum_stochastic_repeats", 5))
    fixtures = cs_policy.fixture_map(root)
    checks: list[dict[str, Any]] = []
    labels: dict[str, str] = {}
    for fixture_id in fixture_ids:
        entry = fixtures.get(fixture_id)
        if entry is None:
            checks.append({"fixture_id": fixture_id, "check": "exists", "status": "blocked", "detail": "unknown fixture"})
            continue
        path = root / str(entry["path"])
        try:
            fixture = read_json(path)
        except MetaError as exc:
            checks.append({"fixture_id": fixture_id, "check": "parse", "status": "blocked", "detail": str(exc)})
            continue
        context = fixture.get("context") if isinstance(fixture.get("context"), dict) else {}
        required_refs = context.get("required_refs") if isinstance(context.get("required_refs"), list) else []
        subject_refs = context.get("subject_matter_refs") if isinstance(context.get("subject_matter_refs"), list) else []
        missing_refs: list[str] = []
        for value in [*required_refs, *subject_refs]:
            try:
                relative = cs_policy.normalize_relative(str(value))
            except cs_policy.PolicyError:
                missing_refs.append(str(value))
                continue
            if not (root / relative).exists():
                missing_refs.append(relative)
        context_ok = context.get("complete") is True and not missing_refs
        checks.append({"fixture_id": fixture_id, "check": "context_complete", "status": "passed" if context_ok else "blocked", "detail": {"missing_refs": missing_refs}})

        oracle = fixture.get("oracle") if isinstance(fixture.get("oracle"), dict) else {}
        deterministic = oracle.get("deterministic") is True
        oracle_type = str(oracle.get("type") or "")
        tolerance = str(oracle.get("tolerance") or "")
        brittle = (not deterministic and oracle_type in {"exact_text", "keyword_exact"}) or not tolerance
        checks.append({"fixture_id": fixture_id, "check": "oracle_tolerance", "status": "blocked" if brittle else "passed", "detail": {"type": oracle_type, "tolerance": tolerance}})

        scorer = fixture.get("scorer") if isinstance(fixture.get("scorer"), dict) else {}
        calibrated = scorer.get("calibrated") is True and bool(str(scorer.get("calibration_evidence") or ""))
        checks.append({"fixture_id": fixture_id, "check": "scorer_calibrated", "status": "passed" if calibrated else "blocked"})

        required_repeats = max(int((fixture.get("execution") or {}).get("minimum_repeats", 1)), 1 if deterministic else minimum_stochastic)
        powered = repeats >= required_repeats
        label = "measured" if powered else "underpowered"
        labels[f"fixture:{fixture_id}:pass_rate"] = label
        checks.append({"fixture_id": fixture_id, "check": "variance_budget", "status": "passed" if powered else "underpowered", "detail": {"configured_repeats": repeats, "required_repeats": required_repeats}})

        uses_judge = oracle_type == "judge" or str(scorer.get("type") or "") == "judge"
        if uses_judge:
            isolated = bool(judge_profile) and judge_profile not in set(tested_profiles)
            checks.append({"fixture_id": fixture_id, "check": "judge_isolation", "status": "passed" if isolated else "blocked", "detail": {"judge_profile": judge_profile, "tested_profiles": list(tested_profiles)}})
            labels[f"fixture:{fixture_id}:judge"] = "soft" if isolated else "underpowered"
    return checks, labels


def validity_prepass(
    root: Path,
    *,
    campaign_id: str,
    candidate_id: str,
    repeats: int,
    judge_profile: str | None,
    actor: str,
) -> dict[str, Any]:
    if repeats < 1:
        raise MetaError("pre-pass repeats must be positive")
    if not actor.strip():
        raise MetaError("validity pre-pass requires an actor")
    campaign = load_campaign(root, campaign_id)
    if candidate_id not in set(campaign.get("candidate_ids") or []):
        raise MetaError("candidate is not registered in the campaign")
    hypothesis = campaign.get("hypothesis")
    if not isinstance(hypothesis, dict):
        raise MetaError("campaign has no frozen hypothesis")
    # Revalidate committed provenance, not just the stored hash.
    committed = git_output(root, "show", f"{hypothesis['provenance_commit']}:{hypothesis['source_path']}")
    hypothesis_ok = sha256_bytes(committed) == hypothesis.get("sha256")

    case_id = str(campaign["case_id"])
    candidate_root = cs_dir(root) / "evolution" / "cases" / case_id / "candidates" / normalize_id(candidate_id)
    manifest = read_json(candidate_root / "manifest.json")
    metadata = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    fixture_ids = [str(value) for value in metadata.get("fixture_ids") or []]
    policy_audit = cs_policy.audit_policies(root)
    fixture_checks, labels = fixture_validity_checks(
        root,
        fixture_ids=fixture_ids,
        repeats=repeats,
        tested_profiles=[str(value) for value in campaign.get("runtime_profiles") or []],
        judge_profile=judge_profile,
    )
    checks: list[dict[str, Any]] = [
        {"check": "policy_fixture_audit", "status": "passed" if policy_audit["ok"] else "blocked", "detail": policy_audit["issues"]},
        {"check": "hypothesis_committed_before_measurement", "status": "passed" if hypothesis_ok else "blocked", "detail": {"commit": hypothesis.get("provenance_commit"), "sha256": hypothesis.get("sha256")}},
        *fixture_checks,
    ]
    blocked = any(item.get("status") == "blocked" for item in checks)
    underpowered = any(item.get("status") == "underpowered" for item in checks)
    status = "blocked" if blocked else "underpowered" if underpowered else "pass"
    result = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "case_id": case_id,
        "candidate_id": normalize_id(candidate_id),
        "status": status,
        "can_attribute_negative_verdict": status == "pass",
        "can_support_promotion": status == "pass",
        "fixture_ids": fixture_ids,
        "fixture_set_sha256": cs_policy.fixture_set_sha256(root, fixture_ids),
        "policy_registry_sha256": policy_audit["policy_registry_sha256"],
        "fixture_index_sha256": policy_audit["fixture_index_sha256"],
        "hypothesis_sha256": hypothesis["sha256"],
        "hypothesis_commit": hypothesis["provenance_commit"],
        "tested_profiles": campaign.get("runtime_profiles") or [],
        "judge_profile": judge_profile,
        "repeats": repeats,
        "measurement_labels": labels,
        "checks": checks,
        "performed_by": actor.strip(),
        "performed_at": now_iso(),
    }
    result["prepass_sha256"] = sha256_bytes(canonical_json({k: v for k, v in result.items() if k != "prepass_sha256"}))
    path = campaign_dir(root, campaign_id) / "results" / f"validity-{normalize_id(candidate_id)}.json"
    write_json(path, result)
    metadata["validity"] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "status": status,
        "fixture_set_sha256": result["fixture_set_sha256"],
        "measurement_labels": labels,
    }
    manifest["meta"] = metadata
    write_json(candidate_root / "manifest.json", manifest)
    campaign.setdefault("validity", {})[normalize_id(candidate_id)] = metadata["validity"]
    campaign["status"] = "validity_passed" if status == "pass" else "validity_blocked"
    save_campaign(root, campaign)
    record_quality_gate(
        root,
        campaign_id=campaign_id,
        name="policy_audit",
        status="passed" if policy_audit["ok"] else "failed",
        label="measured",
        actor=actor,
        command="cs_policy.py audit",
        evidence_path=cs_policy.registry_path(root),
    )
    record_quality_gate(
        root,
        campaign_id=campaign_id,
        name="validity_prepass",
        status="passed" if status == "pass" else "failed",
        label="measured" if status == "pass" else "underpowered" if status == "underpowered" else "measured",
        actor=actor,
        command="cs_meta.py validity-prepass",
        evidence_path=path,
    )
    append_index(root, "validity_prepass", campaign["campaign_id"], candidate_id=candidate_id, status=status, prepass_sha256=result["prepass_sha256"])
    return result


def record_quality_gate(
    root: Path,
    *,
    campaign_id: str,
    name: str,
    status: str,
    label: str,
    actor: str,
    command: str | None = None,
    evidence_path: Path | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    normalized_status = status.strip().casefold()
    if normalized_status not in QUALITY_GATE_STATUSES:
        raise MetaError(f"invalid quality gate status: {status}")
    normalized_label = label.strip().casefold()
    if normalized_label not in MEASUREMENT_LABELS:
        raise MetaError(f"invalid measurement label: {label}")
    if not actor.strip():
        raise MetaError("quality gate record requires an actor")
    campaign = load_campaign(root, campaign_id)
    evidence: dict[str, Any] | None = None
    if evidence_path is not None:
        path = evidence_path.expanduser().resolve()
        if not path.is_file():
            raise MetaError(f"quality gate evidence file not found: {path}")
        try:
            relative = path.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise MetaError("quality gate evidence must be inside the project") from exc
        evidence = {"path": relative, "sha256": sha256_file(path)}
    record = {
        "schema_version": SCHEMA_VERSION,
        "name": normalize_id(name),
        "status": normalized_status,
        "label": normalized_label,
        "command": command,
        "evidence": evidence,
        "note": (note or "")[:2048],
        "recorded_by": actor.strip(),
        "recorded_at": now_iso(),
    }
    path = campaign_dir(root, campaign_id) / "quality-gates" / f"{record['name']}.json"
    write_json(path, record)
    campaign.setdefault("quality_gates", {})[record["name"]] = {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path), "status": normalized_status, "label": normalized_label}
    save_campaign(root, campaign)
    append_index(root, "quality_gate_recorded", campaign["campaign_id"], name=record["name"], status=normalized_status, label=normalized_label)
    return record


def acceptance_check(root: Path, *, campaign_id: str, candidate_id: str) -> dict[str, Any]:
    campaign = load_campaign(root, campaign_id)
    case_id = str(campaign["case_id"])
    candidate_root = cs_dir(root) / "evolution" / "cases" / case_id / "candidates" / normalize_id(candidate_id)
    manifest = read_json(candidate_root / "manifest.json")
    decision = read_json(candidate_root / "decision.json")
    metadata = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    validity = metadata.get("validity") if isinstance(metadata.get("validity"), dict) else {}
    reasons: list[str] = []
    if decision.get("accepted") is not True:
        reasons.append("trusted evaluation decision did not accept the candidate")
    if validity.get("status") != "pass":
        reasons.append("validity pre-pass is not a measured pass")
    config = load_meta_config(root).get("acceptance", {})
    required = [str(value) for value in config.get("required_quality_gates") or []]
    required_label = str(config.get("required_gate_label") or "measured")
    gate_summary: dict[str, Any] = {}
    for name in required:
        reference = (campaign.get("quality_gates") or {}).get(name)
        if not isinstance(reference, dict):
            reasons.append(f"required quality gate is missing: {name}")
            continue
        path = root / str(reference.get("path") or "")
        record = read_json(path)
        if sha256_file(path) != reference.get("sha256"):
            reasons.append(f"quality gate evidence changed: {name}")
        if record.get("status") != "passed":
            reasons.append(f"quality gate did not pass: {name}")
        if record.get("label") != required_label:
            reasons.append(f"quality gate is not {required_label}: {name}")
        gate_summary[name] = {"status": record.get("status"), "label": record.get("label"), "sha256": reference.get("sha256")}
    owner_required = bool(metadata.get("owner_checkpoint_required"))
    authority = "owner" if owner_required else "agent"
    ready = not reasons
    result = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "case_id": case_id,
        "candidate_id": normalize_id(candidate_id),
        "ready": ready,
        "status": "pending_owner_checkpoint" if ready and owner_required else "ready_for_agent_promotion" if ready else "blocked",
        "owner_checkpoint_required": owner_required,
        "promotion_authority": authority,
        "reasons": reasons,
        "quality_gates": gate_summary,
        "decision_sha256": sha256_file(candidate_root / "decision.json"),
        "validity_sha256": validity.get("sha256"),
        "checked_at": now_iso(),
    }
    path = campaign_dir(root, campaign_id) / "results" / f"acceptance-{normalize_id(candidate_id)}.json"
    write_json(path, result)
    acceptance_lock = {
        "schema_version": SCHEMA_VERSION,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "ready": ready,
        "promotion_authority": authority,
        "decision_sha256": result["decision_sha256"],
        "created_at": now_iso(),
    }
    write_json(candidate_root / "acceptance-lock.json", acceptance_lock)
    campaign["status"] = "accepted_pending_owner" if ready and owner_required else "accepted_pending_agent" if ready else campaign.get("status")
    save_campaign(root, campaign)
    append_index(root, "acceptance_checked", campaign["campaign_id"], candidate_id=candidate_id, ready=ready, authority=authority)
    return result


def diagnose_campaign(
    root: Path,
    *,
    campaign_id: str,
    classification: str,
    summary: str,
    mechanism: str | None,
    surface_id: str | None,
    confidence: float | None,
) -> dict[str, Any]:
    campaign = load_campaign(root, campaign_id)
    try:
        result = cs_evolve.record_diagnosis(
            root,
            case_id=str(campaign["case_id"]),
            classification=classification,
            summary=summary,
            mechanism=mechanism,
            surface_id=surface_id,
            confidence=confidence,
        )
    except cs_evolve.EvolutionError as exc:
        raise MetaError(str(exc)) from exc
    if classification == "harness":
        policies = cs_policy.policy_map(root)
        allowed_surfaces = {str(policies[policy_id].get("surface_id")) for policy_id in campaign.get("policy_ids") or []}
        if surface_id not in allowed_surfaces:
            raise MetaError("diagnosis surface is outside the campaign policy scope")
        campaign["status"] = "proposal" if campaign.get("hypothesis") else "diagnose"
    else:
        campaign["status"] = "closed"
        campaign["closed_reason"] = classification
    save_campaign(root, campaign)
    append_index(root, "campaign_diagnosed", campaign["campaign_id"], classification=classification, surface_id=surface_id)
    return {"campaign": campaign, **result}


def create_evaluation_challenge(
    root: Path,
    *,
    campaign_id: str,
    candidate_id: str,
    model_profile: str,
    adapter: str,
    evaluator: str,
    budget: str,
    challenge_id: str | None = None,
) -> dict[str, Any]:
    campaign = load_campaign(root, campaign_id)
    validity_ref = (campaign.get("validity") or {}).get(normalize_id(candidate_id))
    if not isinstance(validity_ref, dict) or validity_ref.get("status") != "pass":
        raise MetaError("evaluation challenge requires a passing validity pre-pass")
    if model_profile not in set(str(value) for value in campaign.get("runtime_profiles") or []):
        raise MetaError("evaluation model/runtime profile is outside the campaign scope")
    try:
        result = cs_eval.create_challenge(
            root,
            case_id=str(campaign["case_id"]),
            candidate_id=candidate_id,
            model_profile=model_profile,
            adapter=adapter,
            evaluator=evaluator,
            budget=budget,
            challenge_id=challenge_id,
        )
    except cs_eval.EvaluationError as exc:
        raise MetaError(str(exc)) from exc
    campaign["status"] = "evaluation"
    save_campaign(root, campaign)
    append_index(root, "evaluation_challenge_created", campaign["campaign_id"], candidate_id=candidate_id, challenge_id=result["challenge"]["challenge_id"])
    return result


def decide_campaign(root: Path, *, campaign_id: str, candidate_id: str) -> dict[str, Any]:
    campaign = load_campaign(root, campaign_id)
    try:
        decision = cs_evolve.decide_candidate(root, str(campaign["case_id"]), candidate_id)
    except cs_evolve.EvolutionError as exc:
        raise MetaError(str(exc)) from exc
    campaign["status"] = "quality_gates" if decision.get("accepted") else "rejected"
    save_campaign(root, campaign)
    append_index(root, "evaluation_decided", campaign["campaign_id"], candidate_id=candidate_id, accepted=bool(decision.get("accepted")))
    return decision


def promote_campaign(
    root: Path,
    *,
    campaign_id: str,
    candidate_id: str,
    approval_kind: str,
    approved_by: str,
    reason: str,
) -> dict[str, Any]:
    campaign = load_campaign(root, campaign_id)
    kind = approval_kind.strip().casefold()
    if kind not in {"owner", "agent"}:
        raise MetaError("approval kind must be owner or agent")
    try:
        result = cs_evolve.promote_candidate(
            root,
            str(campaign["case_id"]),
            candidate_id,
            owner_approved=kind == "owner",
            agent_approved=kind == "agent",
            approved_by=approved_by,
            reason=reason,
        )
    except cs_evolve.EvolutionError as exc:
        raise MetaError(str(exc)) from exc
    return result


def rollback_harness(root: Path, *, version_id: str, approved_by: str, reason: str) -> dict[str, Any]:
    """Restore an immutable Harness version through the explicit Meta boundary."""
    try:
        result = cs_evolve.rollback(root, version_id, reason=reason, approved_by=approved_by)
    except cs_evolve.EvolutionError as exc:
        raise MetaError(str(exc)) from exc
    append_index(
        root,
        "harness_rolled_back",
        "rollback",
        version_id=version_id,
        approved_by=approved_by,
        reason=reason,
    )
    return result


def status(root: Path) -> dict[str, Any]:
    init_runtime(root)
    campaigns: list[dict[str, Any]] = []
    base = meta_dir(root) / "campaigns"
    for path in sorted(base.glob("*/campaign.json")):
        try:
            item = read_json(path)
        except MetaError:
            continue
        campaigns.append({
            "campaign_id": item.get("campaign_id"),
            "title": item.get("title"),
            "status": item.get("status"),
            "signal": item.get("signal"),
            "feedback_count": len(item.get("feedback_ids") or []),
            "policy_ids": item.get("policy_ids") or [],
            "runtime_profiles": item.get("runtime_profiles") or [],
            "candidate_ids": item.get("candidate_ids") or [],
        })
    return {
        "mode": "offline_explicit_meta",
        "normal_runs_import_meta": False,
        "policy_audit": cs_policy.audit_policies(root),
        "feedback_queue": cs_feedback.queue_summary(root),
        "campaigns": campaigns,
        "trigger": load_meta_config(root).get("trigger"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root")

    init_p = sub.add_parser("init", help="initialize the explicit Meta control plane")
    root_arg(init_p)

    status_p = sub.add_parser("status", help="show feedback, policy coverage, and campaigns")
    root_arg(status_p)

    audit = sub.add_parser("policy-audit", help="enforce no-fixture-no-evolution")
    root_arg(audit)

    trigger = sub.add_parser("trigger-scan", help="scan repeated signals; --apply only opens campaigns")
    root_arg(trigger)
    trigger.add_argument("--apply", action="store_true")

    campaign = sub.add_parser("campaign-new", help="open an explicit campaign from classified feedback")
    root_arg(campaign)
    campaign.add_argument("--title", required=True)
    campaign.add_argument("--feedback", action="append", required=True)
    campaign.add_argument("--signal", required=True)
    campaign.add_argument("--policy", action="append", required=True)
    campaign.add_argument("--runtime-profile", action="append", required=True)
    campaign.add_argument("--budget", required=True)
    campaign.add_argument("--campaign-id")

    diagnose = sub.add_parser("diagnose", help="triage campaign cause before proposing")
    root_arg(diagnose)
    diagnose.add_argument("--campaign", required=True)
    diagnose.add_argument("--classification", choices=cs_evolve.DIAGNOSIS_CLASSES, required=True)
    diagnose.add_argument("--summary", required=True)
    diagnose.add_argument("--mechanism")
    diagnose.add_argument("--surface")
    diagnose.add_argument("--confidence", type=float)

    freeze = sub.add_parser("hypothesis-freeze", help="freeze an agent-written, committed hypothesis")
    root_arg(freeze)
    freeze.add_argument("--campaign", required=True)
    freeze.add_argument("--file", required=True)
    freeze.add_argument("--actor", required=True)
    freeze.add_argument("--commit")

    proposal = sub.add_parser("proposal-register", help="validate and register an agent-authored variant")
    root_arg(proposal)
    proposal.add_argument("--campaign", required=True)
    proposal.add_argument("--proposal", required=True)
    proposal.add_argument("--overlay", required=True)

    prepass = sub.add_parser("validity-prepass", help="check fixture/oracle/variance/judge/provenance before evaluation")
    root_arg(prepass)
    prepass.add_argument("--campaign", required=True)
    prepass.add_argument("--candidate", required=True)
    prepass.add_argument("--repeats", type=int, required=True)
    prepass.add_argument("--judge-profile")
    prepass.add_argument("--actor", required=True)

    challenge = sub.add_parser("evaluation-challenge", help="freeze a post-validity trusted evaluation request")
    root_arg(challenge)
    challenge.add_argument("--campaign", required=True)
    challenge.add_argument("--candidate", required=True)
    challenge.add_argument("--model-profile", required=True)
    challenge.add_argument("--adapter", required=True)
    challenge.add_argument("--evaluator", required=True)
    challenge.add_argument("--budget", required=True)
    challenge.add_argument("--challenge-id")

    decide = sub.add_parser("decide", help="apply trusted evaluation rules after signed import")
    root_arg(decide)
    decide.add_argument("--campaign", required=True)
    decide.add_argument("--candidate", required=True)

    gate = sub.add_parser("quality-gate", help="record a measured quality/package/regression gate")
    root_arg(gate)
    gate.add_argument("--campaign", required=True)
    gate.add_argument("--name", required=True)
    gate.add_argument("--status", choices=sorted(QUALITY_GATE_STATUSES), required=True)
    gate.add_argument("--label", choices=sorted(MEASUREMENT_LABELS), required=True)
    gate.add_argument("--actor", required=True)
    gate.add_argument("--command")
    gate.add_argument("--evidence")
    gate.add_argument("--note")

    accept = sub.add_parser("acceptance-check", help="enforce validity, quality gates, and owner authority")
    root_arg(accept)
    accept.add_argument("--campaign", required=True)
    accept.add_argument("--candidate", required=True)

    promote = sub.add_parser("promote", help="promote after acceptance using policy-scoped authority")
    root_arg(promote)
    promote.add_argument("--campaign", required=True)
    promote.add_argument("--candidate", required=True)
    promote.add_argument("--approval-kind", choices=("owner", "agent"), required=True)
    promote.add_argument("--approved-by", required=True)
    promote.add_argument("--reason", required=True)

    rollback = sub.add_parser("rollback", help="restore an immutable Harness snapshot")
    root_arg(rollback)
    rollback.add_argument("--version", required=True)
    rollback.add_argument("--approved-by", required=True)
    rollback.add_argument("--reason", required=True)

    show = sub.add_parser("campaign-show", help="show one campaign")
    root_arg(show)
    show.add_argument("--campaign", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root_value = getattr(args, "root", None) or getattr(args, "global_root", None)
    try:
        root = find_project_root(explicit=root_value)
        if args.command == "init":
            result = init_runtime(root)
        elif args.command == "status":
            result = status(root)
        elif args.command == "policy-audit":
            result = cs_policy.audit_policies(root)
        elif args.command == "trigger-scan":
            result = trigger_scan(root, apply=args.apply)
        elif args.command == "campaign-new":
            result = {"campaign": create_campaign(
                root,
                title=args.title,
                feedback_ids=args.feedback,
                signal=args.signal,
                policy_ids=args.policy,
                runtime_profiles=args.runtime_profile,
                budget_id=args.budget,
                source="manual",
                campaign_id=args.campaign_id,
            )}
        elif args.command == "diagnose":
            result = diagnose_campaign(
                root,
                campaign_id=args.campaign,
                classification=args.classification,
                summary=args.summary,
                mechanism=args.mechanism,
                surface_id=args.surface,
                confidence=args.confidence,
            )
        elif args.command == "hypothesis-freeze":
            result = {"hypothesis": freeze_hypothesis(root, campaign_id=args.campaign, hypothesis_file=Path(args.file), actor=args.actor, commit=args.commit)}
        elif args.command == "proposal-register":
            result = register_proposal(root, campaign_id=args.campaign, proposal_file=Path(args.proposal), overlay=Path(args.overlay))
        elif args.command == "validity-prepass":
            result = {"validity": validity_prepass(root, campaign_id=args.campaign, candidate_id=args.candidate, repeats=args.repeats, judge_profile=args.judge_profile, actor=args.actor)}
        elif args.command == "evaluation-challenge":
            result = create_evaluation_challenge(
                root,
                campaign_id=args.campaign,
                candidate_id=args.candidate,
                model_profile=args.model_profile,
                adapter=args.adapter,
                evaluator=args.evaluator,
                budget=args.budget,
                challenge_id=args.challenge_id,
            )
        elif args.command == "decide":
            result = {"decision": decide_campaign(root, campaign_id=args.campaign, candidate_id=args.candidate)}
        elif args.command == "quality-gate":
            result = {"quality_gate": record_quality_gate(
                root,
                campaign_id=args.campaign,
                name=args.name,
                status=args.status,
                label=args.label,
                actor=args.actor,
                command=args.command,
                evidence_path=Path(args.evidence) if args.evidence else None,
                note=args.note,
            )}
        elif args.command == "acceptance-check":
            result = {"acceptance": acceptance_check(root, campaign_id=args.campaign, candidate_id=args.candidate)}
        elif args.command == "promote":
            result = promote_campaign(
                root,
                campaign_id=args.campaign,
                candidate_id=args.candidate,
                approval_kind=args.approval_kind,
                approved_by=args.approved_by,
                reason=args.reason,
            )
        elif args.command == "rollback":
            result = rollback_harness(
                root,
                version_id=args.version,
                approved_by=args.approved_by,
                reason=args.reason,
            )
        elif args.command == "campaign-show":
            result = {"campaign": load_campaign(root, args.campaign)}
        else:
            raise MetaError(f"unsupported command: {args.command}")
    except (MetaError, cs_policy.PolicyError, cs_feedback.FeedbackError, cs_evolve.EvolutionError, cs_eval.EvaluationError, OSError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
