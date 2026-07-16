from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_ROOT = REPO / "skills" / "cs" / "assets" / "project"
ASSET_ROOT = Path(os.environ.get("CODESTABLE_TEST_ASSET_ROOT", DEFAULT_ASSET_ROOT)).resolve()
RUNTIME_PATH = ASSET_ROOT / ".codestable" / "tools" / "cs_context.py"
META_PATH = ASSET_ROOT / ".codestable" / "tools" / "cs_meta.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = load_module("codestable_compact_evidence_freshness_runtime", RUNTIME_PATH)


class EvidenceFreshnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        runtime.init_runtime(self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=CodeStable Test", "-c", "user.email=test@example.com",
                "commit", "-qm", "runtime baseline",
            ],
            cwd=self.root,
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def new_l3(self, slug: str, *, acceptance_scope: list[str] | None = None) -> str:
        payload = runtime.command_new(SimpleNamespace(
            root=str(self.root), kind="issue", title=f"Evidence freshness {slug}", slug=slug,
            risk=3, owner="owner-a",
            allow_path=["src/**", "tests/**", "review/**", "rollback/**"], no_writes=False,
        ))
        work_id = payload["id"]
        runtime.command_contract(SimpleNamespace(
            root=str(self.root), work=work_id,
            objective="Keep completion bound to the current deliverable",
            constraint=[], non_goal=[], invariant=["Existing behavior remains compatible"],
            acceptance=["The declared validation and review scopes pass"],
            acceptance_scope=acceptance_scope or [], replace=False,
        ))
        runtime.command_boundary(SimpleNamespace(
            root=str(self.root), work=work_id, allow_path=[], forbid_path=[], category=["code"],
            authorization=[], no_writes=False, writes=True, rollback_required=True,
            rollback_not_required=False, replace=False,
        ))
        fact = runtime.command_ledger_add(SimpleNamespace(
            root=str(self.root), work=work_id, kind="fact",
            text="The target behavior is directly exercised by the validation command",
            source="test", non_blocking=False, severity="medium", blocking=False,
            mitigation="", path=[], from_git=False, rollback="",
        ))
        self.assertEqual(fact["entry"]["status"], "confirmed")
        source = self.root / "src" / f"{slug}.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        runtime.command_ledger_add(SimpleNamespace(
            root=str(self.root), work=work_id, kind="change",
            text="Implement the registered source change", source="test",
            non_blocking=False, severity="medium", blocking=False, mitigation="",
            path=[str(source.relative_to(self.root))], from_git=False,
            rollback="restore the previous source file",
        ))
        runtime.command_proposal(SimpleNamespace(
            root=str(self.root), work=work_id, summary="Apply one bounded source change",
            rationale="The change is directly testable and reversible",
            non_change=["Do not alter unrelated behavior"],
            evidence_required=list(runtime.RISK_REQUIREMENTS[3]),
        ))
        return work_id

    def snapshot(self, work_id: str, evidence_type: str) -> dict:
        return runtime.command_snapshot(SimpleNamespace(
            root=str(self.root), work=work_id, type=evidence_type,
            summary=f"{evidence_type} current-state snapshot",
        ))["evidence"]

    def verify(self, work_id: str, evidence_type: str, *, scope: list[str] | None = None) -> dict:
        return runtime.command_verify(SimpleNamespace(
            root=str(self.root), work=work_id, type=evidence_type, cwd=".", timeout=10,
            artifact=[], scope=scope or [], summary=f"{evidence_type} verification",
            command=["--", sys.executable, "-c", "print('PASS')"],
        ))["evidence"]

    def record(self, work_id: str, evidence_type: str, relative: str, *, producer: str,
               scope: list[str] | None = None, content: dict | None = None) -> dict:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content or {"verdict": "PASS"}, sort_keys=True) + "\n", encoding="utf-8")
        return runtime.command_record(SimpleNamespace(
            root=str(self.root), work=work_id, type=evidence_type, status="PASS",
            producer=producer, artifact=[relative], summary=f"{evidence_type} artifact",
            verdict="PASS", scope=scope or [], reviewed_diff_sha256=None,
        ))["evidence"]

    def record_all_l3(self, work_id: str, *, live_scope: list[str] | None = None,
                      review_scope: list[str] | None = None, revision: int = 1) -> dict[str, dict]:
        result = {
            "full_audit": self.snapshot(work_id, "full_audit"),
            "invariant_contract": self.snapshot(work_id, "invariant_contract"),
            "live_validation": self.verify(work_id, "live_validation", scope=live_scope),
            "regression_fixture": self.verify(work_id, "regression_fixture"),
        }
        result["rollback_proof"] = self.record(
            work_id, "rollback_proof", "rollback/proof.json", producer="owner-a",
            content={"verdict": "PASS", "revision": revision},
        )
        result["independent_review"] = self.record(
            work_id, "independent_review", "review/verdict.json", producer="reviewer-b",
            scope=review_scope,
            content={"verdict": "PASS", "revision": revision, "challenge": "no blocker"},
        )
        return result

    def check(self, work_id: str) -> dict:
        payload = runtime.command_check(SimpleNamespace(root=str(self.root), work=work_id))
        completion = dict(payload["completion"])
        completion["required_evidence"] = payload["evidence"]["required"]
        return completion

    @staticmethod
    def requirement(completion: dict, evidence_type: str) -> dict:
        return next(item for item in completion["required_evidence"] if item["type"] == evidence_type)

    def test_registered_source_mutation_stales_prior_validation_review_and_rollback(self) -> None:
        work_id = self.new_l3("source-freshness")
        first = self.record_all_l3(work_id)
        eligible = self.check(work_id)
        self.assertTrue(eligible["eligible"], eligible)

        source = self.root / "src" / "source-freshness.py"
        source.write_text("VALUE = 2\n", encoding="utf-8")
        stale = self.check(work_id)
        self.assertFalse(stale["eligible"])
        stale_codes = {item["code"] for item in stale["missing"]}
        for evidence_type in ("live_validation", "regression_fixture", "rollback_proof", "independent_review"):
            self.assertEqual(self.requirement(stale, evidence_type)["status"], "stale")
            self.assertIn(f"evidence.{evidence_type}.stale", stale_codes)

        second = self.record_all_l3(work_id, revision=2)
        restored = self.check(work_id)
        self.assertTrue(restored["eligible"], restored)
        for evidence_type, entry in second.items():
            requirement = self.requirement(restored, evidence_type)
            self.assertEqual(requirement["status"], "satisfied")
            self.assertEqual(requirement["evidence_ids"], [entry["id"]])
            self.assertNotIn(first[evidence_type]["id"], requirement["evidence_ids"])

    def test_registered_change_set_mutation_stales_prior_evidence(self) -> None:
        work_id = self.create_l3_work("registered-change-freshness")
        self.prepare_l3_contract(work_id)
        self.record_all_l3(work_id)
        self.assertTrue(self.check(work_id)["eligible"])

        runtime.command_ledger(SimpleNamespace(
            root=str(self.root), work=work_id, category="changes",
            text="add a second registered deliverable", source="implementation",
            status="open", path=["src/second.py"], rollback="remove src/second.py",
            blocking=False,
        ))
        stale = self.check(work_id)
        self.assertFalse(stale["eligible"])
        review = self.requirement(stale, "independent_review")
        self.assertEqual(review["status"], "stale")
        reasons = review["stale_evidence"][-1]["reasons"]
        self.assertIn("registered_changes_sha256", {item["binding"] for item in reasons})

        self.record_all_l3(work_id)
        restored = self.check(work_id)
        self.assertTrue(restored["eligible"])
        self.assertEqual(self.requirement(restored, "independent_review")["evidence_ids"], ["ev-0010"])

    def test_external_artifact_mutation_stales_only_artifact_backed_evidence(self) -> None:
        work_id = self.create_l3_work("artifact-freshness")
        self.prepare_l3_contract(work_id)
        self.record_all_l3(work_id)
        self.assertTrue(self.check(work_id)["eligible"])

        review_path = self.root / "review" / "verdict.json"
        review_path.write_text('{"verdict":"PASS","revision":2}\n', encoding="utf-8")
        stale = self.check(work_id)
        self.assertFalse(stale["eligible"])
        review = self.requirement(stale, "independent_review")
        self.assertEqual(review["status"], "stale")
        reasons = review["stale_evidence"][-1]["reasons"]
        self.assertIn("artifact_set_sha256", {item["binding"] for item in reasons})
        self.assertEqual(self.requirement(stale, "live_validation")["status"], "satisfied")
        self.assertEqual(self.requirement(stale, "rollback_proof")["status"], "satisfied")

        runtime.command_record(SimpleNamespace(
            root=str(self.root), work=work_id, type="independent_review", status="PASS",
            producer="reviewer-b", source="artifact_record", summary="review refreshed",
            artifact=["review/verdict.json"], verdict="PASS", identity_assurance="declarative",
            reviewer="reviewer-b", scope=[], reviewed_diff_sha256=None,
        ))
        restored = self.check(work_id)
        self.assertTrue(restored["eligible"])
        self.assertEqual(self.requirement(restored, "independent_review")["evidence_ids"], ["ev-0006"])

    def test_contract_proposal_and_blocking_risk_changes_stale_state_evidence(self) -> None:
        work_id = self.new_l3("state-freshness")
        old_audit = self.snapshot(work_id, "full_audit")
        old_invariant = self.snapshot(work_id, "invariant_contract")
        before = self.check(work_id)
        self.assertEqual(self.requirement(before, "full_audit")["status"], "satisfied")
        self.assertEqual(self.requirement(before, "invariant_contract")["status"], "satisfied")

        runtime.command_contract(SimpleNamespace(
            root=str(self.root), work=work_id, objective=None, constraint=[], non_goal=[],
            invariant=["The new invariant is explicitly reviewed"],
            acceptance=["A second acceptance condition is verified"],
            acceptance_scope=[], replace=False,
        ))
        runtime.command_proposal(SimpleNamespace(
            root=str(self.root), work=work_id,
            summary="Revise the bounded proposal after new information",
            rationale="The task contract changed", non_change=["Preserve public compatibility"],
            evidence_required=list(runtime.RISK_REQUIREMENTS[3]),
        ))
        risk = runtime.command_ledger_add(SimpleNamespace(
            root=str(self.root), work=work_id, kind="risk",
            text="A newly discovered high-risk condition needs explicit closure",
            source="test", non_blocking=False, severity="high", blocking=True,
            mitigation="verify the revised contract", path=[], from_git=False, rollback="",
        ))["entry"]

        stale = self.check(work_id)
        self.assertEqual(self.requirement(stale, "full_audit")["status"], "stale")
        self.assertEqual(self.requirement(stale, "invariant_contract")["status"], "stale")
        codes = {item["code"] for item in stale["missing"]}
        self.assertIn("evidence.full_audit.stale", codes)
        self.assertIn("evidence.invariant_contract.stale", codes)
        self.assertTrue(stale["open_risks"])

        runtime.command_ledger_resolve(SimpleNamespace(
            root=str(self.root), work=work_id, id=risk["id"], status="closed",
            resolution="The revised invariant and acceptance contract address the risk",
            evidence_id=[],
        ))
        new_audit = self.snapshot(work_id, "full_audit")
        new_invariant = self.snapshot(work_id, "invariant_contract")
        current = self.check(work_id)
        self.assertEqual(self.requirement(current, "full_audit")["evidence_ids"], [new_audit["id"]])
        self.assertEqual(self.requirement(current, "invariant_contract")["evidence_ids"], [new_invariant["id"]])
        self.assertNotIn(old_audit["id"], self.requirement(current, "full_audit")["evidence_ids"])
        self.assertNotIn(old_invariant["id"], self.requirement(current, "invariant_contract")["evidence_ids"])

    def test_focused_validation_and_review_do_not_cover_full_acceptance_scope(self) -> None:
        work_id = self.new_l3(
            "acceptance-scope",
            acceptance_scope=["live_validation=scenario:*", "independent_review=codex:full"],
        )
        self.record_all_l3(work_id, live_scope=["scenario:address"], review_scope=["codex:focused"])
        focused = self.check(work_id)
        self.assertFalse(focused["eligible"])
        self.assertEqual(self.requirement(focused, "live_validation")["status"], "scope_mismatch")
        self.assertEqual(self.requirement(focused, "independent_review")["status"], "scope_mismatch")
        codes = {item["code"] for item in focused["missing"]}
        self.assertIn("evidence.live_validation.scope", codes)
        self.assertIn("evidence.independent_review.scope", codes)

        full_live = self.verify(work_id, "live_validation", scope=["scenario:*"])
        full_review = self.record(
            work_id, "independent_review", "review/verdict.json", producer="reviewer-b",
            scope=["codex:full"],
            content={"verdict": "PASS", "revision": 2, "challenge": "complete diff reviewed"},
        )
        complete = self.check(work_id)
        self.assertTrue(complete["eligible"], complete)
        self.assertEqual(self.requirement(complete, "live_validation")["evidence_ids"], [full_live["id"]])
        self.assertEqual(self.requirement(complete, "independent_review")["evidence_ids"], [full_review["id"]])

    def test_legacy_unbound_pass_is_stale_not_current(self) -> None:
        work_id = runtime.command_new(SimpleNamespace(
            root=str(self.root), kind="issue", title="Legacy evidence", slug="legacy-evidence",
            risk=0, owner="owner-a", allow_path=["docs/**"], no_writes=False,
        ))["id"]
        runtime.command_contract(SimpleNamespace(
            root=str(self.root), work=work_id, objective="Validate legacy evidence handling",
            constraint=[], non_goal=[], invariant=[], acceptance=["Legacy PASS is not trusted"],
            acceptance_scope=[], replace=False,
        ))
        note = self.root / "docs" / "note.md"
        note.parent.mkdir(parents=True)
        note.write_text("note\n", encoding="utf-8")
        runtime.command_ledger_add(SimpleNamespace(
            root=str(self.root), work=work_id, kind="change", text="Add note", source="test",
            non_blocking=False, severity="medium", blocking=False, mitigation="",
            path=["docs/note.md"], from_git=False, rollback="restore note",
        ))
        self.verify(work_id, "diff_check")
        self.verify(work_id, "format_check")
        work_dir = self.root / ".codestable" / "work" / "active" / work_id
        entries = runtime.read_evidence(work_dir)
        previous = None
        legacy_lines = []
        for entry in entries:
            payload = dict(entry)
            payload["schema_version"] = 1
            payload.pop("bindings", None)
            payload.pop("scope", None)
            payload["previous_sha256"] = previous
            payload.pop("entry_sha256", None)
            payload["entry_sha256"] = runtime.sha256_bytes(runtime.canonical_json(payload))
            previous = payload["entry_sha256"]
            legacy_lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        (work_dir / "evidence.jsonl").write_text("\n".join(legacy_lines) + "\n", encoding="utf-8")

        completion = self.check(work_id)
        self.assertFalse(completion["eligible"])
        self.assertEqual(self.requirement(completion, "diff_check")["status"], "stale")
        self.assertEqual(self.requirement(completion, "format_check")["status"], "stale")
        codes = {item["code"] for item in completion["missing"]}
        self.assertIn("evidence.diff_check.stale", codes)
        self.assertIn("evidence.format_check.stale", codes)


class MetaDryRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(ASSET_ROOT, self.root, dirs_exist_ok=True)
        feedback_dir = self.root / ".codestable" / "meta" / "feedback" / "items"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        for index in range(3):
            item = {
                "schema_version": 1, "feedback_id": f"fb-{index}", "run_id": f"run-{index}",
                "classification": "harness_policy", "signal": "completion.stale_evidence",
                "policy_ids": ["control.evidence-convergence"],
                "runtime_profile": {"adapter": "test", "model_profile": "test"},
                "harness": {"version": "seed", "content_sha256": "abc"},
                "campaign_ids": [], "status": "queued",
                "triaged_at": f"2026-07-16T00:00:0{index}+00:00",
            }
            (feedback_dir / f"fb-{index}.json").write_text(json.dumps(item, sort_keys=True) + "\n", encoding="utf-8")
        trigger_state = self.root / ".codestable" / "meta" / "trigger-state.json"
        trigger_state.write_text(json.dumps({
            "schema_version": 1,
            "last_scan_at": None,
            "day": date.today().isoformat(),
            "campaigns_opened_today": 2,
            "consumed_feedback_ids": [],
        }, sort_keys=True) + "\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=CodeStable Test", "-c", "user.email=test@example.com",
             "commit", "-qm", "meta baseline"], cwd=self.root, check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_scan(self, *, apply: bool) -> dict:
        command = [sys.executable, str(META_PATH), "trigger-scan", "--root", str(self.root)]
        if apply:
            command.append("--apply")
        completed = subprocess.run(
            command, cwd=self.root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"], payload)
        return payload

    def git_status(self) -> str:
        return subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=self.root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        ).stdout

    def test_trigger_scan_dry_run_is_filesystem_read_only_and_apply_persists(self) -> None:
        self.assertEqual(self.git_status(), "")
        trigger_state = self.root / ".codestable" / "meta" / "trigger-state.json"
        before = trigger_state.read_bytes()
        preview = self.run_scan(apply=False)
        self.assertEqual(len(preview["eligible"]), 1)
        self.assertEqual(preview["created"], [])
        self.assertEqual(trigger_state.read_bytes(), before)
        self.assertEqual(self.git_status(), "")

        applied = self.run_scan(apply=True)
        self.assertEqual(applied["created"], [])
        self.assertTrue(applied["state"]["last_scan_at"])
        self.assertNotEqual(trigger_state.read_bytes(), before)
        self.assertNotEqual(self.git_status(), "")
        self.assertTrue((self.root / ".codestable" / "meta" / "campaigns").is_dir())


if __name__ == "__main__":
    unittest.main()
