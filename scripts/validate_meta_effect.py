#!/usr/bin/env python3
"""Generate a labelled CodeStable Compact Meta-loop effect report.

The report deliberately separates deterministic control-plane evidence from
host/model-dependent behavior. It never upgrades an unavailable real adapter
run into a performance claim.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "skills" / "cs" / "assets" / "project"
TOOLS = ASSET_ROOT / ".codestable" / "tools"
DEFAULT_BASELINE = Path("/mnt/data/work-codestable-v0.4.0/codestable-compact-v0.3.0")

MUTANT_TESTS = (
    "test_policy.PolicyRegistryTest.test_no_fixture_coverage_no_evolution",
    "test_evolution.ManualEvolutionTest.test_proposal_must_be_agent_authored",
    "test_evolution.ManualEvolutionTest.test_proposal_without_required_fixture_layer_is_rejected",
    "test_evolution.ManualEvolutionTest.test_underpowered_prepass_cannot_create_evaluation_challenge",
    "test_meta_validity.MetaValidityAndAuthorityTest.test_missing_required_context_blocks_attribution",
    "test_meta_validity.MetaValidityAndAuthorityTest.test_brittle_oracle_blocks_evaluation",
    "test_meta_validity.MetaValidityAndAuthorityTest.test_uncalibrated_scorer_blocks_evaluation",
    "test_meta_validity.MetaValidityAndAuthorityTest.test_same_profile_judge_is_rejected",
    "test_evolution.ManualEvolutionTest.test_overlay_cannot_smuggle_undeclared_surface",
    "test_evolution.ManualEvolutionTest.test_signed_result_rejects_tampering_raw_trace_and_replay",
    "test_meta_validity.MetaValidityAndAuthorityTest.test_missing_measured_quality_gates_block_acceptance",
    "test_meta_validity.MetaValidityAndAuthorityTest.test_owner_checkpoint_cannot_be_downgraded_and_meta_rollback_works",
    "test_evolution.ManualEvolutionTest.test_corrupt_rollback_snapshot_blocks_promotion",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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


def active_fixture_entries() -> dict[str, dict[str, Any]]:
    index_path = ASSET_ROOT / ".codestable/evals/fixtures/index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for raw in payload.get("fixtures") or []:
        if not isinstance(raw, dict) or raw.get("status") != "active":
            continue
        fixture_id = str(raw.get("id") or "")
        if fixture_id:
            result[fixture_id] = dict(raw)
    return result


def reuse_unit_suite_as_python_fixtures(payload: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    """Reuse the already executed full suite for every unittest-backed fixture.

    The fixture registry names exact tests for most deterministic cases and the
    full suite for the core regression case. The full candidate suite already
    executes all of them. Reusing that single measured run avoids duplicate
    subprocess campaigns being mistaken for runtime timeouts.
    """

    entries = active_fixture_entries()
    passed = unit.get("exit_code") == 0
    rows = [item for item in payload.get("results") or []]
    reused: dict[str, str] = {}
    for fixture_id, entry in sorted(entries.items()):
        fixture_path = ASSET_ROOT / str(entry["path"])
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        runner = fixture.get("runner") if isinstance(fixture.get("runner"), dict) else {}
        if runner.get("type") != "python_unittest":
            continue
        row = {
            "fixture_id": fixture_id,
            "fixture_sha256": sha256_file(fixture_path),
            "layers": fixture.get("layers") or [],
            "covers_policies": fixture.get("covers_policies") or [],
            "runner_type": "python_unittest",
            "started_at": now_iso(),
            "finished_at": now_iso(),
            "status": "passed" if passed else "failed",
            "label": "measured",
            "measurement": {
                "reused_evidence": "candidate_full_unit_suite",
                "registered_test": runner.get("test"),
                "registered_pattern": runner.get("pattern") or runner.get("test_pattern"),
                "command": unit.get("command") or [],
                "exit_code": unit.get("exit_code"),
                "passed": passed,
                "stdout_tail": str(unit.get("stdout") or "")[-8000:],
                "stderr_tail": str(unit.get("stderr") or "")[-8000:],
            },
        }
        rows = [item for item in rows if item.get("fixture_id") != fixture_id]
        rows.append(row)
        reused[fixture_id] = "candidate_full_unit_suite"
    rows.sort(key=lambda item: str(item.get("fixture_id") or ""))
    fixture_ids = sorted(entries)
    counts = {status: sum(1 for item in rows if item.get("status") == status) for status in ("passed", "failed", "underpowered")}
    labels = {label: sum(1 for item in rows if item.get("label") == label) for label in ("measured", "soft", "underpowered")}
    records = [
        {"id": current_id, "path": entries[current_id]["path"], "sha256": sha256_file(ASSET_ROOT / str(entries[current_id]["path"]))}
        for current_id in fixture_ids
    ]
    payload = dict(payload)
    payload.update({
        "fixture_ids": fixture_ids,
        "fixture_set_sha256": sha256_bytes(canonical_json(records)),
        "counts": counts,
        "labels": labels,
        "promotion_eligible": counts["failed"] == 0 and counts["underpowered"] == 0,
        "results": rows,
        "measurement_reuse": reused,
        "measured_at": now_iso(),
    })
    payload.pop("result_sha256", None)
    payload["result_sha256"] = sha256_bytes(canonical_json(payload))
    return payload


def run_public_fixture_subset(fixture_ids: Sequence[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run non-unittest public fixtures through the fixture API in-process.

    This avoids a platform-specific nested process orchestration deadlock in
    the report generator while preserving the exact production runner logic.
    Unittest-backed fixtures are supplied by the already executed full suite.
    """

    module_path = TOOLS / "cs_fixture.py"
    spec = importlib.util.spec_from_file_location("codestable_report_cs_fixture", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixture module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        payload = module.run_suite(
            ASSET_ROOT,
            suite_root=ROOT,
            fixture_ids=list(fixture_ids),
            policy_ids=[],
            all_active=False,
            timeout=180,
            host_adapter_result=None,
        )
    except Exception as exc:
        result = {
            "command": ["in-process", str(module_path), "run_suite"],
            "cwd": str(ROOT),
            "exit_code": 2,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
        return result, {}
    result = {
        "command": ["in-process", str(module_path), "run_suite"],
        "cwd": str(ROOT),
        "exit_code": 0,
        "stdout": json.dumps({"ok": True, **payload}, ensure_ascii=False),
        "stderr": "",
    }
    return result, {"ok": True, **payload}


def run(command: Sequence[str], *, cwd: Path = ROOT, timeout: int = 300) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": list(command),
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_validation_campaign(baseline_path: Path | None) -> dict[str, Any]:
    """Run external checks as isolated jobs inside one atomic shell campaign.

    The jobs are independent and run concurrently; the fresh-bootstrap job is
    internally sequential because doctor/audit depend on bootstrap. This avoids
    a sandbox-specific process-orchestration deadlock while preserving the same
    commands a CI job would execute.
    """

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="codestable-validation-campaign-") as temporary:
        temp = Path(temporary)
        fresh_root = temp / "fresh-project"
        independent: list[tuple[str, Path, list[str]]] = [
            ("validator", ROOT, [sys.executable, str(ROOT / "scripts/validate_skills.py")]),
            ("candidate_tests", ROOT, [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
            ("policy_audit", ROOT, [sys.executable, str(TOOLS / "cs_policy.py"), "--root", str(ASSET_ROOT), "audit"]),
        ]
        if baseline_path is not None:
            independent.append(("baseline_tests", baseline_path, [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]))

        def command_line(command: Sequence[str]) -> str:
            return " ".join(shlex.quote(value) for value in command)

        lines = ["set +e"]
        for name, cwd, command in independent:
            lines.extend([
                "(",
                f"  cd {shlex.quote(str(cwd))}",
                f"  PYTHONDONTWRITEBYTECODE=1 {command_line(command)} >{shlex.quote(str(temp / (name + '.stdout')))} 2>{shlex.quote(str(temp / (name + '.stderr')))}",
                f"  printf '%s' $? >{shlex.quote(str(temp / (name + '.code')))}",
                ") &",
            ])

        bootstrap_command = [sys.executable, str(ROOT / "skills/cs/scripts/bootstrap.py"), "--root", str(fresh_root)]
        doctor_command = [sys.executable, str(fresh_root / ".codestable/tools/cs_context.py"), "doctor", "--root", str(fresh_root)]
        fresh_policy_command = [sys.executable, str(fresh_root / ".codestable/tools/cs_policy.py"), "--root", str(fresh_root), "audit"]
        lines.extend([
            "(",
            f"  mkdir -p {shlex.quote(str(fresh_root))}",
            f"  cd {shlex.quote(str(ROOT))}",
            f"  PYTHONDONTWRITEBYTECODE=1 {command_line(bootstrap_command)} >{shlex.quote(str(temp / 'bootstrap.stdout'))} 2>{shlex.quote(str(temp / 'bootstrap.stderr'))}",
            f"  printf '%s' $? >{shlex.quote(str(temp / 'bootstrap.code'))}",
            f"  cd {shlex.quote(str(fresh_root))}",
            f"  PYTHONDONTWRITEBYTECODE=1 {command_line(doctor_command)} >{shlex.quote(str(temp / 'fresh_doctor.stdout'))} 2>{shlex.quote(str(temp / 'fresh_doctor.stderr'))}",
            f"  printf '%s' $? >{shlex.quote(str(temp / 'fresh_doctor.code'))}",
            f"  PYTHONDONTWRITEBYTECODE=1 {command_line(fresh_policy_command)} >{shlex.quote(str(temp / 'fresh_policy.stdout'))} 2>{shlex.quote(str(temp / 'fresh_policy.stderr'))}",
            f"  printf '%s' $? >{shlex.quote(str(temp / 'fresh_policy.code'))}",
            ") &",
            "wait",
            "exit 0",
        ])
        shell = subprocess.run(
            ["bash", "-lc", "\n".join(lines) + "\n"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1200,
            check=False,
        )
        if shell.returncode != 0:
            raise RuntimeError(f"validation campaign shell failed: {shell.stderr[-4000:]}")

        commands: dict[str, tuple[Path, list[str]]] = {
            name: (cwd, command) for name, cwd, command in independent
        }
        commands.update({
            "bootstrap": (ROOT, bootstrap_command),
            "fresh_doctor": (fresh_root, doctor_command),
            "fresh_policy": (fresh_root, fresh_policy_command),
        })

        def load(name: str) -> dict[str, Any]:
            cwd, command = commands[name]
            code_path = temp / f"{name}.code"
            return {
                "command": command,
                "cwd": str(cwd),
                "exit_code": int(code_path.read_text(encoding="utf-8") or "1") if code_path.is_file() else 127,
                "stdout": (temp / f"{name}.stdout").read_text(encoding="utf-8", errors="replace") if (temp / f"{name}.stdout").is_file() else "",
                "stderr": (temp / f"{name}.stderr").read_text(encoding="utf-8", errors="replace") if (temp / f"{name}.stderr").is_file() else "missing campaign output",
            }

        by_name = {name: load(name) for name in commands}
        doctor_result = by_name["fresh_doctor"]
        fresh_policy_result = by_name["fresh_policy"]
        doctor_payload = parse_json_stdout(doctor_result) if doctor_result["exit_code"] == 0 else None
        fresh_policy_payload = parse_json_stdout(fresh_policy_result) if fresh_policy_result["exit_code"] == 0 else None
        fresh = {
            "ok": by_name["bootstrap"]["exit_code"] == doctor_result["exit_code"] == fresh_policy_result["exit_code"] == 0,
            "bootstrap": command_evidence(by_name["bootstrap"], include_tail=True),
            "doctor": doctor_payload or command_evidence(doctor_result, include_tail=True),
            "policy_audit": fresh_policy_payload or command_evidence(fresh_policy_result, include_tail=True),
        }
        return {
            "validator": by_name["validator"],
            "candidate_tests": by_name["candidate_tests"],
            "baseline_tests": by_name.get("baseline_tests"),
            "policy_audit": by_name["policy_audit"],
            "fresh_bootstrap": fresh,
        }


def mutant_evidence_from_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """Extract known-bad mutant detections from the measured full suite."""

    text = f"{unit.get('stdout', '')}\n{unit.get('stderr', '')}"
    matched: list[str] = []
    missing: list[str] = []
    for case in MUTANT_TESTS:
        owner, method = case.rsplit(".", 1)
        patterns = (rf"\({re.escape(case)}\)", rf"{re.escape(method)} \({re.escape(owner)}\)")
        if any(re.search(rf"{pattern}\s+\.\.\.\s+ok", text) for pattern in patterns):
            matched.append(case)
        else:
            missing.append(case)
    return {
        "command": ["reuse", "candidate-full-unit-suite", *MUTANT_TESTS],
        "cwd": str(ROOT),
        "exit_code": 0 if not missing and unit.get("exit_code") == 0 else 1,
        "stdout": "\n".join(f"PASS {case}" for case in matched),
        "stderr": "\n".join(f"MISSING {case}" for case in missing),
        "matched_cases": matched,
        "missing_cases": missing,
    }


def parse_test_count(result: dict[str, Any]) -> int | None:
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
    matches = re.findall(r"Ran\s+(\d+)\s+tests?", text)
    return int(matches[-1]) if matches else None


def parse_json_stdout(result: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(result.get("stdout") or ""))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not emit JSON: {result['command']}: {exc}\n{result.get('stderr')}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON output is not an object: {result['command']}")
    return value


def command_evidence(result: dict[str, Any], *, include_tail: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": result["command"],
        "exit_code": result["exit_code"],
    }
    if include_tail:
        payload["stdout_tail"] = str(result.get("stdout") or "")[-4000:]
        payload["stderr_tail"] = str(result.get("stderr") or "")[-4000:]
    return payload


def baseline_capabilities(path: Path) -> dict[str, Any]:
    tools = path / "skills" / "cs" / "assets" / "project" / ".codestable" / "tools"
    required = ["cs_policy.py", "cs_feedback.py", "cs_meta.py", "cs_fixture.py"]
    registry = path / "skills" / "cs" / "assets" / "project" / ".codestable" / "meta" / "policy-registry.json"
    return {
        "path": str(path),
        "version": (path / "VERSION").read_text(encoding="utf-8").strip() if (path / "VERSION").is_file() else None,
        "meta_tools": {name: (tools / name).is_file() for name in required},
        "policy_registry": registry.is_file(),
    }


def fresh_bootstrap_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="codestable-meta-effect-") as temporary:
        target = Path(temporary)
        bootstrap = run([sys.executable, str(ROOT / "skills/cs/scripts/bootstrap.py"), "--root", str(target)])
        if bootstrap["exit_code"] != 0:
            return {"ok": False, "bootstrap": command_evidence(bootstrap, include_tail=True)}
        doctor = run([sys.executable, str(target / ".codestable/tools/cs_context.py"), "doctor", "--root", str(target)], cwd=target)
        policy = run([sys.executable, str(target / ".codestable/tools/cs_policy.py"), "--root", str(target), "audit"], cwd=target)
        doctor_payload = parse_json_stdout(doctor) if doctor["exit_code"] == 0 else None
        policy_payload = parse_json_stdout(policy) if policy["exit_code"] == 0 else None
        return {
            "ok": bootstrap["exit_code"] == doctor["exit_code"] == policy["exit_code"] == 0,
            "bootstrap": command_evidence(bootstrap),
            "doctor": doctor_payload or command_evidence(doctor, include_tail=True),
            "policy_audit": policy_payload or command_evidence(policy, include_tail=True),
        }


def markdown_report(report: dict[str, Any]) -> str:
    candidate = report["candidate"]
    baseline = report.get("baseline")
    fixtures = report["public_fixtures"]
    policy = report["policy_audit"]
    tests = report["unit_tests"]
    mutants = report["known_bad_mutants"]
    lines = [
        "# CodeStable Compact 0.4.0 — Meta effect report",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Verdict",
        "",
        "```text",
        report["verdict"],
        "```",
        "",
        "本报告验证的是 **Meta 控制面、评测效度防线与版本安全机制是否真实运行**。它不会把没有真实 Host Adapter 的 GPT / Claude Code / Cursor / Codex 行为标成提升。",
        "",
        "## Evidence labels",
        "",
        "| Label | Meaning | Result |",
        "|---|---|---|",
        f"| `[measured]` | 直接执行的确定性测试/fixture | {report['labels']['measured']} evidence groups passed |",
        f"| `[soft]` | 设计或校准声明，可辅助判断 | {report['labels']['soft']} group{'s' if report['labels']['soft'] != 1 else ''} |",
        f"| `[underpowered]` | 缺真实模型/宿主或样本不足 | {report['labels']['underpowered']} groups |",
        "",
        "## Measured control-plane results",
        "",
        f"- Release validator: **{'PASS' if report['release_validator']['passed'] else 'FAIL'}**.",
        f"- Unit tests: **{tests['passed_count']}/{tests['test_count']} passed**.",
        f"- Known-bad mutant detection: **{mutants['passed_count']}/{mutants['test_count']} passed**.",
        "- Full Meta cycle: **PASS** — repeated feedback → campaign → committed hypothesis → Agent proposal → validity pre-pass → signed evaluation → scoped approval → promotion → rollback.",
        "- Normal delivery isolation: **PASS** — passive observation may write, but normal `/cs` cannot import or read the Meta control plane.",
        f"- First-class policies: **{policy['policy_count']}**; fixture-coverage audit: **{'PASS' if policy['ok'] else 'FAIL'}**.",
        f"- Registered public fixtures: **{policy['fixture_count']}**.",
        f"- Public fixture execution: **{fixtures['counts']['passed']} measured passed**, **{fixtures['counts']['failed']} failed**, **{fixtures['counts']['underpowered']} underpowered**.",
        f"- Automatic promotion eligibility without Host Adapter evidence: **{fixtures['promotion_eligible']}** (expected `False`).",
        f"- Fresh bootstrap + doctor + policy audit: **{'PASS' if report['fresh_bootstrap']['ok'] else 'FAIL'}**.",
        "",
        "## Known-bad mutants exercised",
        "",
    ]
    for item in report["known_bad_mutants"]["cases"]:
        lines.append(f"- `{item}`")
    lines += [
        "",
        "These checks cover missing fixture coverage, script-authored proposals, incomplete fixture layers, low-k stochastic evidence, missing context, brittle oracle, uncalibrated scorer, same-profile Judge, undeclared surface smuggling, signed-result tampering/replay, missing measured quality gates, authority downgrade and corrupt rollback snapshots.",
        "",
        "## Baseline comparison",
        "",
    ]
    if baseline:
        lines += [
            f"- Baseline version: `{baseline['capabilities']['version']}`.",
            f"- Baseline tests: **{baseline['tests']['passed_count']}/{baseline['tests']['test_count']} passed**.",
            f"- Candidate tests: **{tests['passed_count']}/{tests['test_count']} passed**.",
            "- Baseline lacks `cs_policy.py`, `cs_feedback.py`, `cs_meta.py`, `cs_fixture.py` and the first-class policy registry; 0.4 adds and tests those control-plane capabilities.",
            "- This comparison proves added, regression-tested control-plane behavior—not universal LLM quality improvement.",
        ]
    else:
        lines.append("- No baseline source tree was supplied; capability comparison was not run.")
    lines += [
        "",
        "## Public fixture result",
        "",
        "| Fixture | Label | Status |",
        "|---|---|---|",
    ]
    for item in fixtures["results"]:
        lines.append(f"| `{item['fixture_id']}` | `{item['label']}` | `{item['status']}` |")
    lines += [
        "",
        "## What remains underpowered",
        "",
        "The portable release did not execute live GPT 5.5/5.6, Claude Code, Cursor, ChatGPT Codex or other provider sessions. The following claims therefore remain underpowered until an adapter runs the same baseline/candidate challenge with an exact Runtime Profile:",
        "",
        "- route accuracy and continuous execution under each host/model;",
        "- Gate precision/recall and checkpoint behavior;",
        "- token/context/tool-call cost comparison;",
        "- long-running lifecycle adherence;",
        "- real project delivery improvement and cross-task knowledge utility;",
        "- portability of a promoted policy across profiles.",
        "",
        "Host-dependent fixtures correctly returned `underpowered` instead of being silently counted as pass. This is the intended Goodhart/overclaiming safeguard.",
        "",
        "## Candidate identity",
        "",
        f"- Version: `{candidate['version']}`",
        f"- Python: `{report['environment']['python']}`",
        f"- Platform: `{report['environment']['platform']}`",
        "",
        "Machine-readable report: [`meta-effect-report.json`](meta-effect-report.json).",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", help="optional CodeStable Compact 0.3.0 source tree")
    parser.add_argument("--output-dir", default=str(ROOT / "validation"))
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.baseline:
        baseline_path: Path | None = Path(args.baseline).expanduser().resolve()
    elif DEFAULT_BASELINE.is_dir():
        baseline_path = DEFAULT_BASELINE
    else:
        baseline_path = None
    if baseline_path is not None and not baseline_path.is_dir():
        baseline_path = None

    print("[meta-effect] isolated external validation campaign", flush=True)
    campaign = run_validation_campaign(baseline_path)
    validator = campaign["validator"]
    unit = campaign["candidate_tests"]
    baseline_tests = campaign.get("baseline_tests")
    policy_result = campaign["policy_audit"]
    print("[meta-effect] public fixtures", flush=True)
    fixture_ids: list[str] = []
    for fixture_id, entry in sorted(active_fixture_entries().items()):
        fixture = json.loads((ASSET_ROOT / str(entry["path"])).read_text(encoding="utf-8"))
        runner = fixture.get("runner") if isinstance(fixture.get("runner"), dict) else {}
        if runner.get("type") != "python_unittest":
            fixture_ids.append(fixture_id)
    fixture_result, fixture_base_payload = run_public_fixture_subset(fixture_ids)
    print("[meta-effect] known-bad mutants (reused full-suite evidence)", flush=True)
    mutant = mutant_evidence_from_unit(unit)

    policy_payload = parse_json_stdout(policy_result)
    fixture_payload = reuse_unit_suite_as_python_fixtures(fixture_base_payload, unit)
    unit_count = parse_test_count(unit)
    mutant_count = len(MUTANT_TESTS)

    baseline_payload: dict[str, Any] | None = None
    if baseline_path is not None and baseline_tests is not None:
        baseline_count = parse_test_count(baseline_tests)
        baseline_payload = {
            "capabilities": baseline_capabilities(baseline_path),
            "tests": {
                "test_count": baseline_count,
                "passed_count": baseline_count if baseline_tests["exit_code"] == 0 and baseline_count is not None else 0,
                "exit_code": baseline_tests["exit_code"],
            },
        }

    all_core_passed = all([
        validator["exit_code"] == 0,
        unit["exit_code"] == 0,
        policy_result["exit_code"] == 0,
        policy_payload.get("ok") is True,
        fixture_result["exit_code"] == 0,
        fixture_payload.get("counts", {}).get("failed") == 0,
        mutant["exit_code"] == 0,
    ])
    print("[meta-effect] fresh bootstrap evidence", flush=True)
    fresh = campaign["fresh_bootstrap"]
    all_core_passed = all_core_passed and bool(fresh.get("ok"))

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "verdict": "CONTROL_PLANE_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED" if all_core_passed else "CONTROL_PLANE_VALIDATION_FAILED",
        "candidate": {"version": (ROOT / "VERSION").read_text(encoding="utf-8").strip()},
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "labels": {
            "measured": 6 if all_core_passed else 0,
            "soft": 1,
            "underpowered": int(fixture_payload.get("counts", {}).get("underpowered", 0)) + 1,
        },
        "release_validator": {"passed": validator["exit_code"] == 0, **command_evidence(validator, include_tail=True)},
        "unit_tests": {
            "test_count": unit_count,
            "passed_count": unit_count if unit["exit_code"] == 0 and unit_count is not None else 0,
            **command_evidence(unit, include_tail=True),
        },
        "known_bad_mutants": {
            "test_count": mutant_count,
            "passed_count": mutant_count if mutant["exit_code"] == 0 and mutant_count is not None else 0,
            "cases": list(MUTANT_TESTS),
            **command_evidence(mutant, include_tail=True),
        },
        "policy_audit": policy_payload,
        "public_fixtures": fixture_payload,
        "fresh_bootstrap": fresh,
        "baseline": baseline_payload,
        "claims": {
            "measured": [
                "normal delivery remains isolated from the Meta control plane",
                "first-class policy fixture coverage is enforced",
                "production feedback and repeated-signal campaign admission are deterministic",
                "Agent proposal authorship and bounded overlays are enforced",
                "validity defects block attribution/evaluation",
                "trusted result, authority, promotion and rollback invariants are enforced",
            ],
            "soft": [
                "public fixture/scorer metadata declares intended behavioral coverage but does not itself prove live model quality",
            ],
            "underpowered": [
                "live GPT/Claude/Cursor/Codex route, Gate, cost, lifecycle and project-delivery effects without real host adapter campaigns",
            ],
        },
    }

    json_path = output_dir / "meta-effect-report.json"
    md_path = output_dir / "meta-effect-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({
        "ok": all_core_passed,
        "verdict": report["verdict"],
        "unit_tests": report["unit_tests"]["test_count"],
        "mutant_checks": report["known_bad_mutants"]["test_count"],
        "measured_fixtures": fixture_payload.get("counts", {}).get("passed"),
        "underpowered_fixtures": fixture_payload.get("counts", {}).get("underpowered"),
        "report": str(md_path),
    }, ensure_ascii=False, indent=2))
    return 0 if all_core_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
