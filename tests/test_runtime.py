from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
RUNTIME_PATH = REPO / "skills" / "cs" / "assets" / "project" / ".codestable" / "tools" / "cs_context.py"
META_VALIDATOR_PATH = REPO / "scripts" / "validate_meta_effect.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = load_module("codestable_compact_runtime", RUNTIME_PATH)
meta_validator = load_module("codestable_compact_meta_validator", META_VALIDATOR_PATH)


class RuntimeTest(unittest.TestCase):
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

    def new_work(
        self,
        *,
        kind: str = "feature",
        title: str = "Add export filter",
        slug: str = "export-filter",
        risk: int = 1,
        owner: str = "owner-a",
        allow_paths: list[str] | None = None,
        no_writes: bool = False,
    ) -> str:
        payload = runtime.command_new(SimpleNamespace(
            root=str(self.root),
            kind=kind,
            title=title,
            slug=slug,
            risk=risk,
            owner=owner,
            allow_path=allow_paths or ["src/**"],
            no_writes=no_writes,
        ))
        return payload["id"]

    def plan(self, work_id: str, action: str = "inspect", session: str | None = None):
        return runtime.command_plan(SimpleNamespace(
            root=str(self.root), work=work_id, action=action, session=session,
        ))

    def contract(
        self,
        work_id: str,
        *,
        objective: str = "Change observable behavior safely",
        acceptance: list[str] | None = None,
        invariants: list[str] | None = None,
    ) -> dict:
        return runtime.command_contract(SimpleNamespace(
            root=str(self.root),
            work=work_id,
            objective=objective,
            constraint=[],
            non_goal=[],
            invariant=invariants or [],
            acceptance=acceptance or ["The expected behavior is observed"],
            replace=False,
        ))

    def ledger_add(
        self,
        work_id: str,
        kind: str,
        text: str,
        *,
        paths: list[str] | None = None,
        severity: str = "medium",
        blocking: bool = False,
        non_blocking: bool = False,
        mitigation: str = "",
        rollback: str = "",
    ) -> dict:
        return runtime.command_ledger_add(SimpleNamespace(
            root=str(self.root),
            work=work_id,
            kind=kind,
            text=text,
            source="test",
            non_blocking=non_blocking,
            severity=severity,
            blocking=blocking,
            mitigation=mitigation,
            path=paths or [],
            from_git=False,
            rollback=rollback,
        ))

    def verify(self, work_id: str, evidence_type: str, command: list[str]) -> dict:
        return runtime.command_verify(SimpleNamespace(
            root=str(self.root),
            work=work_id,
            type=evidence_type,
            cwd=".",
            timeout=10,
            artifact=[],
            summary="runtime test",
            command=["--", *command],
        ))

    def complete_l0(self, work_id: str, relative_path: str) -> dict:
        self.contract(work_id)
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("validated\n", encoding="utf-8")
        self.ledger_add(work_id, "change", "Update documentation", paths=[relative_path])
        self.verify(work_id, "diff_check", [sys.executable, "-c", "print('diff ok')"])
        self.verify(work_id, "format_check", [sys.executable, "-c", "print('format ok')"])
        return runtime.command_complete(SimpleNamespace(
            root=str(self.root), work=work_id, result="done", reason=None,
        ))

    def test_init_and_doctor(self) -> None:
        doctor = runtime.command_doctor(SimpleNamespace(root=str(self.root)))
        self.assertTrue(doctor["ok"])
        self.assertEqual(doctor["errors"], 0)

    def test_new_state_is_evidence_driven_not_stage_driven(self) -> None:
        work_id = self.new_work(risk=2, allow_paths=["src/**", "tests/**"])
        state = runtime.command_show(SimpleNamespace(
            root=str(self.root), work=work_id, with_context=False,
            with_evidence=True, evidence_limit=20,
        ))["state"]
        self.assertEqual(state["schema_version"], 2)
        self.assertEqual(state["current_action"], "inspect")
        self.assertNotIn("stage", state)
        self.assertNotIn("lane", state)
        self.assertEqual(state["risk"]["level"], 2)
        self.assertEqual(
            [item["type"] for item in state["evidence"]["required"]],
            list(runtime.RISK_REQUIREMENTS[2]),
        )
        work_dir = self.root / ".codestable" / "work" / "active" / work_id
        self.assertTrue((work_dir / "evidence.jsonl").exists())

    def test_runtime_init_repairs_control_and_meta_boundaries(self) -> None:
        config_path = self.root / ".codestable" / "config.json"
        config = runtime.read_json(config_path)
        config["artifacts"]["mode"] = "stage_state"
        config["control_plane"]["state_model"] = "workflow"
        config["control_plane"]["completion_authority"] = "owner"
        config["execution"]["mode"] = "fixed_pipeline"
        config["context"]["excluded_normal_roots"] = []
        config["observability"]["mode"] = "active"
        config["observability"]["best_effort"] = False
        config["observability"]["read_during_normal_runs"] = True
        config["observability"]["capture"]["full_tool_output"] = True
        config["evolution"]["mode"] = "continuous"
        config["evolution"]["auto_promote"] = True
        config["evolution"]["require_private_holdout"] = False
        config["evaluator"]["mode"] = "local_unsigned"
        runtime.write_json(config_path, config)

        runtime.init_runtime(self.root)
        repaired = runtime.read_json(config_path)
        self.assertEqual(repaired["artifacts"]["mode"], "evidence_state")
        self.assertEqual(repaired["control_plane"]["state_model"], "evidence")
        self.assertEqual(repaired["control_plane"]["completion_authority"], "harness")
        self.assertEqual(repaired["execution"]["mode"], "evidence_convergence")
        self.assertTrue(set(runtime.MANDATORY_NORMAL_CONTEXT_EXCLUSIONS).issubset(
            set(repaired["context"]["excluded_normal_roots"])
        ))
        self.assertEqual(repaired["observability"]["mode"], "passive")
        self.assertTrue(repaired["observability"]["best_effort"])
        self.assertFalse(repaired["observability"]["read_during_normal_runs"])
        self.assertFalse(repaired["observability"]["capture"]["full_tool_output"])
        self.assertEqual(repaired["evolution"]["mode"], "manual")
        self.assertFalse(repaired["evolution"]["auto_promote"])
        self.assertTrue(repaired["evolution"]["require_private_holdout"])
        self.assertEqual(repaired["evaluator"]["mode"], "external_signed_aggregate")
        self.assertTrue(runtime.command_doctor(SimpleNamespace(root=str(self.root)))["ok"])

    def test_context_receipt_is_session_scoped_action_aware_and_hash_sensitive(self) -> None:
        work_id = self.new_work()
        work_path = f".codestable/work/active/{work_id}/work.md"

        first = self.plan(work_id, "propose", "live-a")
        self.assertIn(work_path, {item["path"] for item in first["read"]})

        runtime.command_receipt(SimpleNamespace(
            root=str(self.root), work=work_id, session="live-a", action="propose",
            reason="current-work", paths=[work_path],
        ))
        second = self.plan(work_id, "propose", "live-a")
        self.assertIn(work_path, {item["path"] for item in second["reuse"]})

        cold = self.plan(work_id, "propose", "new-conversation")
        self.assertIn(work_path, {item["path"] for item in cold["read"]})

        path = self.root / work_path
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        changed = self.plan(work_id, "propose", "live-a")
        self.assertIn(work_path, {item["path"] for item in changed["read"]})

        runtime.command_receipt(SimpleNamespace(
            root=str(self.root), work=work_id, session="live-a", action="propose",
            reason="current-work", paths=[work_path],
        ))
        stat = path.stat()
        original = path.read_text(encoding="utf-8")
        replacement = ("X" if original[0] != "X" else "Y") + original[1:]
        path.write_text(replacement, encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        metadata_preserved_change = self.plan(work_id, "propose", "live-a")
        self.assertIn(work_path, {item["path"] for item in metadata_preserved_change["read"]})

    def test_explicit_model_link_avoids_global_scan(self) -> None:
        work_id = self.new_work()
        req_dir = self.root / ".codestable" / "model" / "requirements"
        req_dir.mkdir(parents=True, exist_ok=True)
        (req_dir / "export.md").write_text("# Export\n\nOrganization filtering contract.\n", encoding="utf-8")
        (req_dir / "billing.md").write_text("# Billing\n\nInvoices.\n", encoding="utf-8")

        runtime.command_link(SimpleNamespace(
            root=str(self.root), work=work_id,
            model=[".codestable/model/requirements/export.md"], knowledge=[], path=[],
            symbol=[], keyword=[], child=[], parent=None,
        ))
        plan = self.plan(work_id, "inspect", "live")
        paths = {item["path"] for item in plan["read"]}
        self.assertIn(".codestable/model/requirements/export.md", paths)
        self.assertNotIn(".codestable/model/requirements/billing.md", paths)
        self.assertNotIn(".codestable/model/INDEX.md", paths)

    def test_normal_context_rejects_observation_and_evolution_paths(self) -> None:
        work_id = self.new_work()
        observation = self.root / ".codestable" / "observations" / "pending" / "run-x" / "meta.json"
        observation.parent.mkdir(parents=True, exist_ok=True)
        observation.write_text('{"run_id":"run-x"}\n', encoding="utf-8")
        relative = str(observation.relative_to(self.root))

        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_link(SimpleNamespace(
                root=str(self.root), work=work_id,
                model=[], knowledge=[], path=[relative], symbol=[], keyword=[], child=[], parent=None,
            ))
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_receipt(SimpleNamespace(
                root=str(self.root), work=work_id, session="live", action="inspect",
                reason="forbidden", paths=[relative],
            ))

        state_path = self.root / ".codestable" / "work" / "active" / work_id / "state.json"
        state = runtime.read_json(state_path)
        state["scope"]["paths"].append(relative)
        runtime.write_json(state_path, state)
        plan = self.plan(work_id, "inspect", "live")
        planned = {item["path"] for bucket in ("read", "reuse", "missing") for item in plan[bucket]}
        self.assertNotIn(relative, planned)

    def test_completion_is_denied_until_real_evidence_exists(self) -> None:
        work_id = self.new_work(risk=0, allow_paths=["docs/**"])
        self.contract(work_id)
        path = self.root / "docs" / "note.md"
        path.parent.mkdir(parents=True)
        path.write_text("note\n", encoding="utf-8")
        self.ledger_add(work_id, "change", "Update note", paths=["docs/note.md"])

        with self.assertRaisesRegex(runtime.RuntimeErrorWithHint, "completion denied"):
            runtime.command_complete(SimpleNamespace(
                root=str(self.root), work=work_id, result="done", reason=None,
            ))
        check = runtime.command_check(SimpleNamespace(root=str(self.root), work=work_id))
        missing = {item["code"] for item in check["completion"]["missing"]}
        self.assertIn("evidence.diff_check", missing)
        self.assertIn("evidence.format_check", missing)

    def test_artifact_record_cannot_satisfy_command_backed_evidence(self) -> None:
        work_id = self.new_work(risk=0, allow_paths=["docs/**"])
        self.contract(work_id)
        path = self.root / "docs" / "note.md"
        path.parent.mkdir(parents=True)
        path.write_text("note\n", encoding="utf-8")
        self.ledger_add(work_id, "change", "Update note", paths=["docs/note.md"])
        artifact = self.root / ".codestable" / "work" / "active" / work_id / "owner-assertion.txt"
        artifact.write_text("PASS\n", encoding="utf-8")
        for evidence_type in ("diff_check", "format_check"):
            runtime.command_record(SimpleNamespace(
                root=str(self.root), work=work_id, type=evidence_type, status="PASS",
                producer="owner-a", artifact=[str(artifact.relative_to(self.root))],
                summary="owner assertion", verdict="PASS",
            ))

        check = runtime.command_check(SimpleNamespace(root=str(self.root), work=work_id))
        missing = {item["code"] for item in check["completion"]["missing"]}
        self.assertIn("evidence.diff_check", missing)
        self.assertIn("evidence.format_check", missing)

    def test_unregistered_git_change_blocks_completion_and_escalates_risk(self) -> None:
        work_id = self.new_work(risk=0, allow_paths=["docs/**"])
        self.contract(work_id)
        documented = self.root / "docs" / "note.md"
        documented.parent.mkdir(parents=True)
        documented.write_text("note\n", encoding="utf-8")
        self.ledger_add(work_id, "change", "Update note", paths=["docs/note.md"])
        hidden = self.root / "src" / "newpkg" / "auth.py"
        hidden.parent.mkdir(parents=True)
        hidden.write_text("ALLOW = True\n", encoding="utf-8")
        self.verify(work_id, "diff_check", [sys.executable, "-c", "print('diff ok')"])
        self.verify(work_id, "format_check", [sys.executable, "-c", "print('format ok')"])

        check = runtime.command_check(SimpleNamespace(root=str(self.root), work=work_id))
        codes = {item["code"] for item in check["completion"]["missing"]}
        self.assertEqual(check["risk"]["level"], 3)
        self.assertIn("side_effects.unregistered_paths", codes)
        self.assertIn("side_effects.outside_boundary", codes)
        with self.assertRaisesRegex(runtime.RuntimeErrorWithHint, "completion denied"):
            runtime.command_complete(SimpleNamespace(
                root=str(self.root), work=work_id, result="done", reason=None,
            ))

    def test_verify_records_pass_fail_and_blocked_with_hash_chain(self) -> None:
        work_id = self.new_work(risk=1)
        passed = self.verify(work_id, "targeted_test", [sys.executable, "-c", "print('ok')"])["evidence"]
        failed = self.verify(work_id, "targeted_test", [sys.executable, "-c", "raise SystemExit(7)"])["evidence"]
        blocked = self.verify(work_id, "targeted_test", ["codestable-command-that-does-not-exist"])["evidence"]

        self.assertEqual(passed["status"], "PASS")
        self.assertEqual(passed["exit_code"], 0)
        self.assertEqual(failed["status"], "FAIL")
        self.assertEqual(failed["exit_code"], 7)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertIsNone(blocked["exit_code"])
        self.assertEqual(failed["previous_sha256"], passed["entry_sha256"])
        self.assertEqual(blocked["previous_sha256"], failed["entry_sha256"])
        work_dir = self.root / ".codestable" / "work" / "active" / work_id
        self.assertEqual(len(runtime.read_evidence(work_dir)), 3)

    def test_registered_critical_change_escalates_risk_and_requirements(self) -> None:
        work_id = self.new_work(risk=0, allow_paths=["src/**"])
        critical = self.root / "src" / "auth_policy.py"
        critical.parent.mkdir(parents=True)
        critical.write_text("ENABLED = True\n", encoding="utf-8")
        result = self.ledger_add(
            work_id, "change", "Change authorization policy", paths=["src/auth_policy.py"],
            rollback="restore previous policy",
        )
        self.assertEqual(result["risk"]["level"], 3)
        state = runtime.load_state(self.root / ".codestable" / "work" / "active" / work_id)
        self.assertTrue(state["side_effects"]["rollback_required"])
        self.assertEqual(
            [item["type"] for item in state["evidence"]["required"]],
            list(runtime.RISK_REQUIREMENTS[3]),
        )
        self.assertTrue(any(
            item["source"] in {"git_change_scan", "registered_change"}
            for item in state["risk"]["escalations"]
        ))

    def test_git_change_collection_expands_untracked_files_without_documentation_false_positive(self) -> None:
        path = self.root / "src" / "newpkg" / "auth.py"
        path.parent.mkdir(parents=True)
        path.write_text("ALLOW = True\n", encoding="utf-8")
        changed = runtime.collect_git_changes(self.root)
        self.assertIn("src/newpkg/auth.py", changed)
        self.assertEqual(runtime.path_risk_floor(changed)[0], 3)
        self.assertEqual(runtime.path_risk_floor(["docs/security/readme.md"])[0], 0)

    def test_independent_review_rejects_declared_owner_producer(self) -> None:
        work_id = self.new_work(risk=2, owner="owner-a", allow_paths=["src/**", "review/**"])
        artifact = self.root / "review" / "verdict.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
        args = dict(
            root=str(self.root), work=work_id, type="independent_review", status="PASS",
            artifact=["review/verdict.json"], summary="challenge completed", verdict="PASS",
        )
        with self.assertRaisesRegex(runtime.RuntimeErrorWithHint, "must differ"):
            runtime.command_record(SimpleNamespace(**args, producer="owner-a"))
        recorded = runtime.command_record(SimpleNamespace(**args, producer="reviewer-b"))["evidence"]
        self.assertEqual(recorded["status"], "PASS")
        self.assertEqual(recorded["producer"], "reviewer-b")

    def test_l2_completion_requires_proposal_review_proof_and_preserves_verdict(self) -> None:
        work_id = self.new_work(
            risk=2,
            allow_paths=["src/**", "tests/**", "review/**"],
            title="Cross module behavior change",
            slug="cross-module-change",
        )
        self.contract(
            work_id,
            objective="Change cross-module behavior without breaking serialization",
            acceptance=["Integration scenario passes"],
            invariants=["Existing serialized values remain readable"],
        )
        self.ledger_add(work_id, "fact", "The handler calls the serializer directly")
        runtime.command_proposal(SimpleNamespace(
            root=str(self.root), work=work_id,
            summary="Route the handler through one serializer adapter",
            rationale="Removes duplicate behavior while preserving the public contract",
            non_change=["Do not change stored value format"],
            evidence_required=["integration_test", "independent_review"],
        ))
        for relative, content in (
            ("src/service.py", "def value(): return 1\n"),
            ("tests/test_service.py", "assert True\n"),
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.ledger_add(
            work_id, "change", "Unify service behavior and add coverage",
            paths=["src/service.py", "tests/test_service.py"], rollback="restore prior files",
        )
        self.assertEqual(
            runtime.command_snapshot(SimpleNamespace(
                root=str(self.root), work=work_id, type="audit_ledger", summary="audit complete",
            ))["evidence"]["status"],
            "PASS",
        )
        self.assertEqual(
            runtime.command_snapshot(SimpleNamespace(
                root=str(self.root), work=work_id, type="proposal", summary="proposal captured",
            ))["evidence"]["status"],
            "PASS",
        )
        self.verify(work_id, "integration_test", [sys.executable, "-c", "print('integration pass')"])
        review = self.root / "review" / "verdict.json"
        review.parent.mkdir(parents=True, exist_ok=True)
        review.write_text(json.dumps({"verdict": "PASS", "challenge": "no blocker"}) + "\n", encoding="utf-8")
        runtime.command_record(SimpleNamespace(
            root=str(self.root), work=work_id, type="independent_review", status="PASS",
            producer="reviewer-b", artifact=["review/verdict.json"], summary="no blocker", verdict="PASS",
        ))
        proof = runtime.command_proof(SimpleNamespace(
            root=str(self.root), work=work_id, summary="machine assembled proof",
        ))
        self.assertEqual(proof["evidence"]["status"], "PASS")
        self.assertTrue(proof["completion"]["eligible"])

        completed = runtime.command_complete(SimpleNamespace(
            root=str(self.root), work=work_id, result="done", reason=None,
        ))
        self.assertEqual(completed["completion"]["status"], "COMPLETED")
        reloaded = runtime.load_state(self.root / ".codestable" / "work" / "active" / work_id)
        self.assertEqual(reloaded["completion"]["status"], "COMPLETED")
        self.assertEqual(reloaded["completion"]["next_actions"], [])

    def test_evidence_tampering_is_detected_and_blocks_doctor(self) -> None:
        work_id = self.new_work(risk=1)
        self.verify(work_id, "targeted_test", [sys.executable, "-c", "print('ok')"])
        evidence = self.root / ".codestable" / "work" / "active" / work_id / "evidence.jsonl"
        raw = evidence.read_text(encoding="utf-8")
        evidence.write_text(raw.replace('\"status\": \"PASS\"', '\"status\": \"FAIL\"', 1), encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeErrorWithHint, "integrity failure"):
            runtime.read_evidence(evidence.parent)
        doctor = runtime.command_doctor(SimpleNamespace(root=str(self.root)))
        self.assertFalse(doctor["ok"])
        self.assertTrue(any("evidence integrity" in item["message"] for item in doctor["findings"]))

    def test_completed_tampered_evidence_cannot_be_archived(self) -> None:
        work_id = self.new_work(risk=0, allow_paths=["docs/**"])
        self.complete_l0(work_id, "docs/note.md")
        work_dir = self.root / ".codestable" / "work" / "active" / work_id
        evidence = work_dir / "evidence.jsonl"
        evidence.write_text(
            evidence.read_text(encoding="utf-8").replace('"status": "PASS"', '"status": "FAIL"', 1),
            encoding="utf-8",
        )

        state = runtime.load_state(work_dir)
        self.assertEqual(state["completion"]["status"], "COMPLETED")
        self.assertFalse(state["completion"]["eligible"])
        self.assertEqual(state["evidence"]["integrity"], "invalid")
        with self.assertRaisesRegex(runtime.RuntimeErrorWithHint, "integrity|eligible"):
            runtime.command_archive(SimpleNamespace(root=str(self.root), work=work_id, summary="invalid"))

    def test_source_tree_hash_excludes_repository_control_state(self) -> None:
        before = meta_validator.source_tree_sha256(self.root)
        (self.root / ".git" / "volatile").write_text("changed\n", encoding="utf-8")
        active = self.root / ".codestable" / "work" / "active" / "volatile" / "state.json"
        active.parent.mkdir(parents=True)
        active.write_text("{}\n", encoding="utf-8")
        self.assertEqual(meta_validator.source_tree_sha256(self.root), before)
        (self.root / "README.md").write_text("release source\n", encoding="utf-8")
        self.assertNotEqual(meta_validator.source_tree_sha256(self.root), before)

    def test_legacy_stage_state_migrates_without_fabricating_proof(self) -> None:
        work_id = "2026-07-14-legacy-task"
        work_dir = self.root / ".codestable" / "work" / "active" / work_id
        work_dir.mkdir(parents=True)
        runtime.write_json(work_dir / "state.json", {
            "schema_version": 1,
            "id": work_id,
            "kind": "issue",
            "title": "Legacy issue",
            "slug": "legacy-task",
            "lane": "high-risk",
            "stage": "verify",
            "status": "active",
            "scope": {"paths": [], "symbols": [], "keywords": []},
            "links": {"model": [], "knowledge": [], "parent": None, "children": []},
            "validation": {"last_result": "passed", "commands": ["pytest"]},
        })
        (work_dir / "work.md").write_text("# Legacy issue\n", encoding="utf-8")
        runtime.write_json(work_dir / "context.json", {"schema_version": 1, "sessions": {}})

        state = runtime.load_state(work_dir)
        self.assertEqual(state["schema_version"], 2)
        self.assertNotIn("stage", state)
        self.assertNotIn("lane", state)
        self.assertEqual(state["current_action"], "verify")
        self.assertEqual(state["risk"]["level"], 3)
        self.assertIn("Legacy validation was not converted", state["migration"]["note"])
        self.assertEqual(runtime.read_evidence(work_dir), [])
        self.assertFalse(state["completion"]["eligible"])

    def test_archive_requires_harness_completion_and_stays_out_of_default_search(self) -> None:
        work_id = self.new_work(
            kind="issue", title="Unique quasar regression", slug="quasar-regression",
            risk=0, allow_paths=["docs/**"],
        )
        work_md = self.root / ".codestable" / "work" / "active" / work_id / "work.md"
        work_md.write_text(work_md.read_text(encoding="utf-8") + "\nquasar-needle-91827\n", encoding="utf-8")
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_archive(SimpleNamespace(root=str(self.root), work=work_id, summary=None))

        self.complete_l0(work_id, "docs/quasar.md")
        archived_payload = runtime.command_archive(SimpleNamespace(
            root=str(self.root), work=work_id, summary="fixed",
        ))
        self.assertIn("archive", archived_payload["archived"]["path"])

        current = runtime.command_search(SimpleNamespace(
            root=str(self.root), query="quasar-needle-91827", scope="current",
            limit=5, reason=None, deep=False,
        ))
        self.assertEqual(current["results"], [])
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_search(SimpleNamespace(
                root=str(self.root), query="quasar-needle-91827", scope="archive",
                limit=5, reason=None, deep=False,
            ))
        indexed = runtime.command_search(SimpleNamespace(
            root=str(self.root), query="Unique quasar regression", scope="archive",
            limit=5, reason="regression", deep=False,
        ))
        self.assertTrue(any("archive-index.jsonl" in item["path"] for item in indexed["results"]))
        deep = runtime.command_search(SimpleNamespace(
            root=str(self.root), query="quasar-needle-91827", scope="archive",
            limit=5, reason="regression", deep=True,
        ))
        self.assertTrue(any("work.md" in item["path"] for item in deep["results"]))


if __name__ == "__main__":
    unittest.main()
