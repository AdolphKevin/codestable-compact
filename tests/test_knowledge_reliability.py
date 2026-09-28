from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import PACKAGE_ROOT, bootstrap_module, knowledge_module, tree_digest, run_tool
from test_governance_acceptance import card, task


class KnowledgeReliabilityTests(unittest.TestCase):
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
        for name in ("src/auth.py", "src/orders/service.py", "tests/test_auth.py"):
            path = self.root / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text("# verified fixture\n")
        self.sequence = 0

    def evidence(self):
        snapshots = [{"repository": "self", "path": path,
                      "sha256": self.tool.sha256_file(self.root / path)}
                     for path in ("src/auth.py", "tests/test_auth.py")]
        record = {"verified_at": "2026-09-01T08:00:00+00:00", "sources": snapshots,
                  "cases": [{"id": "auth.denied", "result": "passed"}]}
        (self.root / "run.json").write_text(json.dumps(record))
        return [{"kind": "test", "artifact": "tests/test_auth.py", "result": "Access denial passed",
                 "supports": "Every order requires authorization", "verified_at": record["verified_at"],
                 "source_snapshots": snapshots, "case_ids": ["auth.denied"],
                 "run_record": {"repository": "self", "path": "run.json"}}]

    def item(self, title="Authorization", **kwargs):
        kwargs.setdefault("new_card_reason", "An independent constraint in this anonymous regression fixture.")
        return card("security-boundaries", title, title + " constrains order authorization.",
                    scopes=[{"repository": "self", "path": "src/auth.py"}], **kwargs)

    def learn(self, items, dry_run=False, **kwargs):
        self.sequence += 1
        value = task(f"Reliability fixture {self.sequence}")
        value.update(paths=["src/auth.py"], scopes=[], new_task_reason=f"Separate fixture {self.sequence}.")
        return self.tool.learn(self.root, self.config, {"task": value, "items": items}, dry_run=dry_run, **kwargs)

    def brief(self, path="src/orders/new.py", **kwargs):
        return self.tool.selected_brief_payload(self.root, self.config, "Change business behavior",
                                               [path], [], kwargs.pop("limit", None), False, **kwargs)

    def review_summaries(self):
        wiki = self.root / ".codestable/wiki"
        for path in (wiki / "security-boundaries/README.md", wiki / "PROJECT.md"):
            path.write_text("<!-- codestable:canonical:start -->\nOrders require authorization.\n"
                            "<!-- codestable:canonical:end -->\n")
            report = self.tool.knowledge_review(self.root, self.config)["summaries"][path.relative_to(self.root).as_posix()]
            marker = {"sources": report["sources"], "knowledge_hash": report["expected_knowledge_hash"],
                      "summary_hash": report["expected_summary_hash"], "reviewed_at": self.tool.now_iso()}
            with path.open("a") as stream:
                stream.write("<!-- codestable:summary-review " + json.dumps(marker) + " -->\n")

    def refresh_summary(self, name):
        path = self.root / name
        text = path.read_text().split("<!-- codestable:summary-review", 1)[0]
        path.write_text(text)
        report = self.tool.knowledge_review(self.root, self.config)["summaries"][name]
        marker = {"sources": report["sources"], "knowledge_hash": report["expected_knowledge_hash"],
                  "summary_hash": report["expected_summary_hash"], "reviewed_at": self.tool.now_iso()}
        path.write_text(text + "<!-- codestable:summary-review " + json.dumps(marker) + " -->\n")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True)

    def baseline(self):
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")

    def test_fixed_retrieval_regression_set(self):
        authorization = self.learn([self.item(applies_to=[{"repository": "self", "path": "src/orders"}],
                                                    evidence=self.evidence())])["created_cards"][0]["id"]
        self.learn([self.item("Foreign authorization", applies_to=[{"repository": "other", "path": "src/orders"}])])
        cases = json.loads((PACKAGE_ROOT / "tests/fixtures/reliability_eval.json").read_text())
        total_required = found_required = unrelated = returned = output_chars = 0
        stale_cases = stale_misses = 0
        for case in cases:
            with self.subTest(case=case["name"]):
                changed = self.root / case["change"] if case.get("change") else None
                original = changed.read_text() if changed else None
                if changed:
                    changed.write_text("# changed after verification\n")
                brief = self.brief(case["path"])
                titles = {value["title"] for value in brief["knowledge"]}
                required, allowed, forbidden = map(set, (case["required"], case["allowed"], case["forbidden"]))
                self.assertTrue(required <= titles)
                self.assertFalse(titles & forbidden)
                self.assertTrue(titles <= allowed)
                issues = {row["issue_type"] for row in brief["review_queue"]}
                self.assertTrue(set(case["expected_issues"]) <= issues)
                if case.get("expected_validity"):
                    actual = brief["knowledge"][0]["evidence_validity"]["status"]
                    self.assertEqual(actual, case["expected_validity"])
                    if case["expected_validity"] != "current":
                        stale_cases += 1
                        stale_misses += actual == "current"
                total_required += len(required)
                found_required += len(required & titles)
                unrelated += len(titles - allowed)
                returned += len(titles)
                output_chars += len(self.tool.render_brief_markdown(brief))
                if changed:
                    changed.write_text(original)
        self.assertEqual(found_required / total_required, 1)
        self.assertEqual(unrelated / returned, 0)
        self.assertGreater(output_chars, 0)
        self.assertEqual(stale_misses / stale_cases, 0)
        self.metrics = {"critical_constraint_recall": found_required / total_required,
                        "irrelevant_result_ratio": unrelated / returned, "query_count": len(cases),
                        "stale_knowledge_miss_ratio": stale_misses / stale_cases,
                        "brief_output_characters": output_chars}
        result = self.brief()["knowledge"][0]
        self.assertEqual(result["id"], authorization)
        self.assertEqual(result["match_group"], "shared-constraint")
        self.assertEqual(result["evidence_validity"]["status"], "current")

    def test_only_one_dependency_hop_and_total_quota(self):
        third = self.learn([self.item("Third rule")])["created_cards"][0]["id"]
        second = self.learn([self.item("Second rule", depends_on=[third])])["created_cards"][0]["id"]
        self.learn([self.item("Applicable rule", applies_to=[{"repository": "self", "path": "src/orders"}],
                                  depends_on=[second])])
        titles = {row["title"] for row in self.brief()["knowledge"]}
        self.assertEqual(titles, {"Applicable rule", "Second rule"})
        limited = self.brief(limit=1)
        self.assertEqual(len(limited["knowledge"]), 1)
        self.assertGreater(limited["truncation"]["shared_constraints"], 0)

    def test_test_file_without_run_is_not_current_evidence_but_can_be_saved(self):
        value = self.item()
        before = tree_digest(self.root)
        plan = self.learn([value], dry_run=True)
        self.assertTrue(plan["apply_allowed"])
        self.assertTrue(plan["review_queue"])
        self.assertEqual(tree_digest(self.root), before)
        self.learn([value])
        brief = self.brief("src/auth.py")
        self.assertEqual(brief["knowledge"][0]["confidence"], "verified")
        self.assertEqual(brief["knowledge"][0]["evidence_validity"]["status"], "unverifiable")
        self.assertIn("证据不足", self.tool.render_brief_markdown(brief))

    def test_source_and_test_changes_expire_evidence_but_unrelated_changes_do_not(self):
        self.learn([self.item(evidence=self.evidence())])
        (self.root / "unrelated.py").write_text("# unrelated\n")
        self.assertEqual(self.brief("src/auth.py")["knowledge"][0]["evidence_validity"]["status"], "current")
        for name in ("src/auth.py", "tests/test_auth.py"):
            path = self.root / name
            original = path.read_text()
            path.write_text(original + "# changed\n")
            self.assertEqual(self.brief("src/auth.py")["knowledge"][0]["evidence_validity"]["status"], "needs-review")
            path.write_text(original)

    def test_failed_skipped_missing_and_remote_runs_never_prove_pass(self):
        evidence = self.evidence()
        for outcome in ("failed", "skipped", None):
            with self.subTest(outcome=outcome):
                record = json.loads((self.root / "run.json").read_text())
                record["cases"] = [] if outcome is None else [{"id": "auth.denied", "result": outcome}]
                (self.root / "run.json").write_text(json.dumps(record))
                self.assertNotEqual(self.tool.evidence_validity(self.root, self.config, evidence)["status"], "current")
        evidence[0]["run_record"] = "https://ci.example.invalid/runs/1"
        self.assertEqual(self.tool.evidence_validity(self.root, self.config, evidence)["status"], "unverifiable")

    def test_summary_review_propagates_and_reindex_cannot_clear_it(self):
        self.learn([self.item(evidence=self.evidence())])
        self.review_summaries()
        state = self.tool.knowledge_review(self.root, self.config)
        project = ".codestable/wiki/PROJECT.md"
        self.assertEqual(state["summaries"][project]["status"], "current")
        self.learn([self.item("Additional order rule", evidence=self.evidence())])
        state = self.tool.knowledge_review(self.root, self.config)
        self.assertEqual(state["summaries"][project]["status"], "needs-review")
        self.refresh_summary(".codestable/wiki/security-boundaries/README.md")
        self.assertEqual(self.tool.knowledge_review(self.root, self.config)["summaries"][project]["status"], "needs-review")
        self.tool.rebuild_indexes(self.root, self.config)
        self.assertEqual(self.tool.knowledge_review(self.root, self.config)["summaries"][project]["status"], "needs-review")
        self.assertIn("需要复核", self.tool.render_brief_markdown(self.brief()))

    def test_external_evidence_and_summary_files_bind_the_learning_plan(self):
        with tempfile.TemporaryDirectory() as external:
            external_root = Path(external)
            contract = external_root / "contract.json"
            contract.write_text('{"version":1}')
            config_path = self.root / ".codestable/config.json"
            config = copy.deepcopy(self.config)
            config["wiki"]["repositories"] = {"contracts": {"root": external}}
            config_path.write_text(json.dumps(config))
            self.config = self.tool.load_config(self.root)
            value = self.item(evidence=[{"kind": "contract", "artifact": "contract.json", "result": "Reviewed contract",
                "supports": "Order protocol", "verified_at": self.tool.now_iso(), "source_snapshots": [
                    {"repository": "contracts", "path": "contract.json", "sha256": self.tool.sha256_file(contract)}]}])
            payload = {"task": task("External protocol fixture"), "items": [value]}
            plan = self.tool.learn(self.root, self.config, payload, dry_run=True)
            contract.write_text('{"version":2}')
            with self.assertRaisesRegex(self.tool.KnowledgeError, "evidence|证据"):
                self.tool.learn(self.root, self.config, payload, plan_token=plan["plan_token"])
            plan = self.tool.learn(self.root, self.config, payload, dry_run=True)
            with (self.root / ".codestable/wiki/PROJECT.md").open("a") as stream:
                stream.write("\nChanged overview\n")
            with self.assertRaisesRegex(self.tool.KnowledgeError, "knowledge changed"):
                self.tool.learn(self.root, self.config, payload, plan_token=plan["plan_token"])

    def test_supersession_excludes_old_rules_and_reports_stale_dependencies(self):
        old = self.learn([self.item("Old authorization")])["created_cards"][0]["id"]
        self.learn([self.item("Order caller", depends_on=[old], applies_to=[{"repository": "self", "path": "src/orders"}])])
        replacement = self.learn([self.item("Current authorization", supersedes=[old],
            supersession_reason="The accepted permission rule changed.",
            applies_to=[{"repository": "self", "path": "src/orders"}])])["created_cards"][0]["id"]
        result = self.brief()
        self.assertIn(replacement, {row["id"] for row in result["knowledge"]})
        self.assertNotIn(old, {row["id"] for row in result["knowledge"]})
        self.assertIn("dependency-not-current", {row["issue_type"] for row in result["review_queue"]})

    def test_quota_reserves_direct_result_deduplicates_and_limits_shared_results(self):
        for index in range(8):
            self.learn([self.item(f"Shared rule {index}", applies_to=[{"repository": "self", "path": "src/orders"}])])
        direct = card("architecture", "Direct order rule", "Order creation calls the authorized service.",
            scopes=[{"repository": "self", "path": "src/orders/service.py"}],
            applies_to=[{"repository": "self", "path": "src/orders"}])
        self.learn([direct])
        brief = self.brief("src/orders/service.py", limit=3)
        self.assertEqual(len(brief["knowledge"]), 3)
        self.assertEqual(sum(row["match_group"] == "direct" for row in brief["knowledge"]), 1)
        self.assertEqual(len({row["id"] for row in brief["knowledge"]}), 3)
        brief = self.brief(limit=18)
        self.assertEqual(len(brief["knowledge"]), 5)

    def test_repository_and_symbol_boundaries_are_respected(self):
        self.learn([self.item(applies_to=[{"repository": "self", "path": "src/orders", "symbol": "create_order"}])])
        self.assertEqual(self.brief()["knowledge"], [])
        result = self.tool.selected_brief_payload(self.root, self.config, "Change behavior", [], [], None, False,
            scopes=[{"repository": "self", "path": "src/orders/new.py", "symbol": "create_order"}])
        self.assertEqual(len(result["knowledge"]), 1)
        result = self.tool.selected_brief_payload(self.root, self.config, "Change behavior", [], [], None, False,
            scopes=[{"repository": "other", "path": "src/orders/new.py", "symbol": "create_order"}])
        self.assertEqual(result["knowledge"], [])
        other = self.item("Other repository")
        other["scopes"] = [{"repository": "other", "path": "src/foreign.py", "symbol": "foreign"}]
        self.learn([other])
        self.assertEqual(self.brief("src/foreign.py")["knowledge"], [])

    def test_run_time_source_mismatch_and_file_removal_are_visible(self):
        evidence = self.evidence()
        record_path = self.root / "run.json"
        original = record_path.read_text()
        for change in ("time", "source", "duplicate"):
            record = json.loads(original)
            if change == "time":
                record["verified_at"] = "2020-01-01T00:00:00+00:00"
            elif change == "source":
                record["sources"][0]["sha256"] = "0" * 64
            else:
                record["cases"].append(record["cases"][0])
            record_path.write_text(json.dumps(record))
            self.assertEqual(self.tool.evidence_validity(self.root, self.config, evidence)["status"], "unverifiable")
        record_path.write_text(original)
        (self.root / "src/auth.py").unlink()
        self.assertEqual(self.tool.evidence_validity(self.root, self.config, evidence)["status"], "needs-review")

    def test_old_evidence_age_alone_does_not_expire_unchanged_content(self):
        evidence = self.evidence()
        evidence[0]["verified_at"] = "2010-01-01T00:00:00+00:00"
        record = json.loads((self.root / "run.json").read_text())
        record["verified_at"] = evidence[0]["verified_at"]
        (self.root / "run.json").write_text(json.dumps(record))
        self.assertEqual(self.tool.evidence_validity(self.root, self.config, evidence)["status"], "current")

    def test_evidence_and_summary_states_use_index_and_head_without_worktree_leaks(self):
        self.learn([self.item(evidence=self.evidence())])
        self.review_summaries()
        self.baseline()
        (self.root / "src/auth.py").write_text("# unstaged change\n")
        (self.root / "run.json").write_text("not a run summary")
        before = tree_digest(self.root)
        for revision in (":", "HEAD"):
            with self.tool.git_read_view(self.root, revision):
                report = self.tool.knowledge_review(self.root, self.tool.load_config(self.root))
                self.assertTrue(all(row["status"] == "current" for row in report["cards"].values()))
                self.assertEqual(report["summaries"][".codestable/wiki/PROJECT.md"]["status"], "current")
        self.assertEqual(tree_digest(self.root), before)
        self.git("add", "src/auth.py")
        with self.tool.git_read_view(self.root, ":"):
            report = self.tool.knowledge_review(self.root, self.tool.load_config(self.root))
            self.assertTrue(all(row["status"] == "needs-review" for row in report["cards"].values()))
            self.assertEqual(report["summaries"][".codestable/wiki/PROJECT.md"]["status"], "needs-review")

    def test_external_source_changes_invalidate_local_summaries_and_snapshot_is_unverifiable(self):
        with tempfile.TemporaryDirectory() as external:
            contract = Path(external) / "protocol.json"
            contract.write_text("{}")
            self.config["wiki"]["repositories"] = {"contracts": {"root": external}}
            (self.root / ".codestable/config.json").write_text(json.dumps(self.config))
            binding = [{"kind": "contract", "artifact": "protocol.json", "result": "Reviewed protocol",
                "supports": "Order requests follow the shared protocol", "verified_at": self.tool.now_iso(),
                "source_snapshots": [{"repository": "contracts", "path": "protocol.json", "sha256": self.tool.sha256_file(contract)}]}]
            self.learn([self.item(evidence=binding)])
            self.review_summaries()
            self.baseline()
            with self.tool.git_read_view(self.root, "HEAD"):
                report = self.tool.knowledge_review(self.root, self.config)
                self.assertTrue(all(row["status"] == "unverifiable" for row in report["cards"].values()))
            contract.write_text('{"required":"actor"}')
            report = self.tool.knowledge_review(self.root, self.config)
            self.assertTrue(all(row["status"] == "needs-review" for row in report["cards"].values()))
            self.assertEqual(report["summaries"][".codestable/wiki/PROJECT.md"]["status"], "needs-review")
            contract.unlink()
            Path(external).rmdir()
            report = self.tool.knowledge_review(self.root, self.config)
            self.assertTrue(all(row["status"] == "unverifiable" for row in report["cards"].values()))

    def test_old_empty_optional_fields_keep_fingerprints_and_retries_idempotent(self):
        value = self.item()
        normalized_task, items = self.tool.normalize_learning_payload({"task": task(), "items": [value]}, self.config)
        item = items[0]
        legacy = {key: content for key, content in item.items() if key not in {"applies_to", "depends_on"}}
        self.assertEqual(self.tool.item_fingerprint(item), self.tool.item_fingerprint(legacy))
        payload = {"task": task("Idempotent metadata fixture"), "items": [value]}
        first = self.tool.learn(self.root, self.config, payload)
        second = self.tool.learn(self.root, self.config, payload)
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["task_id"], second["task_id"])

    def test_projection_lists_affected_summaries_before_apply_without_writes(self):
        self.learn([self.item(evidence=self.evidence())])
        self.review_summaries()
        before = tree_digest(self.root)
        plan = self.learn([self.item("New shared rule")], dry_run=True)
        paths = {row["path"] for row in plan["review_queue"]}
        self.assertIn(".codestable/wiki/security-boundaries/README.md", paths)
        self.assertIn(".codestable/wiki/PROJECT.md", paths)
        self.assertEqual(tree_digest(self.root), before)

    def test_summary_body_and_explicit_sources_are_bound(self):
        first = self.learn([self.item(evidence=self.evidence())])["created_cards"][0]["id"]
        self.review_summaries()
        name = ".codestable/wiki/security-boundaries/README.md"
        path = self.root / name
        text = path.read_text().split("<!-- codestable:summary-review", 1)[0]
        path.write_text(text + '<!-- codestable:summary-review ' + json.dumps({"sources": [first]}) + ' -->\n')
        report = self.tool.knowledge_review(self.root, self.config)["summaries"][name]
        marker = {"sources": [first], "knowledge_hash": report["expected_knowledge_hash"],
                  "summary_hash": report["expected_summary_hash"], "reviewed_at": self.tool.now_iso()}
        path.write_text(text + '<!-- codestable:summary-review ' + json.dumps(marker) + ' -->\n')
        self.learn([self.item("Unrelated summary source")])
        self.assertEqual(self.tool.knowledge_review(self.root, self.config)["summaries"][name]["status"], "current")
        path.write_text(path.read_text().replace("Orders require authorization.", "Orders now use a different protocol."))
        self.assertEqual(self.tool.knowledge_review(self.root, self.config)["summaries"][name]["status"], "needs-review")

    def test_read_commands_preserve_all_files(self):
        self.learn([self.item(evidence=self.evidence(), applies_to=[{"repository": "self", "path": "src/orders"}])])
        before = tree_digest(self.root)
        for args in (("brief", "--task", "Change order", "--path", "src/orders/new.py"), ("status",),
                     ("doctor",), ("audit", "--format", "json"), ("reindex", "--dry-run")):
            run_tool(self.root, *args, check=False)
            self.assertEqual(tree_digest(self.root), before, args)

    def test_existing_maintenance_cycle_needs_no_extra_command(self):
        payload = {"task": task("Ordinary maintenance fixture"), "items": [self.item(evidence=self.evidence())]}
        self.brief("src/auth.py")
        plan = self.tool.learn(self.root, self.config, payload, dry_run=True)
        result = self.tool.learn(self.root, self.config, payload, plan_token=plan["plan_token"])
        self.assertTrue(result["created_cards"])
        self.assertTrue(self.tool.doctor(self.root, self.config)["ok"])
        self.metrics = {"maintenance_operations": ["brief", "learn --dry-run", "learn apply", "doctor"],
                        "additional_required_operations": 0}
