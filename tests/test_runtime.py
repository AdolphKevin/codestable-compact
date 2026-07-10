from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
RUNTIME_PATH = REPO / "skills" / "cs" / "assets" / "project" / ".codestable" / "tools" / "cs_context.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = load_module("codestable_compact_runtime", RUNTIME_PATH)


class RuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        runtime.init_runtime(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def new_work(self, kind: str = "feature", title: str = "Add export filter") -> str:
        payload = runtime.command_new(SimpleNamespace(
            root=str(self.root), kind=kind, title=title, slug="export-filter",
            lane="standard", stage=None,
        ))
        return payload["id"]

    def plan(self, work_id: str, stage: str, session: str | None):
        return runtime.command_plan(SimpleNamespace(
            root=str(self.root), work=work_id, stage=stage, session=session,
        ))

    def test_init_and_doctor(self) -> None:
        doctor = runtime.command_doctor(SimpleNamespace(root=str(self.root)))
        self.assertTrue(doctor["ok"])
        self.assertEqual(doctor["errors"], 0)

    def test_runtime_init_repairs_unsafe_schema_two_boundaries(self) -> None:
        config_path = self.root / ".codestable" / "config.json"
        config = runtime.read_json(config_path)
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

    def test_context_receipt_is_session_scoped_and_change_sensitive(self) -> None:
        work_id = self.new_work()
        work_path = f".codestable/work/active/{work_id}/work.md"

        first = self.plan(work_id, "design", "live-a")
        self.assertIn(work_path, {item["path"] for item in first["read"]})

        runtime.command_receipt(SimpleNamespace(
            root=str(self.root), work=work_id, session="live-a", stage="design",
            reason="current-work", paths=[work_path],
        ))
        second = self.plan(work_id, "design", "live-a")
        self.assertIn(work_path, {item["path"] for item in second["reuse"]})

        cold = self.plan(work_id, "design", "new-conversation")
        self.assertIn(work_path, {item["path"] for item in cold["read"]})

        path = self.root / work_path
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        changed = self.plan(work_id, "design", "live-a")
        self.assertIn(work_path, {item["path"] for item in changed["read"]})

        # Re-record, then alter bytes while preserving size and mtime; SHA must still detect it.
        runtime.command_receipt(SimpleNamespace(
            root=str(self.root), work=work_id, session="live-a", stage="design",
            reason="current-work", paths=[work_path],
        ))
        stat = path.stat()
        original = path.read_text(encoding="utf-8")
        replacement = ("X" if original[0] != "X" else "Y") + original[1:]
        path.write_text(replacement, encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        metadata_preserved_change = self.plan(work_id, "design", "live-a")
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
        plan = self.plan(work_id, "design", "live")
        paths = {item["path"] for item in plan["read"]}
        self.assertIn(".codestable/model/requirements/export.md", paths)
        self.assertNotIn(".codestable/model/requirements/billing.md", paths)
        self.assertNotIn(".codestable/model/INDEX.md", paths)

    def test_normal_context_rejects_observation_and_evolution_paths(self) -> None:
        work_id = self.new_work()
        observation = self.root / ".codestable" / "observations" / "pending" / "run-x" / "meta.json"
        observation.parent.mkdir(parents=True, exist_ok=True)
        observation.write_text('{"run_id":"run-x"}\n', encoding="utf-8")

        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_link(SimpleNamespace(
                root=str(self.root), work=work_id,
                model=[], knowledge=[], path=[str(observation.relative_to(self.root))],
                symbol=[], keyword=[], child=[], parent=None,
            ))
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_receipt(SimpleNamespace(
                root=str(self.root), work=work_id, session="live", stage="design",
                reason="forbidden", paths=[str(observation.relative_to(self.root))],
            ))

        # A manually edited stale state is filtered as a second line of defense.
        state_path = self.root / ".codestable" / "work" / "active" / work_id / "state.json"
        state = runtime.read_json(state_path)
        state["scope"]["paths"].append(str(observation.relative_to(self.root)))
        runtime.write_json(state_path, state)
        plan = self.plan(work_id, "design", "live")
        planned = {item["path"] for bucket in ("read", "reuse", "missing") for item in plan[bucket]}
        self.assertNotIn(str(observation.relative_to(self.root)), planned)

    def test_archive_is_excluded_from_default_search(self) -> None:
        work_id = self.new_work(kind="issue", title="Unique quasar regression")
        work_md = self.root / ".codestable" / "work" / "active" / work_id / "work.md"
        work_md.write_text(work_md.read_text(encoding="utf-8") + "\nquasar-needle-91827\n", encoding="utf-8")
        runtime.command_set(SimpleNamespace(
            root=str(self.root), work=work_id, stage=None, status="done", lane=None,
            gate_status=None, gate_reason=[], gate_question=None,
            validation_command=[], validation_result="passed",
        ))
        runtime.command_archive(SimpleNamespace(
            root=str(self.root), work=work_id, summary="fixed", force=False,
        ))

        current = runtime.command_search(SimpleNamespace(
            root=str(self.root), query="quasar-needle-91827", scope="current", limit=5, reason=None, deep=False,
        ))
        self.assertEqual(current["results"], [])

        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_search(SimpleNamespace(
                root=str(self.root), query="quasar-needle-91827", scope="archive", limit=5, reason=None, deep=False,
            ))

        indexed = runtime.command_search(SimpleNamespace(
            root=str(self.root), query="Unique quasar regression", scope="archive", limit=5, reason="regression", deep=False,
        ))
        self.assertTrue(indexed["searched_archive"])
        self.assertFalse(indexed["deep_archive"])
        self.assertTrue(any("archive-index.jsonl" in item["path"] for item in indexed["results"]))

        archived = runtime.command_search(SimpleNamespace(
            root=str(self.root), query="quasar-needle-91827", scope="archive", limit=5, reason="regression", deep=True,
        ))
        self.assertTrue(archived["deep_archive"])
        self.assertTrue(any("work.md" in item["path"] for item in archived["results"]))

    def test_archive_requires_closed_status(self) -> None:
        work_id = self.new_work()
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_archive(SimpleNamespace(
                root=str(self.root), work=work_id, summary=None, force=False,
            ))

    def test_validation_result_is_closed_and_archive_requires_exact_pass(self) -> None:
        work_id = self.new_work()
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_set(SimpleNamespace(
                root=str(self.root), work=work_id, stage=None, status=None, lane=None,
                gate_status=None, gate_reason=[], gate_question=None,
                validation_command=[], validation_result="looks-good",
            ))
        runtime.command_set(SimpleNamespace(
            root=str(self.root), work=work_id, stage=None, status="done", lane=None,
            gate_status=None, gate_reason=[], gate_question=None,
            validation_command=[], validation_result="blocked",
        ))
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_archive(SimpleNamespace(
                root=str(self.root), work=work_id, summary=None, force=False,
            ))

    def test_archive_requires_validation_for_done_work(self) -> None:
        work_id = self.new_work()
        runtime.command_set(SimpleNamespace(
            root=str(self.root), work=work_id, stage=None, status="done", lane=None,
            gate_status=None, gate_reason=[], gate_question=None,
            validation_command=[], validation_result=None,
        ))
        with self.assertRaises(runtime.RuntimeErrorWithHint):
            runtime.command_archive(SimpleNamespace(
                root=str(self.root), work=work_id, summary=None, force=False,
            ))


if __name__ == "__main__":
    unittest.main()
