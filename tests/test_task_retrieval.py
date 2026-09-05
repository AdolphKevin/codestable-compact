from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import bootstrap_module, knowledge_module, run_tool, tree_digest
from test_governance_acceptance import card, task


class TaskRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = bootstrap_module()
        cls.tool = knowledge_module()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.bootstrap.install(self.root)
        self.config = self.tool.load_config(self.root)
        self.scope = {"repository": "self", "path": "src/auth.py", "symbol": "authenticate"}
        source = self.root / "src/auth.py"
        source.parent.mkdir()
        source.write_text("def authenticate():\n    return True\n\ndef logout():\n    return True\n")
        self.sequence = 0

    def item(self, title, conclusion, **overrides):
        return card("architecture", title, conclusion, scopes=[self.scope], **overrides)

    def learn(self, items=(), **task_overrides):
        self.sequence += 1
        value = task(f"Independent auth fixture {self.sequence}")
        value.update(scopes=[self.scope], new_task_reason=f"Independent fixture goal {self.sequence}.")
        value.update(task_overrides)
        return self.tool.learn(self.root, self.config, {"task": value, "items": list(items)})

    def brief(self, **overrides):
        arguments = dict(root=self.root, config=self.config, task="修改认证入口", paths=["src/auth.py"],
                         symbols=[], limit_override=None, include_history=False)
        arguments.update(overrides)
        return self.tool.selected_brief_payload(**arguments)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True)

    def baseline(self):
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")

    def test_path_symbol_and_repository_queries_find_structured_task_scope(self):
        result = self.learn()
        before = tree_digest(self.root)
        for options in ({}, {"paths": [], "symbols": ["authenticate"]},
                        {"paths": [], "scopes": [self.scope]}):
            with self.subTest(options=options):
                brief = self.brief(**options)
                self.assertEqual([row["id"] for row in brief["related_tasks"]], [result["task_id"]])
                self.assertEqual(brief["knowledge"], [])
        self.assertEqual(tree_digest(self.root), before)

    def test_different_titles_and_categories_share_a_nonblocking_review_candidate(self):
        first = self.learn([self.item("启动组织偏好", "启动认证恢复账号历史组织偏好。")])
        second = self.learn([card("interfaces", "店铺认证目标", "启动认证使用当前绑定店铺的组织，不恢复历史组织偏好。",
                                  scopes=[self.scope])])
        expected = {first["created_cards"][0]["id"], second["created_cards"][0]["id"]}
        before = tree_digest(self.root)
        brief = self.brief(limit_override=1)
        reviews = brief["review_candidates"]
        self.assertFalse(reviews["blocking"])
        self.assertEqual(reviews["claim"], "scope-overlap-only")
        self.assertEqual(len(reviews["items"]), 1)
        self.assertEqual({row["id"] for row in reviews["items"][0]["cards"]}, expected)
        self.assertEqual(set(brief["receipt"]["review_card_ids"]), expected)
        self.assertEqual(len(brief["knowledge"]), 1)  # A second rule cannot disappear behind the quota.
        self.assertIn("同范围知识核对", self.tool.render_brief_markdown(brief))
        drift = self.tool.drift_payload(self.root, self.config, references_only=True)
        self.assertTrue(drift["ok"], drift["findings"])
        self.assertEqual(drift["review_candidates"], reviews)
        self.assertEqual(tree_digest(self.root), before)

    def test_reviews_ignore_other_repositories_symbols_directories_and_equivalent_conclusions(self):
        source = self.item("Account recovery", "Authentication selects the current organization.")
        documents = []
        # Use explicit metadata to exercise every scope combination, independent of learn deduplication.
        for number, (scopes, conclusion) in enumerate([
            ([self.scope], source["knowledge"]),
            ([{**self.scope, "repository": "other"}], "Authentication restores another organization."),
            ([{**self.scope, "symbol": "logout"}], "Logout clears the organization."),
            ([{**self.scope, "path": "src", "symbol": ""}], "Directory-wide authentication behavior."),
            ([{**self.scope, "path": "src", "symbol": ""}], "A different directory-wide convention."),
            ([self.scope], "  Authentication selects the current organization.  "),
        ]):
            metadata = {**source, "id": f"K-fixture-{number}", "title": f"Rule {number}", "scopes": scopes}
            documents.append(self.tool.card_search_document(
                self.root, self.root / f"rule-{number}.md", metadata, "## 结论\n\n" + conclusion,
                self.tool.normalize_scopes(scopes)))
        review = self.tool.scope_review_candidates(self.root, self.config, documents)
        self.assertEqual(review["items"], [])
        self.assertFalse(review["has_more"])

    def test_file_level_reviews_require_a_concrete_file_and_are_bounded_and_deterministic(self):
        file_scope = {**self.scope, "symbol": ""}
        documents = [
            self.tool.card_search_document(
                self.root, self.root / f"rule-{number}.md",
                {"id": f"K-{number}", "title": f"Rule {number}", "category": "architecture", "status": "current"},
                f"## 结论\n\nAuthentication rule {number} has a distinct constraint.",
                [file_scope],
            )
            for number in range(20)
        ]
        first = self.tool.scope_review_candidates(self.root, self.config, documents)
        second = self.tool.scope_review_candidates(self.root, self.config, list(reversed(documents)))
        self.assertEqual(first, second)
        self.assertEqual(len(first["items"]), 5)
        self.assertTrue(first["has_more"])

    def test_superseded_and_unrelated_rules_do_not_create_review_noise(self):
        first = self.learn([self.item("Historical recovery", "Authentication restores the previous organization.")])
        self.learn([self.item("Current destination", "Authentication uses the confirmed shop organization.",
                             supersedes=[first["created_cards"][0]["id"]],
                             supersession_reason="The accepted destination contract changed.")])
        self.assertEqual(self.brief(include_history=True)["review_candidates"]["items"], [])
        self.assertEqual(self.brief(paths=["src/missing.py"])["review_candidates"]["items"], [])

    def test_unrelated_duplicate_titles_stay_out_of_a_focused_brief(self):
        self.learn([self.item("Historical recovery", "Authentication restores an earlier organization.")])
        result = self.learn([self.item("Current recovery", "Authentication selects the current organization.")])
        path = self.root / result["created_cards"][0]["path"]
        path.write_text(path.read_text().replace('title: "Current recovery"', 'title: "Historical recovery"'))
        self.assertTrue(self.brief()["conflicts"])
        self.assertEqual(self.brief(paths=["src/missing.py"])["conflicts"], [])

    def test_task_files_includes_supersession_endpoints_but_not_other_tasks_or_cache(self):
        old = self.learn([self.item("Old recovery", "Authentication restores a previous organization.")])
        new = self.learn([self.item("Current recovery", "Authentication uses the current shop organization.",
                                   supersedes=[old["created_cards"][0]["id"]],
                                   supersession_reason="The accepted rule changed.")])
        unrelated = self.learn()
        before = tree_digest(self.root)
        result = json.loads(run_tool(self.root, "task-files", "--task-id", new["task_id"], "--format", "json").stdout)
        self.assertEqual(set(result["files"]), {
            new["task_note"], new["created_cards"][0]["path"], old["created_cards"][0]["path"],
        })
        self.assertNotIn(unrelated["task_note"], result["files"])
        self.assertTrue(all("/cache/" not in value for value in result["files"]))
        old_record = next(row for row in result["records"] if row["id"] == old["created_cards"][0]["id"])
        self.assertIn("superseded-card", old_record["relations"])
        self.assertIn("not proof", result["limits"][0])
        self.assertEqual(tree_digest(self.root), before)

    def test_task_files_separates_knowledge_use_from_writeback_and_keeps_current_revision(self):
        first = self.learn([self.item("Bound organization", "Authentication uses the bound organization.")])
        identifier = first["created_cards"][0]["id"]
        usage = {
            "card_id": identifier, "card_revision": 1, "use": "tested",
            "detail": "Verified authentication keeps the confirmed organization.",
            "evidence": [{"kind": "test", "artifact": "tests.test_auth.test_organization",
                          "result": "The authentication fixture passed.",
                          "supports": "Authentication keeps the bound organization."}],
        }
        result = self.learn(knowledge_use=[usage])
        update = self.tool.task_update_template(self.root, self.config, result["task_id"])
        update["task"]["result"] = "The updated authentication fixture passes."
        self.tool.learn(self.root, self.config, update)
        files = self.tool.task_files_payload(self.root, self.config, result["task_id"])
        self.assertEqual(files["files"], [result["task_note"]])
        self.assertEqual(files["task_revision"], 2)
        self.assertEqual(files["reference_only"], [{"id": identifier, "path": first["created_cards"][0]["path"]}])

    def test_task_files_unknown_identifier_is_a_read_only_error(self):
        before = tree_digest(self.root)
        for identifier in ("invalid", "T-unknown"):
            result = run_tool(self.root, "task-files", "--task-id", identifier, check=False)
            self.assertEqual(result.returncode, 2)
        self.assertEqual(tree_digest(self.root), before)

    def test_review_candidates_in_staged_checks_ignore_unstaged_rules(self):
        self.learn([self.item("Current destination", "Authentication selects the bound organization.")])
        self.baseline()
        other = self.learn([self.item("Alternative destination", "Authentication restores an earlier organization.")])
        before = tree_digest(self.root)
        self.assertTrue(self.brief()["review_candidates"]["items"])
        cached = self.tool.drift_payload(self.root, self.config, cached=True)
        self.assertEqual(cached["review_candidates"]["items"], [])
        self.assertEqual(tree_digest(self.root), before)
        self.git("add", other["task_note"], other["created_cards"][0]["path"])
        self.assertEqual(len(self.tool.drift_payload(self.root, self.config, cached=True)["review_candidates"]["items"]), 1)

    def test_partial_staged_supersession_has_a_readable_failure(self):
        first = self.learn([self.item("Old destination", "Authentication restores a previous organization.")])
        self.baseline()
        newer = self.learn([self.item("New destination", "Authentication selects the bound organization.",
                                     supersedes=[first["created_cards"][0]["id"]],
                                     supersession_reason="The accepted destination changed.")])
        self.git("add", newer["task_note"], newer["created_cards"][0]["path"])
        before = tree_digest(self.root)
        result = run_tool(self.root, "drift", "--cached", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("card.supersedes.asymmetric", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(tree_digest(self.root), before)


if __name__ == "__main__":
    unittest.main()
