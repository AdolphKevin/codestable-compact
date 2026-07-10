#!/usr/bin/env python3
"""Run public CodeStable Meta fixtures and emit labelled measurement evidence.

This deterministic helper does not generate or edit Harness policy. It only
executes registered public fixture runners, records what was actually measured,
and marks host/model-dependent fixtures as underpowered when no host adapter is
provided. Private held-out evaluation remains outside the candidate workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cs_policy  # type: ignore

SCHEMA_VERSION = 1
LABELS = {"measured", "soft", "underpowered"}


class FixtureError(RuntimeError):
    """A fixture selection, runner, or evidence invariant failed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def selected_fixture_ids(root: Path, *, fixture_ids: Sequence[str], policy_ids: Sequence[str], all_active: bool) -> list[str]:
    fixtures = cs_policy.fixture_map(root)
    selected: list[str] = []
    if all_active:
        selected.extend(
            fixture_id for fixture_id, item in fixtures.items()
            if item.get("status") == "active"
        )
    for fixture_id in fixture_ids:
        if fixture_id not in fixtures:
            raise FixtureError(f"unknown fixture id: {fixture_id}")
        selected.append(fixture_id)
    wanted_policies = {str(value) for value in policy_ids if str(value).strip()}
    if wanted_policies:
        known = set(cs_policy.policy_map(root))
        unknown = sorted(wanted_policies - known)
        if unknown:
            raise FixtureError(f"unknown policy ids: {unknown}")
        for fixture_id, item in fixtures.items():
            if wanted_policies.intersection(str(value) for value in item.get("covers_policies") or []):
                selected.append(fixture_id)
    result = sorted(set(selected))
    if not result:
        raise FixtureError("select at least one fixture, policy, or --all")
    return result


def run_subprocess(command: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    stdout = completed.stdout[-8000:]
    stderr = completed.stderr[-8000:]
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "passed": completed.returncode == 0,
    }


def run_python_unittest(runner: dict[str, Any], *, suite_root: Path, timeout: int) -> dict[str, Any]:
    tests_dir = suite_root / "tests"
    if not tests_dir.is_dir():
        return {
            "status": "underpowered",
            "label": "underpowered",
            "reason": f"test directory is unavailable at {tests_dir}",
        }
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(value for value in (str(tests_dir), existing) if value)
    if runner.get("test"):
        command = [sys.executable, "-m", "unittest", "-v", str(runner["test"])]
    else:
        pattern = str(runner.get("pattern") or "test*.py")
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"]
    measured = run_subprocess(command, cwd=suite_root, timeout=timeout, env=env)
    return {
        "status": "passed" if measured["passed"] else "failed",
        "label": "measured",
        "measurement": measured,
    }


def run_file_predicate(runner: dict[str, Any], *, project_root: Path) -> dict[str, Any]:
    try:
        relative = cs_policy.normalize_relative(str(runner.get("path") or ""))
    except cs_policy.PolicyError as exc:
        raise FixtureError(str(exc)) from exc
    path = project_root / relative
    if not path.is_file():
        return {"status": "failed", "label": "measured", "reason": f"missing file: {relative}"}
    text = path.read_text(encoding="utf-8", errors="replace").casefold()
    required = [str(value) for value in runner.get("contains") or []]
    missing = [value for value in required if value.casefold() not in text]
    forbidden = [str(value) for value in runner.get("not_contains") or []]
    present_forbidden = [value for value in forbidden if value.casefold() in text]
    passed = not missing and not present_forbidden
    return {
        "status": "passed" if passed else "failed",
        "label": "measured",
        "measurement": {
            "path": relative,
            "sha256": cs_policy.sha256_file(path),
            "missing_contains": missing,
            "present_forbidden": present_forbidden,
        },
    }


def run_command(runner: dict[str, Any], *, project_root: Path, timeout: int) -> dict[str, Any]:
    command = runner.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(value, str) and value for value in command):
        raise FixtureError("command runner requires a non-empty string array")
    result = run_subprocess(list(command), cwd=project_root, timeout=timeout)
    return {
        "status": "passed" if result["passed"] else "failed",
        "label": "measured",
        "measurement": result,
    }


