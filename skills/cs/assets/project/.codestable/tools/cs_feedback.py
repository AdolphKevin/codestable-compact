#!/usr/bin/env python3
"""Production feedback triage and feedback-to-fixture pipeline for CodeStable.

This tool never modifies Harness policy. It turns a named finished observation
into a classified feedback item, and can register an agent-authored regression
fixture after validating its schema and provenance links.
"""

from __future__ import annotations

import argparse
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

import cs_observe  # type: ignore
import cs_policy  # type: ignore

SCHEMA_VERSION = 1
CLASSIFICATIONS = {
    "harness_policy",
    "evaluation_defect",
    "model_profile_variance",
    "project_knowledge",
    "product_code",
    "environment",
    "insufficient_evidence",
}
FEEDBACK_STATUSES = {"triaged", "fixture_registered", "queued", "assigned", "closed"}


class FeedbackError(RuntimeError):
    """A feedback triage or fixture registration invariant failed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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
        raise FeedbackError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FeedbackError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FeedbackError(f"JSON root must be an object: {path}")
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
        raise FeedbackError("identifier cannot be empty")
    return result[:128]


def find_project_root(start: Path | None = None, explicit: str | None = None) -> Path:
    try:
        return cs_policy.find_project_root(start=start, explicit=explicit)
    except cs_policy.PolicyError as exc:
        raise FeedbackError(str(exc)) from exc


def cs_dir(root: Path) -> Path:
    return root / ".codestable"


def feedback_dir(root: Path) -> Path:
    return cs_dir(root) / "meta" / "feedback"


def item_path(root: Path, feedback_id: str) -> Path:
    return feedback_dir(root) / "items" / f"{normalize_id(feedback_id)}.json"


def init_runtime(root: Path) -> dict[str, Any]:
    base = feedback_dir(root)
    created: list[str] = []
    preserved: list[str] = []
    for directory in (base / "items", cs_dir(root) / "evals" / "fixtures" / "production"):
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
    return {"created": created, "preserved": preserved}


def append_index(root: Path, action: str, feedback_id: str, **extra: Any) -> None:
    append_jsonl(
        feedback_dir(root) / "index.jsonl",
        {
            "schema_version": SCHEMA_VERSION,
            "timestamp": now_iso(),
            "action": action,
            "feedback_id": feedback_id,
            **extra,
        },
    )


def load_feedback(root: Path, feedback_id: str) -> dict[str, Any]:
    return read_json(item_path(root, feedback_id))


def runtime_profile_from_observation(meta: dict[str, Any]) -> dict[str, Any]:
    environment = meta.get("environment") if isinstance(meta.get("environment"), dict) else {}
    return {
        "model_profile": str(environment.get("model_profile") or "unknown"),
        "adapter": str(environment.get("adapter") or "unknown"),
        "repository_commit": environment.get("repository_commit"),
    }


def triage_feedback(
    root: Path,
    *,
    run_id: str,
    classification: str,
    signal: str,
    summary: str,
    policy_ids: Sequence[str] = (),
    actor: str,
    fixture_required: bool = True,
    feedback_id: str | None = None,
) -> dict[str, Any]:
    init_runtime(root)
    normalized_classification = classification.strip().casefold()
    if normalized_classification not in CLASSIFICATIONS:
        raise FeedbackError(f"invalid feedback classification: {classification}")
    normalized_signal = cs_observe.normalize_signal(signal)
    if not summary.strip():
        raise FeedbackError("feedback summary is required")
    if not actor.strip():
        raise FeedbackError("feedback triage requires an actor")
    try:
        observation = cs_observe.load_observation(root, run_id)
    except cs_observe.ObservationError as exc:
        raise FeedbackError(str(exc)) from exc
    meta = observation["meta"]
    outcome = observation["outcome"]
    if meta.get("status") != "finished" or not isinstance(outcome, dict):
        raise FeedbackError("only finished observations can be triaged")

    policies = cs_policy.policy_map(root)
    selected_policies = list(dict.fromkeys(str(value).strip() for value in policy_ids if str(value).strip()))
    unknown = [policy_id for policy_id in selected_policies if policy_id not in policies]
    if unknown:
        raise FeedbackError(f"unknown policy ids: {unknown}")
    if normalized_classification == "harness_policy" and not selected_policies:
        raise FeedbackError("Harness-policy feedback must identify at least one policy")
    if normalized_classification != "harness_policy" and selected_policies:
        raise FeedbackError("only Harness-policy feedback may claim affected policy ids")

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    identifier = normalize_id(feedback_id or f"fb-{timestamp}-{normalized_signal}")
    path = item_path(root, identifier)
    if path.exists():
        raise FeedbackError(f"feedback already exists: {identifier}")

    # Make the signal discoverable without changing the Harness or opening a campaign.
    try:
        cs_observe.flag_observation(root, run_id, signals=(normalized_signal,), note=summary)
    except cs_observe.ObservationError as exc:
        raise FeedbackError(str(exc)) from exc
    observation = cs_observe.load_observation(root, run_id)
    meta = observation["meta"]
    outcome = observation["outcome"] or outcome

    item = {
        "schema_version": SCHEMA_VERSION,
        "feedback_id": identifier,
        "run_id": str(meta.get("run_id")),
        "observation_state": observation["state"],
        "classification": normalized_classification,
        "signal": normalized_signal,
        "summary": summary.strip(),
        "policy_ids": selected_policies,
        "runtime_profile": runtime_profile_from_observation(meta),
        "harness": meta.get("harness") or {},
        "task": {
            "kind": meta.get("kind"),
            "route": meta.get("route"),
            "risk_level": meta.get("risk_level"),
            "start_action": meta.get("start_action"),
            "end_action": meta.get("end_action"),
            "work_id": meta.get("work_id"),
            "task_id": meta.get("task_id"),
            "outcome": outcome.get("status"),
            "validation_status": (outcome.get("task_validation") or {}).get("status"),
        },
        "trace_summary": outcome.get("trace_summary") or {},
        "fixture_required": bool(fixture_required),
        "fixture_ids": [],
        "campaign_ids": [],
        "status": "triaged",
        "triaged_by": actor.strip(),
        "triaged_at": now_iso(),
        "updated_at": now_iso(),
    }
    write_json(path, item)
    append_index(
        root,
        "triaged",
        identifier,
        run_id=item["run_id"],
        classification=normalized_classification,
        signal=normalized_signal,
        policy_ids=selected_policies,
    )
    return item


def validate_fixture_document(root: Path, fixture: dict[str, Any], *, feedback: dict[str, Any]) -> dict[str, Any]:
    required = (
        "schema_version",
        "id",
        "title",
        "layers",
        "covers_policies",
        "status",
        "context",
        "oracle",
        "scorer",
        "execution",
        "runner",
        "expected",
    )
    missing = [field for field in required if field not in fixture]
    if missing:
        raise FeedbackError(f"fixture is missing fields: {missing}")
    fixture_id = normalize_id(str(fixture.get("id") or ""))
    layers = fixture.get("layers")
    if not isinstance(layers, list) or not layers:
        raise FeedbackError("fixture layers must be a non-empty array")
    policy_ids = fixture.get("covers_policies")
    if not isinstance(policy_ids, list):
        raise FeedbackError("fixture covers_policies must be an array")
    known_policies = cs_policy.policy_map(root)
    unknown = [policy_id for policy_id in policy_ids if str(policy_id) not in known_policies]
    if unknown:
        raise FeedbackError(f"fixture references unknown policies: {unknown}")
    if feedback.get("classification") == "harness_policy":
        expected = set(str(value) for value in feedback.get("policy_ids") or [])
        actual = set(str(value) for value in policy_ids)
        if not expected.intersection(actual):
            raise FeedbackError("fixture must cover at least one policy named by the feedback")
    context = fixture.get("context")
    if not isinstance(context, dict):
        raise FeedbackError("fixture context must be an object")
    for field in ("required_refs", "subject_matter_refs"):
        values = context.get(field)
        if not isinstance(values, list):
            raise FeedbackError(f"fixture context.{field} must be an array")
        for value in values:
            relative = cs_policy.normalize_relative(str(value))
            if not (root / relative).exists():
                raise FeedbackError(f"fixture context reference does not exist: {relative}")
    oracle = fixture.get("oracle")
    if not isinstance(oracle, dict) or not str(oracle.get("type") or ""):
        raise FeedbackError("fixture oracle must declare a type")
    scorer = fixture.get("scorer")
    if not isinstance(scorer, dict) or not str(scorer.get("id") or ""):
        raise FeedbackError("fixture scorer must declare an id")
    execution = fixture.get("execution")
    if not isinstance(execution, dict):
        raise FeedbackError("fixture execution must be an object")
    repeats = execution.get("minimum_repeats")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise FeedbackError("fixture execution.minimum_repeats must be a positive integer")
    clean = json.loads(json.dumps(fixture))
    clean["id"] = fixture_id
    clean["source_feedback_ids"] = sorted(
        set(str(value) for value in (*clean.get("source_feedback_ids", []), feedback["feedback_id"]))
    )
    clean["registered_at"] = now_iso()
    return clean


def register_fixture(
    root: Path,
    *,
    feedback_id: str,
    fixture_file: Path,
    actor: str,
) -> dict[str, Any]:
    if not actor.strip():
        raise FeedbackError("fixture registration requires an actor")
    feedback = load_feedback(root, feedback_id)
    source_path = fixture_file.expanduser().resolve()
    fixture = read_json(source_path)
    clean = validate_fixture_document(root, fixture, feedback=feedback)
    fixture_id = str(clean["id"])
    destination = cs_dir(root) / "evals" / "fixtures" / "production" / fixture_id / "fixture.json"
    if destination.exists():
        raise FeedbackError(f"fixture already exists: {fixture_id}")
    write_json(destination, clean)

    index_path = cs_policy.fixture_index_path(root)
    index = cs_policy.load_fixture_index(root)
    if any(isinstance(item, dict) and item.get("id") == fixture_id for item in index["fixtures"]):
        destination.unlink(missing_ok=True)
        raise FeedbackError(f"fixture index already contains: {fixture_id}")
    index["fixtures"].append(
        {
            "id": fixture_id,
            "path": destination.relative_to(root).as_posix(),
            "layers": list(clean.get("layers") or []),
            "covers_policies": list(clean.get("covers_policies") or []),
            "status": "active",
            "deterministic": bool((clean.get("oracle") or {}).get("deterministic")),
            "source_feedback_ids": [feedback["feedback_id"]],
        }
    )
    index["fixtures"].sort(key=lambda item: str(item.get("id") or ""))
    cs_policy.write_json(index_path, index)

    feedback.setdefault("fixture_ids", []).append(fixture_id)
    feedback["fixture_ids"] = sorted(set(feedback["fixture_ids"]))
    feedback["status"] = "fixture_registered"
    feedback["fixture_registered_by"] = actor.strip()
    feedback["updated_at"] = now_iso()
    write_json(item_path(root, feedback["feedback_id"]), feedback)
    append_index(root, "fixture_registered", feedback["feedback_id"], fixture_id=fixture_id, actor=actor.strip())
    return {
        "feedback": feedback,
        "fixture": clean,
        "fixture_path": destination.relative_to(root).as_posix(),
        "fixture_sha256": cs_policy.sha256_file(destination),
        "fixture_index_sha256": cs_policy.sha256_file(index_path),
    }


def assign_campaign(root: Path, feedback_ids: Sequence[str], campaign_id: str) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    normalized_campaign = normalize_id(campaign_id)
    for feedback_id in feedback_ids:
        item = load_feedback(root, feedback_id)
        campaigns = list(dict.fromkeys([*(item.get("campaign_ids") or []), normalized_campaign]))
        item["campaign_ids"] = campaigns
        item["status"] = "assigned"
        item["updated_at"] = now_iso()
        write_json(item_path(root, item["feedback_id"]), item)
        append_index(root, "assigned", item["feedback_id"], campaign_id=normalized_campaign)
        updated.append(item)
    return updated


def iter_feedback(root: Path) -> Iterable[dict[str, Any]]:
    init_runtime(root)
    for path in sorted((feedback_dir(root) / "items").glob("*.json")):
        try:
            yield read_json(path)
        except FeedbackError:
            continue


def list_feedback(
    root: Path,
    *,
    classification: str | None = None,
    signal: str | None = None,
    status: str | None = None,
    unassigned_only: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    if limit < 1 or limit > 1000:
        raise FeedbackError("feedback list limit must be between 1 and 1000")
    rows: list[dict[str, Any]] = []
    for item in iter_feedback(root):
        if classification and item.get("classification") != classification:
            continue
        if signal and item.get("signal") != signal:
            continue
        if status and item.get("status") != status:
            continue
        if unassigned_only and item.get("campaign_ids"):
            continue
        rows.append(item)
    rows.sort(key=lambda item: str(item.get("triaged_at") or ""), reverse=True)
    return {"feedback": rows[:limit], "count": min(len(rows), limit), "matched": len(rows)}


def queue_summary(root: Path) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for item in iter_feedback(root):
        if item.get("classification") != "harness_policy" or item.get("campaign_ids"):
            continue
        harness = item.get("harness") if isinstance(item.get("harness"), dict) else {}
        key = f"{item.get('signal')}|{','.join(sorted(str(value) for value in item.get('policy_ids') or []))}|{(item.get('runtime_profile') or {}).get('adapter')}|{(item.get('runtime_profile') or {}).get('model_profile')}|{harness.get('version')}|{harness.get('content_sha256')}"
        group = groups.setdefault(
            key,
            {
                "signal": item.get("signal"),
                "policy_ids": item.get("policy_ids") or [],
                "runtime_profile": item.get("runtime_profile") or {},
                "harness": {"version": harness.get("version"), "content_sha256": harness.get("content_sha256")},
                "feedback_ids": [],
            },
        )
        group["feedback_ids"].append(item["feedback_id"])
    values = []
    for group in groups.values():
        group["count"] = len(group["feedback_ids"])
        values.append(group)
    values.sort(key=lambda item: (-int(item["count"]), str(item["signal"])))
    return {"groups": values, "unassigned_harness_feedback": sum(int(item["count"]) for item in values)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root")

    init_p = sub.add_parser("init", help="initialize feedback storage")
    root_arg(init_p)

    triage = sub.add_parser("triage", help="classify one named finished observation")
    root_arg(triage)
    triage.add_argument("--run", required=True)
    triage.add_argument("--classification", choices=sorted(CLASSIFICATIONS), required=True)
    triage.add_argument("--signal", required=True)
    triage.add_argument("--summary", required=True)
    triage.add_argument("--policy", action="append", default=[])
    triage.add_argument("--actor", required=True)
    triage.add_argument("--fixture-not-required", action="store_true")
    triage.add_argument("--feedback-id")

    register = sub.add_parser("fixture-register", help="register an agent-authored fixture for feedback")
    root_arg(register)
    register.add_argument("--feedback", required=True)
    register.add_argument("--file", required=True)
    register.add_argument("--actor", required=True)

    list_p = sub.add_parser("list", help="list classified feedback")
    root_arg(list_p)
    list_p.add_argument("--classification", choices=sorted(CLASSIFICATIONS))
    list_p.add_argument("--signal")
    list_p.add_argument("--status", choices=sorted(FEEDBACK_STATUSES))
    list_p.add_argument("--unassigned-only", action="store_true")
    list_p.add_argument("--limit", type=int, default=100)

    show = sub.add_parser("show", help="show one feedback item")
    root_arg(show)
    show.add_argument("--feedback", required=True)

    queue = sub.add_parser("queue", help="group unassigned Harness feedback without opening campaigns")
    root_arg(queue)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root_value = getattr(args, "root", None) or getattr(args, "global_root", None)
    try:
        root = find_project_root(explicit=root_value)
        if args.command == "init":
            result = init_runtime(root)
        elif args.command == "triage":
            result = {
                "feedback": triage_feedback(
                    root,
                    run_id=args.run,
                    classification=args.classification,
                    signal=args.signal,
                    summary=args.summary,
                    policy_ids=args.policy,
                    actor=args.actor,
                    fixture_required=not args.fixture_not_required,
                    feedback_id=args.feedback_id,
                )
            }
        elif args.command == "fixture-register":
            result = register_fixture(root, feedback_id=args.feedback, fixture_file=Path(args.file), actor=args.actor)
        elif args.command == "list":
            result = list_feedback(
                root,
                classification=args.classification,
                signal=args.signal,
                status=args.status,
                unassigned_only=args.unassigned_only,
                limit=args.limit,
            )
        elif args.command == "show":
            result = {"feedback": load_feedback(root, args.feedback)}
        elif args.command == "queue":
            result = queue_summary(root)
        else:
            raise FeedbackError(f"unsupported command: {args.command}")
    except (FeedbackError, cs_observe.ObservationError, cs_policy.PolicyError, OSError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **result}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
