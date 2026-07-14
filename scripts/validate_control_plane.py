#!/usr/bin/env python3
"""Run isolated evidence-state control-plane scenarios and emit a proof report."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills" / "cs" / "assets" / "project" / ".codestable" / "tools" / "cs_context.py"
DEFAULT_BASELINE = Path("/mnt/data/codestable-compact-baseline")


def load_runtime() -> Any:
    spec = importlib.util.spec_from_file_location("codestable_control_validation_runtime", RUNTIME)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runtime: {RUNTIME}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNTIME_MODULE = load_runtime()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: Sequence[str], *, cwd: Path, timeout: int = 60) -> dict[str, Any]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        completed = subprocess.run(
            list(command), cwd=cwd, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
        return {
            "command": list(command),
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": list(command),
            "cwd": str(cwd),
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timeout": True,
        }


def parse_json(result: dict[str, Any], *, stream: str = "stdout") -> dict[str, Any]:
    raw = str(result.get(stream) or "")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not emit JSON on {stream}: {result['command']}: {exc}: {raw[-1000:]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON output is not an object: {result['command']}")
    return payload


class Scenario:
    def __init__(self, project: Path) -> None:
        self.project = project
        self.commands: list[dict[str, Any]] = []
        self.checks: list[dict[str, Any]] = []

    def call(self, *args: str, expected: int = 0, timeout: int = 60) -> dict[str, Any]:
        del timeout  # command_verify carries its own bounded timeout policy.
        print(f"[control-plane] {args[0]} {' '.join(args[1:4])}", file=sys.stderr, flush=True)
        parsed = RUNTIME_MODULE.build_parser().parse_args(["--root", str(self.project), *args])
        if not getattr(parsed, "root", None):
            parsed.root = getattr(parsed, "global_root", None)
        try:
            payload = parsed.func(parsed)
            code = 1 if parsed.command == "doctor" and not payload.get("ok", False) else 0
        except RUNTIME_MODULE.RuntimeErrorWithHint as exc:
            payload = {"ok": False, "error": str(exc)}
            code = 2
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.commands.append({
            "command": [sys.executable, str(RUNTIME), "--root", str(self.project), *args],
            "exit_code": code,
            "result_tail": rendered[-1600:],
        })
        if code != expected:
            raise RuntimeError(
                f"unexpected exit code {code} != {expected}: {[str(RUNTIME), *args]}\nresult={rendered}"
            )
        return payload

    def check(self, name: str, condition: bool, detail: Any) -> None:
        self.checks.append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise RuntimeError(f"check failed: {name}: {detail}")


def create_file(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def initialize_git(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=CodeStable Validator", "-c", "user.email=validator@example.com",
            "commit", "-qm", "runtime baseline",
        ],
        cwd=root,
        check=True,
    )


def locate_work(project: Path, work_id: str) -> Path:
    active = project / ".codestable" / "work" / "active" / work_id
    if active.is_dir():
        return active
    matches = list((project / ".codestable" / "work" / "archive").glob(f"*/{work_id}"))
    if len(matches) != 1:
        raise FileNotFoundError(f"cannot locate work {work_id}: {matches}")
    return matches[0]


def evidence_entries(project: Path, work_id: str) -> list[dict[str, Any]]:
    path = locate_work(project, work_id) / "evidence.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def chain_valid(entries: list[dict[str, Any]]) -> bool:
    previous = None
    for index, entry in enumerate(entries, start=1):
        if entry.get("sequence") != index or entry.get("previous_sha256") != previous:
            return False
        previous = entry.get("entry_sha256")
    return bool(entries)


def copy_work(project: Path, work_id: str, destination: Path) -> None:
    source = locate_work(project, work_id)
    bucket = "archive" if "archive" in source.parts else "active"
    target = destination / bucket / work_id
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)


def run_scenarios(output_dir: Path, baseline: Path | None) -> dict[str, Any]:
    artifact_root = output_dir / "control-plane-artifacts"
    if artifact_root.exists():
        shutil.rmtree(artifact_root)
    artifact_root.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="codestable-control-plane-") as temporary:
        project = Path(temporary) / "project"
        project.mkdir()
        scenario = Scenario(project)
        init = scenario.call("init")
        scenario.check("runtime initialized", ".codestable/config.json" in (init.get("created") or []) or not init.get("created"), init)
        initialize_git(project)

        # L0: completion must be denied until real command evidence exists.
        l0 = scenario.call("new", "model", "Correct compact documentation", "--risk", "0", "--allow-path", "docs/control.md")
        l0_id = str(l0["id"])
        scenario.call("contract", "--work", l0_id, "--objective", "Correct one canonical statement", "--acceptance", "The canonical statement is formatted and diff-clean")
        denied = scenario.call("complete", "--work", l0_id, "--result", "done", expected=2)
        scenario.check("L0 completion denied without evidence", "completion denied" in str(denied.get("error")), denied)
        out_of_scope = scenario.call(
            "ledger-add", "--work", l0_id, "change", "Attempt an undeclared code change", "--path", "src/escape.py", expected=2,
        )
        scenario.check("side-effect boundary rejects undeclared path", "escapes side-effect boundary" in str(out_of_scope.get("error")), out_of_scope)
        create_file(project, "docs/control.md", "evidence-state control\n")
        scenario.call("ledger-add", "--work", l0_id, "change", "Corrected canonical control statement", "--path", "docs/control.md")
        owner_artifact = f".codestable/work/active/{l0_id}/owner-assertion.txt"
        create_file(project, owner_artifact, "PASS\n")
        scenario.call(
            "record", "--work", l0_id, "--type", "diff_check", "--status", "PASS",
            "--producer", "owner", "--artifact", owner_artifact, "--verdict", "PASS",
        )
        scenario.call(
            "record", "--work", l0_id, "--type", "format_check", "--status", "PASS",
            "--producer", "owner", "--artifact", owner_artifact, "--verdict", "PASS",
        )
        wrong_source = scenario.call("complete", "--work", l0_id, "--result", "done", expected=2)
        scenario.check(
            "artifact records cannot impersonate command evidence",
            "missing PASS evidence: diff_check" in str(wrong_source.get("error")),
            wrong_source,
        )
        diff = scenario.call("verify", "--work", l0_id, "--type", "diff_check", "--", sys.executable, "-c", "print('diff clean')")
        fmt = scenario.call("verify", "--work", l0_id, "--type", "format_check", "--", sys.executable, "-c", "print('format clean')")
        scenario.check("Harness recorded command exit codes", diff["evidence"].get("exit_code") == 0 and fmt["evidence"].get("exit_code") == 0, [diff["evidence"], fmt["evidence"]])
        hidden = create_file(project, "docs/escape.md", "undeclared\n")
        hidden_write = scenario.call("complete", "--work", l0_id, "--result", "done", expected=2)
        scenario.check(
            "unregistered Git-visible write blocks completion",
            "not registered" in str(hidden_write.get("error")) and "escape the side-effect boundary" in str(hidden_write.get("error")),
            hidden_write,
        )
        hidden.unlink()
        completed_l0 = scenario.call("complete", "--work", l0_id, "--result", "done")
        scenario.check("L0 completed after exact evidence", completed_l0["completion"].get("status") == "COMPLETED", completed_l0)
        l0_evidence_path = locate_work(project, l0_id) / "evidence.jsonl"
        original_l0_evidence = l0_evidence_path.read_text(encoding="utf-8")
        l0_evidence_path.write_text(
            original_l0_evidence.replace('"status": "PASS"', '"status": "FAIL"', 1),
            encoding="utf-8",
        )
        invalid_archive = scenario.call("archive", "--work", l0_id, "--summary", "invalid", expected=2)
        scenario.check(
            "completed tampered evidence cannot be archived",
            "integrity" in str(invalid_archive.get("error")),
            invalid_archive,
        )
        l0_evidence_path.write_text(original_l0_evidence, encoding="utf-8")
        archived_l0 = scenario.call("archive", "--work", l0_id, "--summary", "L0 evidence-gated completion")
        scenario.check("completed work archived", "/archive/" in archived_l0["archived"]["path"], archived_l0)
        l0_entries = evidence_entries(project, l0_id)
        scenario.check("L0 evidence chain valid", chain_valid(l0_entries), {"entries": len(l0_entries)})
        copy_work(project, l0_id, artifact_root / "l0")

        # L2: proposal, integration evidence, independent reviewer and derived proof.
        l2 = scenario.call(
            "new", "feature", "Converge cross-module state", "--risk", "2", "--owner", "owner-a",
            "--allow-path", "src/**", "--allow-path", "tests/**", "--allow-path", "review/**",
        )
        l2_id = str(l2["id"])
        scenario.call(
            "contract", "--work", l2_id,
            "--objective", "Use one canonical cross-module state path",
            "--acceptance", "Integration behavior uses the canonical path",
            "--invariant", "Serialized values remain compatible",
            "--non-goal", "No generic framework",
        )
        scenario.call("ledger-add", "--work", l2_id, "fact", "The handler and serializer currently duplicate state conversion", "--source", "src/handler.py")
        scenario.call(
            "proposal", "--work", l2_id,
            "--summary", "Route both modules through one canonical conversion",
            "--rationale", "Removes duplicate behavior while preserving the contract",
            "--non-change", "Stored representation remains unchanged",
            "--evidence-required", "integration and independent challenge",
        )
        create_file(project, "src/service.py", "def canonical(value):\n    return value\n")
        create_file(project, "tests/test_service.py", "assert True\n")
        scenario.call(
            "ledger-add", "--work", l2_id, "change", "Unified state conversion and integration coverage",
            "--path", "src/service.py", "--path", "tests/test_service.py", "--rollback", "restore previous files",
        )
        audit = scenario.call("snapshot", "--work", l2_id, "--type", "audit_ledger")
        proposal = scenario.call("snapshot", "--work", l2_id, "--type", "proposal")
        integration = scenario.call("verify", "--work", l2_id, "--type", "integration_test", "--", sys.executable, "-c", "print('integration pass')")
        scenario.check("L2 state snapshots and integration passed", all(item["evidence"]["status"] == "PASS" for item in (audit, proposal, integration)), [audit, proposal, integration])
        create_file(project, "review/l2.md", "PASS: no missed caller, dual path or compatibility blocker.\n")
        self_review = scenario.call(
            "record", "--work", l2_id, "--type", "independent_review", "--status", "PASS",
            "--producer", "owner-a", "--artifact", "review/l2.md", expected=2,
        )
        scenario.check("declared Owner producer cannot supply independent review", "must differ" in str(self_review.get("error")), self_review)
        review = scenario.call(
            "record", "--work", l2_id, "--type", "independent_review", "--status", "PASS",
            "--producer", "reviewer-b", "--artifact", "review/l2.md", "--verdict", "PASS",
        )
        proof = scenario.call("proof", "--work", l2_id, "--summary", "Machine-assembled L2 proof")
        scenario.check(
            "L2 review has a declared distinct producer and proof is derived",
            review["evidence"]["producer"] == "reviewer-b"
            and review["evidence"]["metadata"].get("identity_assurance") == "declarative"
            and proof["evidence"]["source"] == "proof_assembly",
            [review, proof],
        )
        completed_l2 = scenario.call("complete", "--work", l2_id, "--result", "done")
        shown_l2 = scenario.call("show", "--work", l2_id)
        scenario.check("completed verdict survives reload", completed_l2["completion"]["status"] == shown_l2["state"]["completion"]["status"] == "COMPLETED", shown_l2)
        l2_entries = evidence_entries(project, l2_id)
        scenario.check("L2 evidence chain valid", chain_valid(l2_entries), {"entries": len(l2_entries)})
        copy_work(project, l2_id, artifact_root / "l2")

        # L3: actual critical path raises risk and replaces completion requirements.
        l3 = scenario.call(
            "new", "issue", "Protect authorization state", "--risk", "0", "--owner", "owner-critical",
            "--allow-path", "src/**", "--allow-path", "tests/**", "--allow-path", "review/**", "--allow-path", "rollback/**",
        )
        l3_id = str(l3["id"])
        scenario.call(
            "contract", "--work", l3_id,
            "--objective", "Correct authorization state without widening access",
            "--acceptance", "Unauthorized requests remain denied and authorized requests pass",
            "--invariant", "Default deny remains authoritative",
            "--non-goal", "No permission model redesign",
        )
        scenario.call(
            "boundary", "--work", l3_id, "--category", "authorization", "--authorization", "security-owner",
            "--rollback-required",
        )
        scenario.call("ledger-add", "--work", l3_id, "fact", "Authorization is decided in src/auth_policy.py", "--source", "src/auth_policy.py")
        scenario.call(
            "proposal", "--work", l3_id,
            "--summary", "Correct the default-deny transition in one policy function",
            "--rationale", "The observed divergence begins at this transition",
            "--non-change", "Role and token schemas remain unchanged",
            "--evidence-required", "live authorization scenarios and rollback",
        )
        create_file(project, "src/auth_policy.py", "def allowed(subject):\n    return bool(subject)\n")
        change_l3 = scenario.call(
            "ledger-add", "--work", l3_id, "change", "Corrected authorization transition",
            "--path", "src/auth_policy.py", "--rollback", "restore the previous policy file",
        )
        l3_state_after_change = scenario.call("show", "--work", l3_id)["state"]
        required_l3 = [item["type"] for item in l3_state_after_change["evidence"]["required"]]
        expected_l3 = ["full_audit", "invariant_contract", "live_validation", "rollback_proof", "independent_review", "regression_fixture"]
        scenario.check("critical executable path escalates L0 to L3", change_l3["risk"]["level"] == 3 and required_l3 == expected_l3, {"risk": change_l3["risk"], "required": required_l3})
        full_audit = scenario.call("snapshot", "--work", l3_id, "--type", "full_audit")
        invariant = scenario.call("snapshot", "--work", l3_id, "--type", "invariant_contract")
        live = scenario.call("verify", "--work", l3_id, "--type", "live_validation", "--", sys.executable, "-c", "print('authorized=pass unauthorized=deny')")
        create_file(project, "rollback/l3.md", "PASS: restored previous policy in isolated copy and reran deny scenario.\n")
        rollback = scenario.call(
            "record", "--work", l3_id, "--type", "rollback_proof", "--status", "PASS",
            "--producer", "harness", "--artifact", "rollback/l3.md", "--verdict", "PASS",
        )
        create_file(project, "review/l3.md", "PASS: challenged permission widening, failure ordering and rollback.\n")
        review_l3 = scenario.call(
            "record", "--work", l3_id, "--type", "independent_review", "--status", "PASS",
            "--producer", "security-reviewer", "--artifact", "review/l3.md", "--verdict", "PASS",
        )
        regression = scenario.call("verify", "--work", l3_id, "--type", "regression_fixture", "--", sys.executable, "-c", "print('fixture catches permission widening')")
        scenario.check("all L3 evidence sources passed", all(item["evidence"]["status"] == "PASS" for item in (full_audit, invariant, live, rollback, review_l3, regression)), [full_audit, invariant, live, rollback, review_l3, regression])
        completed_l3 = scenario.call("complete", "--work", l3_id, "--result", "done")
        scenario.check("L3 completed only after full policy", completed_l3["completion"]["status"] == "COMPLETED", completed_l3)
        copy_work(project, l3_id, artifact_root / "l3")

        risk_scan = scenario.call(
            "new", "issue", "Expand untracked critical directory", "--risk", "0", "--allow-path", "src/**",
        )
        risk_scan_id = str(risk_scan["id"])
        create_file(project, "src/newpkg/auth.py", "ALLOW = True\n")
        expanded_change = scenario.call(
            "ledger-add", "--work", risk_scan_id, "change", "Register an untracked directory",
            "--path", "src/newpkg", "--rollback", "remove the new package",
        )
        scenario.check(
            "untracked critical directory expands to executable files and escalates risk",
            expanded_change["risk"]["level"] == 3
            and expanded_change["entry"]["paths"] == ["src/newpkg/auth.py"],
            expanded_change,
        )

        # Evidence statuses remain semantically distinct.
        statuses = scenario.call("new", "issue", "Classify verifier outcomes", "--risk", "1", "--no-writes")
        status_id = str(statuses["id"])
        passing = scenario.call("verify", "--work", status_id, "--type", "targeted_test", "--", sys.executable, "-c", "print('pass')")
        failing = scenario.call("verify", "--work", status_id, "--type", "diagnostic_test", "--", sys.executable, "-c", "raise SystemExit(7)")
        blocked = scenario.call("verify", "--work", status_id, "--type", "environment_probe", "--", "codestable-command-that-does-not-exist")
        create_file(project, "review/partial.md", "Only one of two external scenarios was available.\n")
        partial = scenario.call(
            "record", "--work", status_id, "--type", "external_scenario", "--status", "PARTIAL",
            "--producer", "external-runner", "--artifact", "review/partial.md", "--verdict", "PARTIAL",
        )
        observed_statuses = [passing["evidence"]["status"], failing["evidence"]["status"], blocked["evidence"]["status"], partial["evidence"]["status"]]
        scenario.check("PASS/FAIL/BLOCKED/PARTIAL remain distinct", observed_statuses == ["PASS", "FAIL", "BLOCKED", "PARTIAL"], observed_statuses)
        scenario.check("blocked command has no fabricated exit code", blocked["evidence"].get("exit_code") is None, blocked["evidence"])
        copy_work(project, status_id, artifact_root / "statuses")

        # Tampering invalidates doctor and cannot be mistaken for a business failure.
        tamper = scenario.call("new", "issue", "Detect evidence tampering", "--risk", "1", "--no-writes")
        tamper_id = str(tamper["id"])
        scenario.call("verify", "--work", tamper_id, "--type", "targeted_test", "--", sys.executable, "-c", "print('before tamper')")
        tamper_path = project / ".codestable" / "work" / "active" / tamper_id / "evidence.jsonl"
        original = tamper_path.read_text(encoding="utf-8")
        tamper_path.write_text(original.replace('"status": "PASS"', '"status": "FAIL"', 1), encoding="utf-8")
        doctor = scenario.call("doctor", expected=1)
        messages = [str(item.get("message")) for item in doctor.get("findings", [])]
        scenario.check("evidence tampering detected by doctor", doctor.get("ok") is False and any("evidence integrity" in item for item in messages), doctor)
        copy_work(project, tamper_id, artifact_root / "tamper")

        baseline_delta: dict[str, Any] | None = None
        if baseline and baseline.is_dir():
            baseline_config_path = baseline / "skills/cs/assets/project/.codestable/config.json"
            baseline_runtime_path = baseline / "skills/cs/assets/project/.codestable/tools/cs_context.py"
            baseline_config = json.loads(baseline_config_path.read_text(encoding="utf-8"))
            baseline_source = baseline_runtime_path.read_text(encoding="utf-8")
            candidate_config = json.loads((project / ".codestable/config.json").read_text(encoding="utf-8"))
            baseline_delta = {
                "baseline_path": str(baseline),
                "baseline_version": (baseline / "VERSION").read_text(encoding="utf-8").strip() if (baseline / "VERSION").is_file() else None,
                "baseline": {
                    "artifact_mode": baseline_config.get("artifacts", {}).get("mode"),
                    "active_files": baseline_config.get("artifacts", {}).get("required_active_files"),
                    "execution_mode": baseline_config.get("execution", {}).get("mode"),
                    "workflow_cursor_fields": all(token in baseline_source for token in ('"lane"', '"stage"')),
                    "command_backed_verify": "def command_verify" in baseline_source,
                    "hash_chained_evidence": "entry_sha256" in baseline_source and "previous_sha256" in baseline_source,
                },
                "candidate": {
                    "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
                    "artifact_mode": candidate_config.get("artifacts", {}).get("mode"),
                    "active_files": candidate_config.get("artifacts", {}).get("required_active_files"),
                    "execution_mode": candidate_config.get("execution", {}).get("mode"),
                    "workflow_cursor_fields": False,
                    "command_backed_verify": True,
                    "hash_chained_evidence": True,
                },
            }

        all_checks = scenario.checks
        report = {
            "schema_version": 1,
            "generated_at": now_iso(),
            "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "verdict": "PASS" if all(item["passed"] for item in all_checks) else "FAIL",
            "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
            "summary": {
                "checks": len(all_checks),
                "passed": sum(1 for item in all_checks if item["passed"]),
                "commands": len(scenario.commands),
                "completed_tasks": 3,
                "evidence_statuses": ["PASS", "FAIL", "BLOCKED", "PARTIAL"],
            },
            "checks": all_checks,
            "baseline_delta": baseline_delta,
            "artifacts": {
                "root": str(artifact_root.relative_to(ROOT)),
                "sha256": {
                    str(path.relative_to(ROOT)): sha256_file(path)
                    for path in sorted(artifact_root.rglob("*")) if path.is_file()
                },
            },
            "command_evidence": scenario.commands,
        }
        return report


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# CodeStable Compact control-plane validation",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Version: `{report['version']}`",
        "",
        "## Verdict",
        "",
        "```text",
        report["verdict"],
        "```",
        "",
        f"Executed **{report['summary']['commands']}** Harness commands and passed **{report['summary']['passed']}/{report['summary']['checks']}** assertions across L0, L2, L3, provenance, side-effect, status-classification and tamper scenarios.",
        "",
        "## Measured checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for item in report["checks"]:
        lines.append(f"| {item['name']} | {'PASS' if item['passed'] else 'FAIL'} |")
    delta = report.get("baseline_delta")
    if delta:
        baseline = delta["baseline"]
        candidate = delta["candidate"]
        lines += [
            "",
            "## Architectural effect against the unpacked baseline",
            "",
            f"Baseline: `{delta['baseline_version']}` at `{delta['baseline_path']}`.",
            "",
            "| Property | Baseline | Candidate |",
            "|---|---|---|",
            f"| Active-state mode | `{baseline['artifact_mode']}` | `{candidate['artifact_mode']}` |",
            f"| Execution control | `{baseline['execution_mode']}` | `{candidate['execution_mode']}` |",
            f"| `evidence.jsonl` required | `{('evidence.jsonl' in (baseline['active_files'] or []))}` | `{('evidence.jsonl' in (candidate['active_files'] or []))}` |",
            f"| Lane/stage workflow cursor | `{baseline['workflow_cursor_fields']}` | `{candidate['workflow_cursor_fields']}` |",
            f"| Harness executes verification commands | `{baseline['command_backed_verify']}` | `{candidate['command_backed_verify']}` |",
            f"| Hash-chained evidence | `{baseline['hash_chained_evidence']}` | `{candidate['hash_chained_evidence']}` |",
        ]
    lines += [
        "",
        "## What was actually demonstrated",
        "",
        "- `done` was rejected before required evidence and artifact records could not impersonate command evidence.",
        "- Unregistered Git-visible writes were detected and rejected by the side-effect boundary.",
        "- Real command exit codes were captured by the Harness.",
        "- The declared Owner producer was rejected for L2 review; a declaratively distinct artifact-backed producer plus machine proof was required.",
        "- A critical executable authorization path dynamically escalated L0 to L3 and replaced the evidence policy.",
        "- An untracked critical directory was expanded to its executable file before risk classification.",
        "- `PASS`, `FAIL`, `BLOCKED` and `PARTIAL` remained distinct.",
        "- Evidence-chain tampering caused `doctor` to fail with an integrity finding.",
        "- Completed state survived reload, while later evidence tampering blocked archive without erasing the historical verdict.",
        "",
        "## Proof artifacts",
        "",
        f"Preserved under `{report['artifacts']['root']}`. The JSON report records SHA-256 for every artifact.",
        "",
        "Machine-readable report: [`control-plane-report.json`](control-plane-report.json).",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT / "validation"))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="optional unpacked pre-refactor source tree")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = Path(args.baseline).expanduser().resolve() if args.baseline else None
    if baseline is not None and not baseline.is_dir():
        baseline = None
    try:
        report = run_scenarios(output_dir, baseline)
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "generated_at": now_iso(),
            "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "verdict": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
        }
        (output_dir / "control-plane-report.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "control-plane-report.md").write_text(f"# CodeStable Compact control-plane validation\n\n```text\nFAIL\n{failure['error']}\n```\n", encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1
    (output_dir / "control-plane-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "control-plane-report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "ok": report["verdict"] == "PASS",
        "checks": report["summary"]["checks"],
        "commands": report["summary"]["commands"],
        "report": str(output_dir / "control-plane-report.md"),
    }, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