def run_one(root: Path, suite_root: Path, fixture_id: str, *, timeout: int, host_adapter_result: Path | None) -> dict[str, Any]:
    entry = cs_policy.fixture_map(root)[fixture_id]
    fixture_path = root / str(entry["path"])
    fixture = cs_policy.fixture_document(root, entry)
    runner = fixture.get("runner") if isinstance(fixture.get("runner"), dict) else {}
    runner_type = str(runner.get("type") or "")
    started = now_iso()
    if runner_type == "python_unittest":
        outcome = run_python_unittest(runner, suite_root=suite_root, timeout=timeout)
    elif runner_type == "file_predicate":
        outcome = run_file_predicate(runner, project_root=root)
    elif runner_type == "command":
        outcome = run_command(runner, project_root=root, timeout=timeout)
    elif runner_type == "host_adapter":
        if host_adapter_result is None:
            outcome = {
                "status": "underpowered",
                "label": "underpowered",
                "reason": "fixture requires a real host/model adapter run",
            }
        else:
            supplied = json.loads(host_adapter_result.read_text(encoding="utf-8"))
            record = supplied.get(fixture_id) if isinstance(supplied, dict) else None
            if not isinstance(record, dict):
                outcome = {"status": "underpowered", "label": "underpowered", "reason": "host result missing fixture"}
            else:
                label = str(record.get("label") or "soft")
                if label not in LABELS:
                    raise FixtureError(f"invalid host result label for {fixture_id}: {label}")
                status = str(record.get("status") or "")
                if status not in {"passed", "failed", "underpowered"}:
                    raise FixtureError(f"invalid host result status for {fixture_id}: {status}")
                outcome = {"status": status, "label": label, "measurement": record.get("measurement") or {}}
    else:
        outcome = {"status": "underpowered", "label": "underpowered", "reason": f"unsupported runner type: {runner_type}"}
    return {
        "fixture_id": fixture_id,
        "fixture_sha256": cs_policy.sha256_file(fixture_path),
        "layers": fixture.get("layers") or [],
        "covers_policies": fixture.get("covers_policies") or [],
        "runner_type": runner_type,
        "started_at": started,
        "finished_at": now_iso(),
        **outcome,
    }


def run_suite(
    root: Path,
    *,
    suite_root: Path,
    fixture_ids: Sequence[str],
    policy_ids: Sequence[str],
    all_active: bool,
    timeout: int,
    host_adapter_result: Path | None,
) -> dict[str, Any]:
    audit = cs_policy.require_clean_audit(root)
    selected = selected_fixture_ids(root, fixture_ids=fixture_ids, policy_ids=policy_ids, all_active=all_active)
    rows = [run_one(root, suite_root, fixture_id, timeout=timeout, host_adapter_result=host_adapter_result) for fixture_id in selected]
    counts = {
        status: sum(1 for item in rows if item.get("status") == status)
        for status in ("passed", "failed", "underpowered")
    }
    labels = {
        label: sum(1 for item in rows if item.get("label") == label)
        for label in sorted(LABELS)
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": cs_policy.load_fixture_index(root).get("suite_id"),
        "project_root": str(root),
        "suite_root": str(suite_root),
        "fixture_ids": selected,
        "fixture_set_sha256": cs_policy.fixture_set_sha256(root, selected),
        "policy_registry_sha256": audit["policy_registry_sha256"],
        "fixture_index_sha256": audit["fixture_index_sha256"],
        "counts": counts,
        "labels": labels,
        "promotion_eligible": counts["failed"] == 0 and counts["underpowered"] == 0,
        "results": rows,
        "measured_at": now_iso(),
    }
    result["result_sha256"] = sha256_bytes(canonical_json({key: value for key, value in result.items() if key != "result_sha256"}))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", dest="global_root")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run selected public fixtures")
    run.add_argument("--root")
    run.add_argument("--suite-root", default=".")
    run.add_argument("--fixture", action="append", default=[])
    run.add_argument("--policy", action="append", default=[])
    run.add_argument("--all", action="store_true")
    run.add_argument("--timeout", type=int, default=180)
    run.add_argument("--host-result")
    run.add_argument("--output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root_value = getattr(args, "root", None) or getattr(args, "global_root", None)
    try:
        root = cs_policy.find_project_root(explicit=root_value)
        if args.command != "run":
            raise FixtureError(f"unsupported command: {args.command}")
        result = run_suite(
            root,
            suite_root=Path(args.suite_root).expanduser().resolve(),
            fixture_ids=args.fixture,
            policy_ids=args.policy,
            all_active=args.all,
            timeout=args.timeout,
            host_adapter_result=Path(args.host_result).expanduser().resolve() if args.host_result else None,
        )
        if args.output:
            output = Path(args.output).expanduser().resolve()
            atomic_write(output, json_dump(result))
            payload = {"output": str(output), **result}
        else:
            payload = result
    except (FixtureError, cs_policy.PolicyError, OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(json_dump({"ok": True, **payload}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
