from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from support import base_task, bootstrap_module, json_output, run_tool, tree_digest


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = bootstrap_module()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project"
        self.root.mkdir()
        self.bootstrap.install(self.root)
        source = self.root / "src/orders/service.py"
        source.parent.mkdir(parents=True)
        source.write_text("class OrderService:\n    def create(self):\n        return True\n")
        self.ref = {"system": "github", "id": "https://github.com/acme/orders/issues/17"}

    def learn(self, task):
        raw = json.dumps({"task": task, "items": []})
        preview = json_output(run_tool(self.root, "learn", "--file", "-", "--dry-run", stdin=raw))
        if preview.get("idempotent"):
            return preview
        return json_output(run_tool(self.root, "learn", "--file", "-", "--plan-token", preview["plan_token"], stdin=raw))

    def test_external_reference_round_trip_and_exact_lookup(self):
        before = tree_digest(self.root)
        generated = json_output(run_tool(self.root, "template", "--external-ref",
            "GitHub=https://GitHub.com/Acme/Orders/issues/017/", "--external-ref",
            "github=https://github.com/acme/orders/issues/17"))
        self.assertEqual(generated["task"]["external_refs"], [self.ref])
        self.assertEqual(tree_digest(self.root), before)

        task = base_task()
        task["external_refs"] = generated["task"]["external_refs"]
        result = self.learn(task)
        files = json_output(run_tool(self.root, "task-files", "--task-id", result["task_id"], "--format", "json"))
        self.assertEqual(files["external_refs"], [self.ref])
        brief = json_output(run_tool(self.root, "brief", "--task", "unrelated words", "--external-ref",
            "github=https://github.com/acme/orders/issues/17", "--format", "json"))
        self.assertEqual([row["id"] for row in brief["related_tasks"]], [result["task_id"]])
        self.assertEqual(brief["related_tasks"][0]["external_refs"], [self.ref])
        missing = json_output(run_tool(self.root, "brief", "--task", task["title"], "--external-ref",
            "github=https://github.com/other/orders/issues/17", "--format", "json"))
        self.assertEqual(missing["related_tasks"], [])

    def test_plan_export_refuses_every_existing_destination_before_planning(self):
        self.learn(base_task())
        conflicting = {**base_task(), "result": "A different result requiring task identity clarification."}
        regular = self.root.parent / "existing.token"
        regular.write_text("old token must survive\n")
        missing = self.root.parent / "never-create.token"
        dangling = self.root.parent / "dangling.token"
        dangling.symlink_to(missing)
        before = tree_digest(self.root)
        for path in (regular, dangling, self.root.parent):
            for value in (base_task(), conflicting):
                with self.subTest(path=path, task=value["result"]):
                    process = run_tool(self.root, "learn", "--file", "-", "--dry-run", "--plan-out", str(path),
                        stdin=json.dumps({"task": value, "items": []}), check=False)
                    result = json_output(process)
                    self.assertEqual(process.returncode, 2, result)
                    self.assertEqual(result["error_code"], "plan-file-exists")
                    self.assertTrue(result["next_action"])
        self.assertEqual(regular.read_text(), "old token must survive\n")
        self.assertTrue(dangling.is_symlink())
        self.assertFalse(missing.exists())
        self.assertEqual(tree_digest(self.root), before)

    def test_no_plan_result_and_retry_are_explicit_and_leave_output_absent(self):
        original = json.dumps({"task": base_task(), "items": []})
        plan_file = self.root.parent / "initial.token"
        preview = json_output(run_tool(self.root, "learn", "--file", "-", "--dry-run", "--plan-out", str(plan_file), stdin=original))
        self.assertEqual(preview["plan_state"], "ready")
        applied = json_output(run_tool(self.root, "learn", "--file", "-", "--plan-file", str(plan_file), stdin=original))
        retry = json_output(run_tool(self.root, "learn", "--file", "-", "--plan-file", str(plan_file), stdin=original))
        self.assertTrue(retry["idempotent"])
        self.assertEqual(retry["task_id"], applied["task_id"])
        absent = self.root.parent / "no-application.token"
        no_op = json_output(run_tool(self.root, "learn", "--file", "-", "--dry-run", "--plan-out", str(absent), stdin=original))
        self.assertEqual(no_op["plan_state"], "not-needed")
        self.assertIsNone(no_op["plan_file"])
        self.assertIsNone(no_op["plan_token"])
        self.assertFalse(absent.exists())
        conflicting = {**base_task(), "result": "Different result without resolving the existing task."}
        process = run_tool(self.root, "learn", "--file", "-", "--dry-run", "--plan-out", str(absent),
            stdin=json.dumps({"task": conflicting, "items": []}), check=False)
        blocked = json_output(process)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(blocked["plan_state"], "blocked")
        self.assertEqual(blocked["error_code"], "plan-not-applicable")
        self.assertIsNone(blocked["plan_file"])
        self.assertFalse(absent.exists())

    def test_concurrent_plan_export_publishes_one_complete_file(self):
        destination = self.root.parent / "concurrent.token"
        values = [json.dumps({"task": {**base_task(f"Concurrent {number}"), "result": f"Completed fixture {number}."}, "items": []})
                  for number in range(6)]
        def export(raw):
            return run_tool(self.root, "learn", "--file", "-", "--dry-run", "--plan-out", str(destination), stdin=raw, check=False)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(export, values))
        winners = [(index, json_output(value)) for index, value in enumerate(results) if value.returncode == 0]
        self.assertEqual(len(winners), 1, [value.stdout for value in results])
        winner, preview = winners[0]
        self.assertEqual(destination.read_text().strip(), preview["plan_token"])
        for result in results:
            if result.returncode:
                self.assertEqual(json_output(result)["error_code"], "plan-file-exists")
        applied = json_output(run_tool(self.root, "learn", "--file", "-", "--plan-file", str(destination), stdin=values[winner]))
        self.assertTrue(applied["ok"])
        self.assertEqual(list(destination.parent.glob(".concurrent.token.*")), [])

    def test_external_references_survive_updates_and_consolidation_without_auto_merge(self):
        first = base_task("First logical task")
        first["external_refs"] = [self.ref]
        created = self.learn(first)
        update = json_output(run_tool(self.root, "template", "--task-id", created["task_id"]))["task"]
        self.assertEqual(update["external_refs"], [self.ref])
        update.pop("external_refs")  # Older callers cannot accidentally erase the relationship.
        update["result"] = "An additional failure case is now covered."
        updated = self.learn(update)
        again = self.learn(update)
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["task_revision"], updated["task_revision"])
        second = base_task("Another logical task")
        second["new_task_reason"] = "Separately accepted input normalization requirement."
        another_ref = {"system": "tracker", "id": "ORD-18"}
        second["external_refs"] = [another_ref, self.ref]
        duplicate = self.learn(second)
        before = tree_digest(self.root)
        matches = json_output(run_tool(self.root, "brief", "--task", "search", "--limit", "1", "--external-ref",
            "github=" + self.ref["id"], "--format", "json"))
        self.assertEqual({row["id"] for row in matches["related_tasks"]}, {created["task_id"], duplicate["task_id"]})
        self.assertTrue(matches["external_task_matches"]["multiple_candidates"])
        self.assertFalse(matches["external_task_matches"]["auto_merge"])
        self.assertEqual(tree_digest(self.root), before)
        raw = json.dumps({"canonical_task_id": created["task_id"], "expected_revision": updated["task_revision"],
            "duplicates": [{"id": duplicate["task_id"], "expected_revision": 1}],
            "reason": "Both notes describe the same accepted delivery after review."})
        preview = json_output(run_tool(self.root, "consolidate", "--file", "-", "--dry-run", stdin=raw))
        run_tool(self.root, "consolidate", "--file", "-", "--plan-token", preview["plan_token"], stdin=raw)
        canonical = json_output(run_tool(self.root, "task-files", "--task-id", created["task_id"], "--format", "json"))
        self.assertEqual(canonical["external_refs"], [self.ref, another_ref])
        archived = json_output(run_tool(self.root, "task-files", "--task-id", duplicate["task_id"], "--format", "json"))
        self.assertEqual(archived["external_refs"], [self.ref, another_ref])
        self.assertEqual(archived["canonical_task_id"], created["task_id"])
        matches = json_output(run_tool(self.root, "brief", "--task", "search", "--external-ref",
            "tracker=ORD-18", "--format", "json"))
        self.assertEqual([row["id"] for row in matches["related_tasks"]], [created["task_id"]])

    def test_external_references_reject_ambiguous_or_malformed_identifiers(self):
        before = tree_digest(self.root)
        for refs in ({}, [{"system": "github", "id": "17"}], [{"system": "github", "id": "https://github.com/a/b/pull/1"}],
                     [{"system": "github", "id": "https://github.com/a/b/issues/1?x=y"}],
                     [{"system": "tracker", "id": 17}], [{"system": "tracker", "id": "hello\nworld"}],
                     [{"system": "github", "id": self.ref["id"], "extra": "ignored"}]):
            with self.subTest(refs=refs):
                task = {**base_task(), "external_refs": refs}
                result = run_tool(self.root, "learn", "--file", "-", "--dry-run", check=False,
                    stdin=json.dumps({"task": task, "items": []}))
                self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(tree_digest(self.root), before)

    def test_shared_external_identity_requires_an_explicit_new_task_reason(self):
        existing = self.learn({**base_task(), "external_refs": [self.ref]})
        other = {**base_task("Unrelated title"), "paths": [], "symbols": [], "external_refs": [self.ref]}
        result = run_tool(self.root, "learn", "--file", "-", "--dry-run", check=False,
            stdin=json.dumps({"task": other, "items": []}))
        preview = json_output(result)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(preview["task_candidates"][0]["task_id"], existing["task_id"])
        self.assertEqual(preview["task_candidates"][0]["reasons"], ["same-external-reference"])
        self.assertFalse(preview["apply_allowed"])

    def test_bootstrap_advertises_additive_capabilities_without_rebuilding(self):
        before = tree_digest(self.root)
        report = self.bootstrap.check_install(self.root)
        self.assertTrue({"task-external-refs", "exclusive-plan-file", "review-actions"} <= set(report["capabilities"]))
        self.assertEqual(tree_digest(self.root), before)


if __name__ == "__main__":
    unittest.main()
