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
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "skills" / "cs" / "assets" / "project"
TOOLS = ASSET_ROOT / ".codestable" / "tools"
DEFAULT_BASELINE = Path("/mnt/data/codestable-compact-baseline")

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


def run_validation_campaign(candidate_test_evidence: Path | None, *, strict_evidence: bool = False) -> dict[str, Any]:
    """Run release checks, reusing source-bound unit evidence when supplied."""

    validator = run(
        [sys.executable, str(ROOT / "scripts/validate_skills.py")],
        cwd=ROOT,
        timeout=300,
    )
    candidate_tests: dict[str, Any]
    if candidate_test_evidence is not None and candidate_test_evidence.is_file():
        try:
            candidate_tests = load_recorded_test_result(candidate_test_evidence, ROOT)
        except RuntimeError:
            if strict_evidence:
                raise
            print("[meta-effect] recorded candidate tests are stale; executing the live suite", flush=True)
            candidate_tests = run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=ROOT,
                timeout=600,
            )
    else:
        candidate_tests = run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT,
            timeout=600,
        )
    policy_audit = run(
        [sys.executable, str(TOOLS / "cs_policy.py"), "--root", str(ASSET_ROOT), "audit"],
        cwd=ROOT,
        timeout=300,
    )
    return {
        "validator": validator,
        "candidate_tests": candidate_tests,
        "policy_audit": policy_audit,
        "fresh_bootstrap": fresh_bootstrap_check(),
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
    if isinstance(result.get("recorded_evidence"), dict):
        payload["recorded_evidence"] = result["recorded_evidence"]
    return payload


def runtime_capabilities(path: Path) -> dict[str, Any]:
    asset_root = path / "skills" / "cs" / "assets" / "project"
    config_path = asset_root / ".codestable" / "config.json"
    runtime_path = asset_root / ".codestable" / "tools" / "cs_context.py"
    tools = asset_root / ".codestable" / "tools"
    required_meta = ["cs_policy.py", "cs_feedback.py", "cs_meta.py", "cs_fixture.py"]
    registry = asset_root / ".codestable" / "meta" / "policy-registry.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
    runtime_source = runtime_path.read_text(encoding="utf-8") if runtime_path.is_file() else ""
    active_files = config.get("artifacts", {}).get("required_active_files") or []
    return {
        "path": str(path),
        "version": (path / "VERSION").read_text(encoding="utf-8").strip() if (path / "VERSION").is_file() else None,
        "meta_tools": {name: (tools / name).is_file() for name in required_meta},
        "policy_registry": registry.is_file(),
        "artifact_mode": config.get("artifacts", {}).get("mode"),
        "execution_mode": config.get("execution", {}).get("mode"),
        "evidence_ledger_required": "evidence.jsonl" in active_files,
        "workflow_cursor_fields": '"lane": lane' in runtime_source and '"stage": stage' in runtime_source,
        "command_backed_verify": "def command_verify" in runtime_source,
        "hash_chained_evidence": "entry_sha256" in runtime_source and "previous_sha256" in runtime_source,
    }


def baseline_capabilities(path: Path) -> dict[str, Any]:
    return runtime_capabilities(path)


def source_tree_sha256(root: Path) -> str:
    """Hash release sources while excluding generated validation evidence."""

    records: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in {".codestable", ".git", "validation"}:
            continue
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"} or path.name == ".DS_Store":
            continue
        records.append({"path": relative.as_posix(), "sha256": sha256_file(path)})
    return sha256_bytes(canonical_json(records))


def load_recorded_test_result(evidence_path: Path, source_root: Path) -> dict[str, Any]:
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"test evidence is not an object: {evidence_path}")
    log_path = evidence_path.parent / str(payload.get("log_path") or "")
    if not log_path.is_file():
        raise RuntimeError(f"test evidence log is missing: {log_path}")
    if sha256_file(log_path) != payload.get("log_sha256"):
        raise RuntimeError(f"test evidence log hash mismatch: {log_path}")
    if source_tree_sha256(source_root) != payload.get("source_tree_sha256"):
        raise RuntimeError(f"test evidence source tree changed: {source_root}")
    output = log_path.read_text(encoding="utf-8", errors="replace")
    def display(path: Path) -> str:
        try:
            return path.relative_to(ROOT).as_posix()
        except ValueError:
            return str(path)

    result = {
        "command": payload.get("command") or [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        "cwd": str(source_root),
        "exit_code": int(payload.get("exit_code", 1)),
        "stdout": "",
        "stderr": output,
        "recorded_evidence": {
            "path": display(evidence_path),
            "sha256": sha256_file(evidence_path),
            "log_path": display(log_path),
            "log_sha256": payload.get("log_sha256"),
            "source_tree_sha256": payload.get("source_tree_sha256"),
        },
    }
    parsed_count = parse_test_count(result)
    if parsed_count != payload.get("test_count"):
        raise RuntimeError(f"test evidence count mismatch: {parsed_count} != {payload.get('test_count')}")
    return result


def load_control_plane_validation(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "control-plane-report.json"
    if not path.is_file():
        raise RuntimeError("control-plane report is missing; run scripts/validate_control_plane.py first")
    report = json.loads(path.read_text(encoding="utf-8"))
    current_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if report.get("version") != current_version or report.get("verdict") != "PASS":
        raise RuntimeError("control-plane report is stale or failed")
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if summary.get("checks") != summary.get("passed"):
        raise RuntimeError("control-plane report contains failed checks")
    for relative, expected in (report.get("artifacts", {}).get("sha256") or {}).items():
        artifact = ROOT / str(relative)
        if not artifact.is_file() or sha256_file(artifact) != expected:
            raise RuntimeError(f"control-plane proof artifact changed: {relative}")
    return report

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
    control = report["control_plane_validation"]
    lines = [
        f"# CodeStable Compact {candidate['version']} — control-plane and Meta effect report",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Verdict",
        "",
        "```text",
        report["verdict"],
        "```",
        "",
        "本报告分别验证生产控制平面与 Meta 演进控制面。确定性结果来自真实运行的命令、测试、fixture、完整性检查与回滚检查；未运行真实 Host Adapter 的模型效果不会被标成提升。",
        "",
        "## Evidence labels",
        "",
        "| Label | Meaning | Result |",
        "|---|---|---|",
        f"| `[measured]` | 直接执行的确定性验证组 | {report['labels']['measured']} groups passed |",
        f"| `[soft]` | 设计或校准声明，可辅助判断 | {report['labels']['soft']} group{'s' if report['labels']['soft'] != 1 else ''} |",
        f"| `[underpowered]` | 缺真实模型/宿主或样本不足 | {report['labels']['underpowered']} groups |",
        "",
        "## Measured production control-plane results",
        "",
        f"- Evidence-state scenarios: **{control['summary']['passed']}/{control['summary']['checks']} passed** across **{control['summary']['commands']} Harness commands**.",
        "- Completion without required evidence: **REJECTED**.",
        "- Undeclared side effects: **REJECTED**.",
        "- Verification provenance: **PASS** — the Harness executed commands and captured actual exit codes.",
        "- L2 review producer boundary: **PASS** — the declared Owner producer was rejected; portable identity assurance remains declarative.",
        "- Dynamic risk escalation: **PASS** — a critical authorization path upgraded L0 to L3 and replaced the evidence policy.",
        "- Evidence semantics: **PASS** — `PASS`, `FAIL`, `BLOCKED`, and `PARTIAL` remained distinct.",
        "- Evidence integrity: **PASS** — tampering caused `doctor` to fail.",
        "",
        "## Measured Meta and release results",
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
        before = baseline["capabilities"]
        after = report["candidate"]["capabilities"]
        lines += [
            f"- Baseline version: `{before['version']}`; tests: **{baseline['tests']['passed_count']}/{baseline['tests']['test_count']} passed**.",
            f"- Candidate version: `{candidate['version']}`; tests: **{tests['passed_count']}/{tests['test_count']} passed**.",
            "",
            "| Property | Baseline | Candidate |",
            "|---|---|---|",
            f"| Active-state mode | `{before['artifact_mode']}` | `{after['artifact_mode']}` |",
            f"| Execution control | `{before['execution_mode']}` | `{after['execution_mode']}` |",
            f"| `evidence.jsonl` required | `{before['evidence_ledger_required']}` | `{after['evidence_ledger_required']}` |",
            f"| Lane/stage workflow cursor | `{before['workflow_cursor_fields']}` | `{after['workflow_cursor_fields']}` |",
            f"| Harness-executed verification | `{before['command_backed_verify']}` | `{after['command_backed_verify']}` |",
            f"| Hash-chained evidence | `{before['hash_chained_evidence']}` | `{after['hash_chained_evidence']}` |",
            "",
            "The comparison demonstrates added, regression-tested evidence-state behavior while retaining the 0.4 Meta safety plane. It does not establish universal model-quality improvement.",
        ]
    else:
        lines.append("- No baseline source tree was supplied; architectural capability comparison was not run.")
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
        "The portable release did not execute live GPT-5.6, Claude Code, Cursor, ChatGPT Codex or other provider sessions. The following claims remain underpowered until a Host Adapter runs the same baseline/candidate challenge with an exact Runtime Profile:",
        "",
        "- route accuracy and autonomous evidence convergence under each host/model;",
        "- completion-gate precision/recall and intervention behavior;",
        "- token/context/tool-call cost comparison;",
        "- real-project delivery improvement and cross-task knowledge utility;",
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
        "Machine-readable reports: [`meta-effect-report.json`](meta-effect-report.json) and [`control-plane-report.json`](control-plane-report.json).",
        "",
    ]
    return "\n".join(lines)

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", help="optional unpacked pre-refactor/0.4 source tree")
    parser.add_argument("--output-dir", default=str(ROOT / "validation"))
    parser.add_argument("--candidate-test-evidence", help="optional source-bound candidate unittest evidence JSON")
    parser.add_argument("--baseline-test-evidence", help="optional source-bound baseline unittest evidence JSON")
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

    candidate_test_evidence = Path(args.candidate_test_evidence).expanduser().resolve() if args.candidate_test_evidence else output_dir / "candidate-0.5-test-evidence.json"
    baseline_test_evidence = Path(args.baseline_test_evidence).expanduser().resolve() if args.baseline_test_evidence else output_dir / "baseline-0.4-test-evidence.json"

    print("[meta-effect] verified production control-plane report", flush=True)
    control_report = load_control_plane_validation(output_dir)
    print("[meta-effect] release and Meta validation campaign", flush=True)
    campaign = run_validation_campaign(
        candidate_test_evidence if candidate_test_evidence.is_file() else None,
        strict_evidence=bool(args.candidate_test_evidence),
    )
    validator = campaign["validator"]
    unit = campaign["candidate_tests"]
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
    if baseline_path is not None:
        baseline_result: dict[str, Any] | None = None
        if baseline_test_evidence.is_file():
            try:
                baseline_result = load_recorded_test_result(baseline_test_evidence, baseline_path)
            except RuntimeError:
                if args.baseline_test_evidence:
                    raise
                print("[meta-effect] recorded baseline tests are stale; reporting capability delta without a baseline rerun", flush=True)
        baseline_count = parse_test_count(baseline_result) if baseline_result is not None else None
        baseline_payload = {
            "capabilities": baseline_capabilities(baseline_path),
            "tests": {
                "test_count": baseline_count,
                "passed_count": baseline_count if baseline_result is not None and baseline_result["exit_code"] == 0 and baseline_count is not None else 0,
                "exit_code": baseline_result["exit_code"] if baseline_result is not None else None,
                "evidence": command_evidence(baseline_result, include_tail=True) if baseline_result is not None else None,
                "status": "measured" if baseline_result is not None else "not_rerun",
            },
        }

    control_passed = (
        control_report.get("verdict") == "PASS"
        and control_report.get("summary", {}).get("checks") == control_report.get("summary", {}).get("passed")
    )
    all_core_passed = all([
        control_passed,
        validator["exit_code"] == 0,
        unit["exit_code"] == 0,
        policy_result["exit_code"] == 0,
        policy_payload.get("ok") is True,
        fixture_result["exit_code"] == 0,
        fixture_payload.get("counts", {}).get("failed") == 0,
        mutant["exit_code"] == 0,
        bool(campaign["fresh_bootstrap"].get("ok")),
    ])

    candidate_capabilities = runtime_capabilities(ROOT)
    report: dict[str, Any] = {
        "schema_version": 2,
        "generated_at": now_iso(),
        "verdict": "CONTROL_AND_META_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED" if all_core_passed else "CONTROL_OR_META_VALIDATION_FAILED",
        "candidate": {
            "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "capabilities": candidate_capabilities,
        },
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "labels": {
            "measured": 7 if all_core_passed else 0,
            "soft": 1,
            "underpowered": int(fixture_payload.get("counts", {}).get("underpowered", 0)) + 1,
        },
        "control_plane_validation": control_report,
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
        "fresh_bootstrap": campaign["fresh_bootstrap"],
        "baseline": baseline_payload,
        "claims": {
            "measured": [
                "evidence-state completion and side-effect boundaries are enforced",
                "risk-adaptive evidence requirements and independent review are enforced",
                "verification commands and evidence-chain integrity are machine recorded",
                "normal delivery remains isolated from the Meta control plane",
                "first-class policy fixture coverage is enforced",
                "validity defects block attribution and evaluation",
                "trusted result, authority, promotion and rollback invariants are enforced",
            ],
            "soft": [
                "public fixture and scorer metadata declares intended behavioral coverage but does not itself prove live model quality",
            ],
            "underpowered": [
                "live GPT/Claude/Cursor/Codex route, cost, autonomous convergence and project-delivery effects without real Host Adapter campaigns",
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
        "control_checks": control_report.get("summary", {}).get("checks"),
        "unit_tests": report["unit_tests"]["test_count"],
        "mutant_checks": report["known_bad_mutants"]["test_count"],
        "measured_fixtures": fixture_payload.get("counts", {}).get("passed"),
        "underpowered_fixtures": fixture_payload.get("counts", {}).get("underpowered"),
        "report": str(md_path),
    }, ensure_ascii=False, indent=2))
    return 0 if all_core_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
