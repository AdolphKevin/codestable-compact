from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO / "skills" / "cs" / "assets" / "project"
HARNESS_PATH = ASSET_ROOT / ".codestable" / "tools" / "cs_harness.py"
EVOLVE_PATH = ASSET_ROOT / ".codestable" / "tools" / "cs_evolve.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = load_module("codestable_compact_harness_test", HARNESS_PATH)
evolve = load_module("codestable_compact_harness_evolve_test", EVOLVE_PATH)


class ReadOnlyHarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(ASSET_ROOT, self.root, dirs_exist_ok=True)
        evolve.init_runtime(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_identity_uses_only_active_surfaces_and_detects_drift(self) -> None:
        identity = harness.active_identity(self.root)
        self.assertEqual(identity["version"], "seed")
        self.assertFalse(identity["drift_detected"])
        self.assertEqual(identity["content_sha256"], identity["snapshot_content_sha256"])

        routing = self.root / ".codestable" / "reference" / "routing.md"
        routing.write_text(routing.read_text(encoding="utf-8") + "\nlocal drift\n", encoding="utf-8")
        drifted = harness.active_identity(self.root)
        self.assertTrue(drifted["drift_detected"])

    def test_playbook_query_is_bounded_filtered_and_public(self) -> None:
        playbook = self.root / ".codestable" / "harness" / "playbook.jsonl"
        rules = [
            {
                "id": "retry-on-timeout",
                "status": "active",
                "rule": "After the same timeout, change strategy instead of repeating blindly.",
                "applies_to": ["issue", "analyze"],
                "keywords": ["timeout", "retry"],
                "confidence": 0.9,
                "source_case": "case-timeout",
                "private_notes": "must never enter normal context",
            },
            {
                "id": "feature-only",
                "status": "active",
                "rule": "Feature-specific rule.",
                "applies_to": ["feature", "design"],
                "keywords": ["feature"],
            },
            {
                "id": "retired-rule",
                "status": "retired",
                "rule": "Do not load this.",
                "applies_to": ["issue", "analyze"],
                "keywords": ["timeout"],
            },
        ]
        playbook.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in rules),
            encoding="utf-8",
        )
        result = harness.query_playbook(
            self.root,
            kind="issue",
            stage="analyze",
            keywords=("timeout",),
            limit=5,
        )
        self.assertEqual([item["id"] for item in result["rules"]], ["retry-on-timeout"])
        self.assertNotIn("private_notes", result["rules"][0])
        with self.assertRaises(harness.HarnessReadError):
            harness.query_playbook(self.root, kind=None, stage=None, keywords=(), limit=21)

    def test_normal_harness_reader_has_no_control_plane_dependency(self) -> None:
        source = HARNESS_PATH.read_text(encoding="utf-8")
        for forbidden in (
            ".codestable/observations",
            ".codestable/evolution",
            ".codestable/evals",
            ".codestable/harness/versions",
            "import cs_evolve",
            "import cs_eval",
            "import cs_observe",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
