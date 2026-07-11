#!/usr/bin/env python3
"""Non-destructively migrate 0.2-alpha telemetry runs into 0.3 observations.

Dry-run is the default. `--apply` copies finished legacy runs and never removes
or edits `.codestable/telemetry/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = 2
PASS_OUTCOMES = {"passed", "pass", "success", "ok", "completed"}
SAFE_EVENT_KEYS = {"stage", "tool", "attempt", "status", "category", "signal", "route", "lane", "action"}
SAFE_SIGNATURE_KEYS = {"verifier_cause", "causal_role", "agent_mechanism"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def normalize_id(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return (result or "legacy-run")[:96]


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def safe_legacy_payload(value: Any) -> dict[str, Any]:
    """Keep only compact allow-listed metadata; never copy raw legacy payloads."""
    digest = hashlib.sha256(canonical_json(value)).hexdigest()
    result: dict[str, Any] = {"legacy_payload_sha256": digest}
    if not isinstance(value, dict):
        return result
    for key in sorted(SAFE_EVENT_KEYS):
        child = value.get(key)
        if child is None or isinstance(child, (dict, list)):
            continue
        if isinstance(child, str):
            result[key] = child[:256]
        elif isinstance(child, (bool, int, float)):
            result[key] = child
    return result


def safe_failure_signature(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    for key in SAFE_SIGNATURE_KEYS:
        child = value.get(key)
        if child is not None:
            result[key] = str(child)[:512]
    return result or None


def normalize_event_type(value: Any) -> str:
    result = re.sub(r"[^a-z0-9_.-]+", "_", str(value or "legacy_event").strip().casefold()).strip("_.-")
    if not result or not result[0].isalpha():
        result = f"legacy_{result or 'event'}"
    return result[:64]


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def build_plan(root: Path) -> list[dict[str, Any]]:
    legacy = root / ".codestable" / "telemetry" / "runs"
    if not legacy.is_dir():
        return []
    plans: list[dict[str, Any]] = []
    for directory in sorted(legacy.iterdir()):
        if not directory.is_dir():
            continue
        run_path = directory / "run.json"
        summary_path = directory / "summary.json"
        if not run_path.is_file() or not summary_path.is_file():
            plans.append({
                "run_id": directory.name,
                "action": "skip",
                "reason": "unfinished_or_missing_summary",
            })
            continue
        run = read_json(run_path)
        summary = read_json(summary_path)
        outcome = str(summary.get("outcome") or "unknown").casefold()
        failure_signature = summary.get("failure_signature")
        flagged = outcome not in PASS_OUTCOMES or isinstance(failure_signature, dict)
        target_state = "flagged" if flagged else "pending"
        target = root / ".codestable" / "observations" / target_state / normalize_id(str(run.get("id") or directory.name))
        plans.append({
            "run_id": normalize_id(str(run.get("id") or directory.name)),
            "source": directory.relative_to(root).as_posix(),
            "target": target.relative_to(root).as_posix(),
            "state": target_state,
            "outcome": outcome,
            "action": "skip" if target.exists() else "copy",
            "reason": "target_exists" if target.exists() else "legacy_finished_run",
        })
    return plans


def convert(root: Path, plan: dict[str, Any]) -> None:
    source = root / plan["source"]
    target = root / plan["target"]
    target.mkdir(parents=True, exist_ok=False)
    run = read_json(source / "run.json")
    summary = read_json(source / "summary.json")
    legacy_events = load_events(source / "events.jsonl")
    signals: list[str] = []
    signature = summary.get("failure_signature")
    if isinstance(signature, dict):
        mechanism = str(signature.get("agent_mechanism") or "legacy_failure").strip().casefold()
        mechanism = re.sub(r"[^a-z0-9_.-]+", "_", mechanism).strip("_.") or "legacy_failure"
        signals.append(f"legacy.{mechanism[:80]}")
    outcome_text = str(summary.get("outcome") or "unknown").casefold()
    passed = outcome_text in PASS_OUTCOMES
    meta = {
        "schema_version": SCHEMA_VERSION,
        "run_id": plan["run_id"],
        "state": plan["state"],
        "status": "finished",
        "work_id": run.get("work"),
        "task_id": run.get("task_id"),
        "kind": "legacy",
        "lane": "unknown",
        "entry": "legacy-0.2-alpha",
        "route": "unknown",
        "start_stage": None,
        "end_stage": None,
        "harness": {
            "version": run.get("harness_version", "unknown"),
            "content_sha256": None,
            "snapshot_content_sha256": None,
            "drift_detected": False,
            "manifest_sha256": None,
        },
        "environment": {
            "repository_commit": None,
            "model_profile": run.get("model", "unknown"),
            "adapter": run.get("adapter", "unknown"),
        },
        "started_at": run.get("started_at"),
        "finished_at": run.get("ended_at") or summary.get("ended_at"),
        "event_count": len(legacy_events),
        "dropped_events": 0,
        "signals": signals,
        "selection": {"case_ids": []},
        "migration": {"source": plan["source"], "migrated_at": now_iso()},
    }
    (target / "meta.json").write_text(json_dump(meta), encoding="utf-8")
    with (target / "events.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for index, event in enumerate(legacy_events, start=1):
            converted = {
                "schema_version": SCHEMA_VERSION,
                "seq": index,
                "timestamp": event.get("timestamp"),
                "type": normalize_event_type(event.get("type")),
                "payload": safe_legacy_payload(event.get("payload")),
            }
            handle.write(json.dumps(converted, ensure_ascii=False, sort_keys=True) + "\n")
    validation = {
        "status": "passed" if passed else "failed",
        "verifier_id": str(run.get("evaluator") or "legacy-evaluator"),
        "command": None,
        "exit_code": 0 if passed else 1,
        "evidence": [],
        "issued_by": "legacy-migration",
    }
    outcome = {
        "schema_version": SCHEMA_VERSION,
        "run_id": plan["run_id"],
        "status": "completed" if passed else "failed",
        "task_validation": validation,
        "signals": signals,
        "metrics": summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {},
        "note": "Migrated from CodeStable 0.2 alpha; raw legacy notes remain only in the preserved telemetry directory.",
        "selected_for_evolution": False,
        "legacy_failure_signature": safe_failure_signature(signature),
    }
    (target / "outcome.json").write_text(json_dump(outcome), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="project root containing .codestable/telemetry")
    parser.add_argument("--apply", action="store_true", help="copy eligible runs; default is dry-run")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    try:
        plans = build_plan(root)
        applied: list[str] = []
        if args.apply:
            for plan in plans:
                if plan.get("action") != "copy":
                    continue
                convert(root, plan)
                applied.append(str(plan["run_id"]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({
        "ok": True,
        "root": str(root),
        "dry_run": not args.apply,
        "legacy_preserved": True,
        "plan": plans,
        "applied": applied,
    }), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
