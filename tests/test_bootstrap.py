from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import ASSET_ROOT, PACKAGE_ROOT, SHARED_TOOL, bootstrap_module, file_digest, knowledge_module, tree_digest


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bootstrap = bootstrap_module()
        cls.knowledge = knowledge_module()

    def test_distribution_contains_only_the_cs_skill(self) -> None:
        skills = sorted(path.name for path in (PACKAGE_ROOT / "skills").iterdir() if path.is_dir())
        self.assertEqual(skills, ["cs"])
        for retired in ("cs-feat", "cs-issue", "cs-refactor", "cs-roadmap", "cs-model"):
            self.assertFalse((PACKAGE_ROOT / "skills" / retired).exists())

    def test_fresh_install_matches_assets_and_doctor_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self.bootstrap.install(root, upgrade=False)
            self.assertEqual(result["mode"], "knowledge_wiki")
            self.assertEqual(result["runtime_source"], "skill")
            self.assertEqual(Path(result["runtime_path"]), SHARED_TOOL)
            self.assertTrue(result["runtime_contract"]["ok"])
            self.assertIn("audit", result["runtime_contract"]["documented_commands"])
            self.assertIn("learn", result["runtime_contract"]["documented_commands"])
            self.assertIn("template", result["runtime_contract"]["documented_commands"])
            self.assertIn("topics list", result["runtime_contract"]["documented_commands"])
            self.assertIn("topics suggest", result["runtime_contract"]["documented_commands"])
            self.assertFalse((root / ".codestable" / "tools" / "cs_knowledge.py").exists())
            self.assertNotIn("backup", result)
            self.assertNotIn("backed_up", result)
            self.assertFalse((root / ".codestable" / "backups").exists())
            self.assertFalse(result["file_lifecycle"]["automatic_backups"])
            config = json.loads((root / ".codestable" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["schema_version"], 3)
            self.assertEqual(config["mode"], "knowledge_wiki")
            self.assertEqual(len(config["wiki"]["categories"]), 11)
            doctor = self.knowledge.doctor(root, self.knowledge.load_config(root))
            self.assertTrue(doctor["ok"], doctor)

    def test_release_drift_is_informational_and_explicit_upgrade_retires_local_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root, upgrade=False)
            before = tree_digest(root / ".codestable")
            current = self.bootstrap.check_install(root)
            self.assertTrue(current["ok"], current)
            self.assertEqual(current["status"], "current")
            self.assertTrue(current["runtime_contract"]["ok"])
            self.assertEqual(before, tree_digest(root / ".codestable"))

            installed_tool = root / ".codestable" / "tools" / "cs_knowledge.py"
            installed_tool.parent.mkdir(parents=True, exist_ok=True)
            installed_tool.write_text("#!/usr/bin/env python3\nprint('synthetic old runtime')\n", encoding="utf-8")
            (root / ".codestable" / "VERSION").write_text("0.0.0\n", encoding="utf-8")
            stale_before = tree_digest(root / ".codestable")
            stale = self.bootstrap.check_install(root)
            self.assertTrue(stale["ok"], stale)
            self.assertEqual(stale["status"], "current")
            self.assertEqual(stale["runtime_source"], "skill")
            self.assertTrue(stale["runtime_contract"]["ok"])
            self.assertTrue(stale["doctor"]["ok"])
            self.assertFalse(stale["release_metadata"]["aligned"])
            self.assertFalse(stale["release_metadata"]["compatibility_gate"])
            self.assertIn(".codestable/tools/cs_knowledge.py", stale["retired_files_present"])
            self.assertIn(
                ".codestable/VERSION",
                {value["path"] for value in stale["managed_file_mismatches"]},
            )
            self.assertEqual(stale_before, tree_digest(root / ".codestable"))
            self.bootstrap.install(root, upgrade=False)
            self.assertTrue(installed_tool.is_file())
            self.assertEqual(stale_before, tree_digest(root / ".codestable"))

            upgraded = self.bootstrap.install(root, upgrade=True)
            self.assertTrue(upgraded["runtime_contract"]["ok"])
            self.assertEqual(upgraded["retired"], [".codestable/tools/cs_knowledge.py"])
            self.assertFalse(installed_tool.exists())
            self.assertNotIn("backup", upgraded)
            self.assertNotIn("backed_up", upgraded)
            self.assertFalse((root / ".codestable" / "backups").exists())
            restored = self.bootstrap.check_install(root)
            self.assertTrue(restored["ok"], restored)
            self.assertEqual(restored["status"], "current")

    def test_skill_command_contract_rejects_a_documented_missing_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "SKILL.md"
            skill.write_text(
                "| Request | Behavior |\n|---|---|\n| `$cs brief <task>` | read |\n"
                "| `$cs missing-command` | unavailable |\n",
                encoding="utf-8",
            )
            result = self.bootstrap.verify_runtime_command_contract(SHARED_TOOL, skill)
            self.assertFalse(result["ok"])
            self.assertIn("missing-command", result["documented_commands"])
            self.assertEqual(result["unavailable_commands"][0]["command"], "missing-command")

    def test_upgrade_retires_old_tools_without_backups_and_preserves_project_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root, upgrade=False)
            custom_files = {
                root / ".codestable" / "model" / "domain.md": "project domain\n",
                root / ".codestable" / "knowledge" / "notes" / "pitfall.md": "project knowledge\n",
                root / ".codestable" / "work" / "active" / "w1" / "state.json": '{"active":true}\n',
                root / ".codestable" / "wiki" / "PROJECT.md": "# Custom\n\n<!-- codestable:canonical:start -->\n订单是核心聚合。\n<!-- codestable:canonical:end -->\n",
            }
            for path, content in custom_files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            before = {path: file_digest(path) for path in custom_files}

            old_tools = ("cs_context.py", "cs_meta.py", "cs_harness.py", "cs_knowledge.py")
            for name in old_tools:
                path = root / ".codestable" / "tools" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# legacy {name}\n", encoding="utf-8")
            config_path = root / ".codestable" / "config.json"
            config_path.write_text(
                json.dumps({"schema_version": 3, "mode": "evidence_state", "custom": {"keep": "yes"}}),
                encoding="utf-8",
            )
            historical_backup = root / ".codestable" / "backups" / "older-release" / "manual.txt"
            historical_backup.parent.mkdir(parents=True, exist_ok=True)
            historical_backup.write_text("historical backup\n", encoding="utf-8")
            historical_backup_digest = file_digest(historical_backup)

            result = self.bootstrap.install(root, upgrade=True)
            self.assertNotIn("backup", result)
            self.assertNotIn("backed_up", result)
            self.assertEqual(result["runtime_source"], "skill")
            self.assertFalse(result["file_lifecycle"]["automatic_backups"])
            migration = result["knowledge_migration"]
            self.assertTrue(migration["required"])
            self.assertEqual(migration["status"], "pending_page_audit")
            self.assertFalse(migration["automatic_promotion"])
            self.assertFalse(migration["automatic_removal"])
            self.assertTrue(migration["source_pages_retained_in_place"])
            self.assertEqual(
                {page["path"] for page in migration["pages"]},
                {
                    ".codestable/model/domain.md",
                    ".codestable/knowledge/notes/pitfall.md",
                },
            )
            self.assertEqual(set(result["retired"]), {f".codestable/tools/{name}" for name in old_tools})
            for path, digest in before.items():
                self.assertTrue(path.is_file())
                self.assertEqual(file_digest(path), digest)
            for page in migration["pages"]:
                source = root / page["path"]
                self.assertNotIn("backup_path", page)
                self.assertEqual(file_digest(source), page["sha256"])
                self.assertEqual(source.stat().st_size, page["bytes"])
            for name in old_tools:
                self.assertFalse((root / ".codestable" / "tools" / name).exists())
            self.assertTrue(historical_backup.is_file())
            self.assertEqual(file_digest(historical_backup), historical_backup_digest)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["mode"], "knowledge_wiki")
            self.assertEqual(config["custom"], {"keep": "yes"})
            self.assertFalse((root / ".codestable" / "tools" / "cs_knowledge.py").exists())
            doctor = self.knowledge.doctor(root, self.knowledge.load_config(root))
            self.assertTrue(doctor["ok"], doctor)

    def test_incompatible_schema_requires_upgrade_without_running_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root, upgrade=False)
            config_path = root / ".codestable" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["schema_version"] = 2
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            before = tree_digest(root / ".codestable")

            result = self.bootstrap.check_install(root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "needs-upgrade")
            self.assertEqual(result["doctor"]["status"], "not-run")
            self.assertIn("runtime.schema.incompatible", {item["code"] for item in result["compatibility_findings"]})
            self.assertEqual(result["suggested_command"][-1], "--upgrade")
            self.assertEqual(before, tree_digest(root / ".codestable"))

    def test_fresh_install_has_no_pending_knowledge_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.bootstrap.install(Path(temporary), upgrade=False)
            migration = result["knowledge_migration"]
            self.assertFalse(migration["required"])
            self.assertEqual(migration["status"], "not_required")
            self.assertEqual(migration["pages"], [])

    def test_install_with_legacy_pages_requires_upgrade_without_touching_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / ".codestable" / "knowledge" / "note.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("legacy fact\n", encoding="utf-8")
            before = file_digest(legacy)

            result = self.bootstrap.install(root, upgrade=False)

            migration = result["knowledge_migration"]
            self.assertTrue(migration["required"])
            self.assertEqual(migration["status"], "upgrade_required")
            self.assertEqual([page["path"] for page in migration["pages"]], [".codestable/knowledge/note.md"])
            self.assertNotIn("backup_path", migration["pages"][0])
            self.assertTrue(migration["source_pages_retained_in_place"])
            self.assertTrue(legacy.is_file())
            self.assertEqual(file_digest(legacy), before)

    def test_upgrade_preserves_seed_wiki_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root, upgrade=False)
            project = root / ".codestable" / "wiki" / "PROJECT.md"
            requirements = root / ".codestable" / "wiki" / "requirements" / "README.md"
            project.write_text("custom project overview", encoding="utf-8")
            requirements.write_text("custom requirements page", encoding="utf-8")
            before = tree_digest(root / ".codestable" / "wiki")
            self.bootstrap.install(root, upgrade=True)
            after = tree_digest(root / ".codestable" / "wiki")
            self.assertEqual(before, after)
            self.assertEqual(project.read_text(encoding="utf-8"), "custom project overview")
            self.assertEqual(requirements.read_text(encoding="utf-8"), "custom requirements page")

    def test_invalid_config_is_rejected_without_replacement_or_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root, upgrade=False)
            config = root / ".codestable" / "config.json"
            config.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repair it before install or upgrade"):
                self.bootstrap.install(root, upgrade=False)
            self.assertEqual(config.read_text(encoding="utf-8"), "{broken")
            self.assertFalse((root / ".codestable" / "backups").exists())

    def test_asset_manifest_is_complete(self) -> None:
        manifest = json.loads((ASSET_ROOT / ".codestable" / "manifest.json").read_text(encoding="utf-8"))
        declared = set(manifest["managed_files"]) | set(manifest["seed_files"]) | {".codestable/config.json"}
        actual = {
            path.relative_to(ASSET_ROOT).as_posix()
            for path in ASSET_ROOT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(actual, declared)


if __name__ == "__main__":
    unittest.main()
