from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import bootstrap_module, knowledge_module, run_tool, tree_digest
from test_governance_acceptance import card, task


class CompactStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = bootstrap_module()
        cls.tool = knowledge_module()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.bootstrap.install(self.root)
        self.config = self.tool.load_config(self.root)
        self.config["wiki"]["topics"] = {"checkout-flow": {"label": "Checkout", "summary": "Checkout invariants"}}
        self.config["wiki"]["topic_governance"] = {"mode": "required", "minimum_coverage": 1.0}
        self.save_config()
        self.source = self.root / "commerce/checkout.py"
        self.source.parent.mkdir()
        self.source.write_text("def create_checkout():\n    return 1\n")

    def save_config(self):
        (self.root / ".codestable/config.json").write_text(json.dumps(self.config))

    def git(self, *arguments):
        return subprocess.check_output(["git", *arguments], cwd=self.root, text=True)

    def baseline(self):
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "CodeStable Fixture")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture baseline")

    def learn(self, title="Checkout implementation", with_card=False):
        value = task(title)
        value["new_task_reason"] = "Independent acceptance fixture: " + title
        items = [card("architecture", "Checkout boundary", "Checkout creation commits one complete result.", topics=["checkout-flow"])] if with_card else []
        return self.tool.learn(self.root, self.config, {"task": value, "items": items})

    def stage_change(self):
        self.source.write_text("def create_checkout():\n    return 2\n")
        result = self.learn()
        self.git("add", "commerce/checkout.py", result["task_note"])
        return result

    def test_learning_changes_only_its_sources_in_git(self):
        self.baseline()
        result = self.learn(with_card=True)
        changes = set(self.git("ls-files", "--others", "--exclude-standard").splitlines())
        self.assertEqual(changes, {result["task_note"], result["created_cards"][0]["path"]})
        self.assertEqual(self.git("diff", "--name-only"), "")
        self.assertTrue((self.root / ".codestable/cache/wiki/index.jsonl").is_file())
        self.assertFalse((self.root / ".codestable/wiki/index.jsonl").exists())

    def test_missing_and_poisoned_cache_cannot_change_knowledge(self):
        self.learn(with_card=True)
        cache = self.root / ".codestable/cache/wiki"
        (cache / "index.jsonl").write_text("untrusted stale index\n")
        shutil.rmtree(cache)
        before = tree_digest(self.root)
        brief = self.tool.selected_brief_payload(self.root, self.config, "Checkout", ["commerce/checkout.py"], [], None, False)
        self.assertEqual(len(brief["knowledge"]), 1)
        self.assertTrue(self.tool.doctor(self.root, self.config)["ok"])
        self.assertTrue(self.tool.rebuild_indexes(self.root, self.config, dry_run=True)["changed"])
        self.assertEqual(tree_digest(self.root), before)
        self.tool.rebuild_indexes(self.root, self.config)
        self.assertEqual(self.tool.rebuild_indexes(self.root, self.config, dry_run=True)["changed"], [])

    def test_cache_rebuild_does_not_expire_a_source_bound_plan(self):
        self.baseline()
        value = {"task": task(), "items": []}
        plan = self.tool.learn(self.root, self.config, value, dry_run=True)
        self.tool.rebuild_indexes(self.root, self.config)
        self.tool.learn(self.root, self.config, value, plan_token=plan["plan_token"])

    def test_compact_records_preserve_information_once_and_roundtrip_updates(self):
        result = self.learn(with_card=True)
        path = self.root / result["created_cards"][0]["path"]
        metadata, body, content = self.tool.read_markdown(path)
        for section in ("未来复用场景", "适用范围", "验证与依据", "来源任务", "主要替代方案", "后果"):
            self.assertNotIn("## " + section, body)
        self.assertEqual(content.count(metadata["evidence"][0]["artifact"]), 1)
        self.assertEqual(len(metadata["future_use"]), 2)
        self.assertNotIn("scope_history: []", content)
        update = self.tool.task_update_template(self.root, self.config, result["task_id"])
        self.assertEqual(update["task"]["source"], task()["source"])
        self.assertEqual(update["task"]["verification"], task()["verification"])
        update["task"]["summary"] = "Verified the updated checkout result."
        updated = self.tool.learn(self.root, self.config, update)
        self.assertEqual(updated["task_id"], result["task_id"])
        self.assertEqual(updated["task_revision"], 2)

    def test_focused_retrieval_does_not_fill_categories_with_text_noise(self):
        items = [card("architecture", "Checkout boundary", "Checkout commits once.", topics=["checkout-flow"])]
        for category in ("interfaces", "security-boundaries", "performance-risks"):
            items.append(card(category, f"Checkout noise {category}", "Checkout validation and performance for an unrelated service.",
                              scopes=[{"repository": "external", "path": "other/service.py"}], topics=["checkout-flow"]))
        self.tool.learn(self.root, self.config, {"task": task(), "items": items})
        focused = self.tool.selected_brief_payload(self.root, self.config, "Checkout validation performance", [], [], None, False,
                                                   scopes=[{"repository": "self", "path": "commerce/checkout.py", "symbol": ""}])
        self.assertEqual([value["title"] for value in focused["knowledge"]], ["Checkout boundary"])
        self.assertEqual(focused["retrieval_mode"], "focused")
        broad = self.tool.selected_brief_payload(self.root, self.config, "Checkout validation performance", [], [], None, False,
                                                 scopes=[{"repository": "self", "path": "commerce/checkout.py", "symbol": ""}], broad=True)
        self.assertGreater(len(broad["knowledge"]), 1)
        missing = self.tool.selected_brief_payload(self.root, self.config, "Checkout", ["unrelated.py"], [], None, False)
        self.assertEqual(missing["knowledge"], [])

    def test_staged_checks_ignore_other_working_changes_without_writes(self):
        self.learn("Baseline boundary", with_card=True)
        self.baseline()
        self.stage_change()
        self.source.write_text("def unrelated_work_in_progress():\n    pass\n")
        (self.root / ".codestable/config.json").write_text("broken unrelated working config")
        (self.root / ".codestable/wiki/architecture/unrelated.md").write_text("---\ninvalid\n---\n")
        before = tree_digest(self.root)
        drift = self.tool.drift_payload(self.root, self.config, cached=True)
        self.assertTrue(drift["ok"], drift)
        audit = json.loads(run_tool(self.root, "audit", "--cached", "--format", "json").stdout)
        self.assertTrue(audit["ok"], audit)
        self.assertEqual(audit["knowledge_source"], "git-index")
        self.assertEqual(tree_digest(self.root), before)

    def test_unstaged_completion_cannot_hide_an_incomplete_staged_task(self):
        self.baseline()
        result = self.stage_change()
        path = self.root / result["task_note"]
        completed = path.read_text()
        path.write_text(completed.replace('task_status: "completed"', 'task_status: "partial"'))
        self.git("add", result["task_note"])
        path.write_text(completed)
        result = self.tool.drift_payload(self.root, self.config, cached=True)
        self.assertIn("task-not-completed", {value["issue_type"] for value in result["findings"]})

    def test_staged_source_checks_do_not_use_an_unstaged_symbol_fix(self):
        self.learn("Baseline boundary", with_card=True)
        self.baseline()
        self.source.write_text("def other_function():\n    return 2\n")
        result = self.learn("Replace checkout function")
        self.git("add", "commerce/checkout.py", result["task_note"])
        self.source.write_text("def create_checkout():\n    return 2\n")
        drift = self.tool.drift_payload(self.root, self.config, cached=True)
        self.assertIn("symbol-text-not-found", {value["issue_type"] for value in drift["unverified_references"]})

    def test_partial_supersession_is_rejected_from_staged_relations(self):
        old = self.learn("Baseline boundary", with_card=True)
        self.baseline()
        item = card("architecture", "New checkout boundary", "Checkout creation uses the replacement entry.",
                    topics=["checkout-flow"], supersedes=[old["created_cards"][0]["id"]], supersession_reason="The accepted implementation boundary changed.")
        value = task("Replace the checkout boundary")
        value["new_task_reason"] = "Explicitly replace the accepted checkout contract."
        new = self.tool.learn(self.root, self.config, {"task": value, "items": [item]})
        self.git("add", new["task_note"], new["created_cards"][0]["path"])
        drift = self.tool.drift_payload(self.root, self.config, cached=True)
        self.assertIn("card.supersedes.asymmetric", {value["issue_type"] for value in drift["findings"]})
        self.git("add", old["created_cards"][0]["path"])
        self.assertTrue(self.tool.drift_payload(self.root, self.config, cached=True)["ok"])

    def test_committed_checks_ignore_both_index_and_working_tree(self):
        self.baseline()
        baseline = self.git("rev-parse", "HEAD").strip()
        result = self.stage_change()
        self.git("commit", "-qm", "complete checkout fixture")
        path = self.root / result["task_note"]
        path.write_text("---\ninvalid\n---\n")
        self.git("add", result["task_note"])
        (self.root / ".codestable/config.json").unlink()
        before = tree_digest(self.root)
        result = json.loads(run_tool(self.root, "audit", "--base", baseline, "--format", "json").stdout)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["knowledge_source"], "HEAD")
        self.assertEqual(tree_digest(self.root), before)

    def test_audit_labels_existing_governance_debt_separately(self):
        self.learn(with_card=True)
        self.config["wiki"]["topics"] = {}
        self.save_config()
        self.baseline()
        self.stage_change()
        result = self.tool.audit_payload(self.root, self.config, cached=True)
        self.assertFalse(result["ok"])
        self.assertGreater(result["comparison"]["existing"], 0)
        self.assertEqual(result["comparison"]["introduced_or_changed"], 0)

    def test_rebuild_resets_sources_and_keeps_application_source(self):
        result = self.learn(with_card=True)
        source = self.source.read_bytes()
        plan = self.bootstrap.install(self.root, rebuild=True, dry_run=True)
        self.bootstrap.install(self.root, rebuild=True, plan_token=plan["plan_token"])
        config = self.tool.load_config(self.root)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertFalse((self.root / result["task_note"]).exists())
        self.assertFalse((self.root / result["created_cards"][0]["path"]).exists())
        self.assertEqual(self.tool.status_payload(self.root, config)["cards"], 0)
        self.assertTrue(self.tool.doctor(self.root, config)["ok"])

    def test_failed_cache_write_rolls_back_the_source_transaction(self):
        before = tree_digest(self.root)
        original_write = self.tool.atomic_write_text
        def fail(path, content):
            if path == self.root / ".codestable/cache/wiki/index.jsonl":
                raise OSError("simulated cache storage failure")
            original_write(path, content)
        with patch.object(self.tool, "atomic_write_text", side_effect=fail):
            with self.assertRaises(OSError):
                self.learn(with_card=True)
        self.assertEqual(tree_digest(self.root), before)


if __name__ == "__main__":
    unittest.main()
