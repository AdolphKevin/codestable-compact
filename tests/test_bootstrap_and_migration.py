from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO / "skills" / "cs" / "scripts" / "bootstrap.py"
MIGRATE_PATH = REPO / "scripts" / "migrate_legacy.py"
MIGRATE_ALPHA_PATH = REPO / "scripts" / "migrate_alpha_observations.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = load_module("codestable_compact_bootstrap_test", BOOTSTRAP_PATH)
migrate = load_module("codestable_compact_migrate_test", MIGRATE_PATH)
migrate_alpha = load_module("codestable_compact_migrate_alpha_test", MIGRATE_ALPHA_PATH)


class BootstrapAndMigrationTest(unittest.TestCase):
    def test_bootstrap_keeps_runtime_observations_out_of_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bootstrap.install(root, upgrade=False)
            ignore_path = root / ".codestable" / "observations" / ".gitignore"
            ignore_path.write_text("README.md\n", encoding="utf-8")
            bootstrap.install(root, upgrade=True)
            self.assertEqual(ignore_path.read_text(encoding="utf-8"), "/*\n!/.gitignore\n!/README.md\n")
            for state in ("pending", "flagged", "selected"):
                self.assertTrue(
                    (root / ".codestable" / "observations" / state / ".gitkeep").is_file()
                )
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)

            generated = (
                ".codestable/observations/index.jsonl",
                ".codestable/observations/pending/run-a/meta.json",
            )
            for relative in generated:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
                ignored = subprocess.run(
                    ["git", "check-ignore", "--quiet", relative], cwd=root, check=False
                )
                self.assertEqual(ignored.returncode, 0, relative)

            for relative in (
                ".codestable/observations/.gitignore",
                ".codestable/observations/README.md",
            ):
                ignored = subprocess.run(
                    ["git", "check-ignore", "--quiet", relative], cwd=root, check=False
                )
                self.assertEqual(ignored.returncode, 1, relative)

    def test_bootstrap_preserves_user_config_and_upgrade_backs_up_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bootstrap.install(root, upgrade=False)
            config_path = root / ".codestable" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["entry"]["route_summary"] = "off"
            config["custom"] = {"keep": True}
            config_path.write_text(json.dumps(config), encoding="utf-8")

            reference = root / ".codestable" / "reference" / "routing.md"
            reference.write_text("locally modified\n", encoding="utf-8")
            payload = bootstrap.install(root, upgrade=True)
            merged = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(merged["entry"]["route_summary"], "off")
            self.assertTrue(merged["custom"]["keep"])
            self.assertIn("# Routing and continuation", reference.read_text(encoding="utf-8"))
            self.assertIsNotNone(payload["backup"])
            backup = Path(payload["backup"]) / ".codestable" / "reference" / "routing.md"
            self.assertEqual(backup.read_text(encoding="utf-8"), "locally modified\n")

    def test_bootstrap_migrates_alpha_config_to_safe_manual_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / ".codestable" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "entry": {"mode": "auto", "route_summary": "off"},
                        "telemetry": {
                            "enabled": True,
                            "capture_raw_prompts": True,
                            "capture_source_or_diffs": True,
                            "retention_days": 45,
                        },
                        "evolution": {
                            "enabled": True,
                            "auto_promote": "low_risk_only",
                            "trigger": {"minimum_failed_runs": 3},
                        },
                        "custom": {"keep": True},
                    }
                ),
                encoding="utf-8",
            )
            bootstrap.install(root, upgrade=True)
            migrated = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(migrated["schema_version"], 3)
            self.assertEqual(migrated["entry"]["route_summary"], "off")
            self.assertTrue(migrated["custom"]["keep"])
            self.assertEqual(migrated["observability"]["mode"], "passive")
            self.assertEqual(migrated["observability"]["retention"]["pending_days"], 45)
            self.assertFalse(migrated["observability"]["capture"]["raw_prompts"])
            self.assertFalse(migrated["observability"]["capture"]["raw_model_responses"])
            self.assertFalse(migrated["observability"]["capture"]["source_or_diffs"])
            self.assertEqual(migrated["evolution"]["mode"], "manual")
            for field in ("run_during_normal_work", "auto_diagnose", "auto_propose", "auto_evaluate", "auto_promote"):
                self.assertFalse(migrated["evolution"][field])
            self.assertEqual(migrated["evolution"]["promotion_authority"], "owner_checkpoint_by_policy")
            self.assertTrue(migrated["evolution"]["require_validity_prepass"])
            self.assertTrue(migrated["evolution"]["require_fixture_covered_policy"])
            self.assertEqual(migrated["meta"]["trigger"]["mode"], "scan_only_by_default")
            self.assertGreaterEqual(migrated["meta"]["validity"]["minimum_stochastic_repeats"], 5)
            self.assertIn("legacy_telemetry_config", migrated["migration"])

    def test_bootstrap_repairs_unsafe_schema_two_config_without_losing_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bootstrap.install(root, upgrade=False)
            config_path = root / ".codestable" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["context"]["excluded_normal_roots"] = [".custom/private"]
            config["observability"].update({
                "enabled": False,
                "mode": "active-analysis",
                "best_effort": False,
                "read_during_normal_runs": True,
            })
            config["observability"]["capture"].update({
                "raw_prompts": True,
                "raw_model_responses": True,
                "source_or_diffs": True,
                "full_tool_output": True,
            })
            config["evolution"].update({
                "enabled": False,
                "mode": "continuous",
                "run_during_normal_work": True,
                "auto_diagnose": True,
                "auto_propose": True,
                "auto_evaluate": True,
                "auto_promote": True,
                "trigger": {"minimum_runs": 1},
                "require_selected_cases": False,
                "require_human_promotion_gate": False,
                "require_private_holdout": False,
            })
            config["evaluator"] = {
                "mode": "local_unsigned",
                "require_signed_results": False,
                "signing_algorithm": "none",
                "private_holdout_location": "inside_candidate_workspace",
            }
            config["custom"] = {"keep": "yes"}
            config_path.write_text(json.dumps(config), encoding="utf-8")

            bootstrap.install(root, upgrade=False)
            repaired = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertFalse(repaired["observability"]["enabled"])
            self.assertFalse(repaired["evolution"]["enabled"])
            self.assertEqual(repaired["custom"], {"keep": "yes"})
            exclusions = set(repaired["context"]["excluded_normal_roots"])
            self.assertIn(".custom/private", exclusions)
            for required in bootstrap.MANDATORY_NORMAL_EXCLUSIONS:
                self.assertIn(required, exclusions)
            self.assertEqual(repaired["observability"]["mode"], "passive")
            self.assertTrue(repaired["observability"]["best_effort"])
            self.assertFalse(repaired["observability"]["read_during_normal_runs"])
            for field in ("raw_prompts", "raw_model_responses", "source_or_diffs", "full_tool_output"):
                self.assertFalse(repaired["observability"]["capture"][field])
            self.assertEqual(repaired["evolution"]["mode"], "manual")
            for field in ("run_during_normal_work", "auto_diagnose", "auto_propose", "auto_evaluate", "auto_promote"):
                self.assertFalse(repaired["evolution"][field])
            self.assertTrue(repaired["evolution"]["require_selected_cases"])
            self.assertEqual(repaired["evolution"]["promotion_authority"], "owner_checkpoint_by_policy")
            self.assertTrue(repaired["evolution"]["require_validity_prepass"])
            self.assertTrue(repaired["evolution"]["require_fixture_covered_policy"])
            self.assertFalse(repaired["meta"]["normal_runs_may_import_meta"])
            self.assertEqual(repaired["meta"]["trigger"]["mode"], "scan_only_by_default")
            self.assertTrue(repaired["evolution"]["require_private_holdout"])
            self.assertNotIn("trigger", repaired["evolution"])
            self.assertEqual(repaired["evaluator"]["mode"], "external_signed_aggregate")
            self.assertTrue(repaired["evaluator"]["require_signed_results"])
            self.assertEqual(repaired["evaluator"]["private_holdout_location"], "outside_candidate_workspace")

    def test_bootstrap_recovers_invalid_json_config_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bootstrap.install(root, upgrade=False)
            config_path = root / ".codestable" / "config.json"
            config_path.write_text("{broken", encoding="utf-8")
            payload = bootstrap.install(root, upgrade=False)
            repaired = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired["entry"]["mode"], "auto")
            self.assertEqual(repaired["observability"]["mode"], "passive")
            self.assertEqual(repaired["evolution"]["mode"], "manual")
            self.assertIsNotNone(payload["backup"])
            backup = Path(payload["backup"]) / ".codestable" / "config.json"
            self.assertEqual(backup.read_text(encoding="utf-8"), "{broken")

    def test_legacy_migration_is_dry_run_then_non_destructive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cs = root / ".codestable"
            (cs / "requirements" / "adrs").mkdir(parents=True)
            (cs / "requirements" / "orders" / "adrs").mkdir(parents=True)
            (cs / "features" / "2025-01-01-old-feature").mkdir(parents=True)
            (cs / "compound").mkdir(parents=True)
            (cs / "requirements" / "VISION.md").write_text("legacy vision", encoding="utf-8")
            (cs / "requirements" / "adrs" / "001-old.md").write_text("old decision", encoding="utf-8")
            (cs / "requirements" / "orders" / "adrs" / "002-order.md").write_text("order decision", encoding="utf-8")
            (cs / "features" / "2025-01-01-old-feature" / "design.md").write_text("history needle", encoding="utf-8")
            (cs / "compound" / "pitfall.md").write_text("pitfall", encoding="utf-8")

            plan = migrate.build_plan(root)
            self.assertGreater(len(plan), 0)
            self.assertFalse((cs / "migration-staging").exists())

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = migrate.main([str(root), "--apply"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue((cs / "migration-staging" / "model" / "vision.legacy.md").is_file())
            self.assertTrue((cs / "migration-staging" / "model" / "decisions" / "001-old.md").is_file())
            self.assertTrue((cs / "migration-staging" / "model" / "decisions" / "orders" / "002-order.md").is_file())
            self.assertTrue((cs / "migration-staging" / "knowledge" / "notes" / "pitfall.md").is_file())
            self.assertTrue((cs / "work" / "archive" / "legacy" / "features" / "2025-01-01-old-feature" / "design.md").is_file())
            self.assertTrue((cs / "features" / "2025-01-01-old-feature" / "design.md").is_file())
            self.assertTrue((cs / "migration-report.json").is_file())

    def test_alpha_run_migration_is_dry_run_sanitized_and_non_destructive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / ".codestable" / "telemetry" / "runs" / "legacy-run"
            legacy.mkdir(parents=True)
            (legacy / "run.json").write_text(
                json.dumps(
                    {
                        "id": "legacy-run",
                        "work": "work-1",
                        "task_id": "task-1",
                        "harness_version": "h-alpha",
                        "model": "model-a",
                        "adapter": "adapter-a",
                        "evaluator": "legacy-evaluator",
                        "started_at": "2026-07-01T00:00:00+00:00",
                        "ended_at": "2026-07-01T00:05:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            (legacy / "summary.json").write_text(
                json.dumps(
                    {
                        "outcome": "failed",
                        "notes": "raw prompt accidentally copied here: SECRET",
                        "failure_signature": {
                            "verifier_cause": "acceptance failed",
                            "causal_role": "route was wrong",
                            "agent_mechanism": "routing mistake",
                        },
                        "metrics": {"tool_calls": 12},
                    }
                ),
                encoding="utf-8",
            )
            (legacy / "events.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": "2026-07-01T00:01:00+00:00",
                        "type": "Tool Failed",
                        "payload": {
                            "tool": "shell",
                            "attempt": 2,
                            "raw_prompt": "SECRET",
                            "diff": "SECRET DIFF",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            plan = migrate_alpha.build_plan(root)
            self.assertEqual(plan[0]["action"], "copy")
            self.assertFalse((root / ".codestable" / "observations").exists())

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = migrate_alpha.main([str(root), "--apply"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["legacy_preserved"])
            self.assertTrue(legacy.is_dir())

            target = root / ".codestable" / "observations" / "flagged" / "legacy-run"
            self.assertTrue(target.is_dir())
            events = (target / "events.jsonl").read_text(encoding="utf-8")
            outcome = (target / "outcome.json").read_text(encoding="utf-8")
            self.assertNotIn("SECRET", events)
            self.assertNotIn("SECRET", outcome)
            event = json.loads(events.strip())
            self.assertEqual(event["payload"]["tool"], "shell")
            self.assertIn("legacy_payload_sha256", event["payload"])
            self.assertNotIn("raw_prompt", event["payload"])
            self.assertNotIn("diff", event["payload"])


if __name__ == "__main__":
    unittest.main()
