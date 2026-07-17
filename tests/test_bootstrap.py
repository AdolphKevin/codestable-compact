from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import ASSET_ROOT, ASSET_TOOL, PACKAGE_ROOT, bootstrap_module, file_digest, knowledge_module, tree_digest


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
            self.assertTrue(result["tool_hash_matches_asset"])
            self.assertEqual(file_digest(root / ".codestable" / "tools" / "cs_knowledge.py"), file_digest(ASSET_TOOL))
            config = json.loads((root / ".codestable" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["schema_version"], 1)
            self.assertEqual(config["mode"], "knowledge_wiki")
            self.assertEqual(len(config["wiki"]["categories"]), 11)
            doctor = self.knowledge.doctor(root, self.knowledge.load_config(root))
            self.assertTrue(doctor["ok"], doctor)

    def test_upgrade_retires_old_tools_backs_up_and_preserves_project_data(self) -> None:
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

            old_tools = ("cs_context.py", "cs_meta.py", "cs_harness.py")
            for name in old_tools:
                path = root / ".codestable" / "tools" / name
                path.write_text(f"# legacy {name}\n", encoding="utf-8")
            installed_tool = root / ".codestable" / "tools" / "cs_knowledge.py"
            installed_tool.write_text("# stale tool\n", encoding="utf-8")
            config_path = root / ".codestable" / "config.json"
            config_path.write_text(
                json.dumps({"schema_version": 3, "mode": "evidence_state", "custom": {"keep": "yes"}}),
                encoding="utf-8",
            )

            result = self.bootstrap.install(root, upgrade=True)
            self.assertIsNotNone(result["backup"])
            self.assertTrue(result["tool_hash_matches_asset"])
            self.assertEqual(set(result["retired"]), {f".codestable/tools/{name}" for name in old_tools})
            for path, digest in before.items():
                self.assertTrue(path.is_file())
                self.assertEqual(file_digest(path), digest)
            for name in old_tools:
                self.assertFalse((root / ".codestable" / "tools" / name).exists())
                self.assertTrue((Path(result["backup"]) / ".codestable" / "tools" / name).is_file())
            self.assertTrue((Path(result["backup"]) / ".codestable" / "config.json").is_file())
            self.assertTrue((Path(result["backup"]) / ".codestable" / "tools" / "cs_knowledge.py").is_file())
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["mode"], "knowledge_wiki")
            self.assertEqual(config["custom"], {"keep": "yes"})
            self.assertEqual(file_digest(installed_tool), file_digest(ASSET_TOOL))
            doctor = self.knowledge.doctor(root, self.knowledge.load_config(root))
            self.assertTrue(doctor["ok"], doctor)

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

    def test_invalid_config_is_backed_up_and_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root, upgrade=False)
            config = root / ".codestable" / "config.json"
            config.write_text("{broken", encoding="utf-8")
            result = self.bootstrap.install(root, upgrade=False)
            self.assertIsNotNone(result["backup"])
            self.assertEqual((Path(result["backup"]) / ".codestable" / "config.json").read_text(encoding="utf-8"), "{broken")
            repaired = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(repaired["mode"], "knowledge_wiki")

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
