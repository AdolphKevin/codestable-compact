from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import PACKAGE_ROOT, SHARED_TOOL, bootstrap_module, knowledge_module, tree_digest


SELF_SCOPE = {"repository": "self", "path": "commerce/checkout.py", "symbol": "create_checkout"}


def future_use(constraint: str) -> list[dict[str, str]]:
    return [
        {"change": "replace the payment adapter", "actor": "commerce maintainer", "constraint": constraint},
        {"change": "change checkout persistence", "actor": "storage maintainer", "constraint": constraint},
    ]


def evidence(supports: str, kind: str = "test") -> list[dict[str, str]]:
    return [
        {
            "kind": kind,
            "artifact": "tests.test_checkout.CheckoutTests.test_atomic_checkout",
            "result": "the anonymous commerce integration check passed",
            "supports": supports,
        }
    ]


def task(title: str = "Evolve anonymous checkout") -> dict:
    return {
        "title": title,
        "kind": "task",
        "status": "completed",
        "request": "Change an anonymous commerce backend without losing checkout invariants.",
        "summary": "Kept the checkout boundary and verified it with an anonymous fixture.",
        "result": "The synthetic checkout remains consistent.",
        "scopes": [SELF_SCOPE],
        "tags": ["checkout"],
        "verification": ["python3 -m unittest tests.test_checkout"],
        "knowledge_summary": "Captured only stable constraints supported by the anonymous fixture.",
        "source": {"fixture": "anonymous-commerce"},
        "knowledge_use": [],
    }


def card(category: str, title: str, conclusion: str, **overrides: object) -> dict:
    value: dict[str, object] = {
        "category": category,
        "title": title,
        "knowledge": conclusion,
        "rationale": "The boundary prevents a partial checkout state.",
        "future_use": future_use(conclusion),
        "scopes": [SELF_SCOPE],
        "tags": ["checkout"],
        "confidence": "verified",
        "evidence": evidence(conclusion),
        "status": "current",
    }
    value.update(overrides)
    return value


class GovernanceAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bootstrap = bootstrap_module()
        cls.tool = knowledge_module()
        cls.eval_cases = json.loads((PACKAGE_ROOT / "tests" / "fixtures" / "retrieval_eval.json").read_text())

    def make_root(self, temporary: str, configure_topic: bool = False) -> tuple[Path, dict]:
        root = Path(temporary)
        self.bootstrap.install(root, upgrade=False)
        source = root / "commerce" / "checkout.py"
        source.parent.mkdir(parents=True)
        source.write_text("def create_checkout():\n    return 'created'\n", encoding="utf-8")
        test_file = root / "tests" / "test_checkout.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "import unittest\n\nclass CheckoutTests(unittest.TestCase):\n"
            "    def test_atomic_checkout(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        config_path = root / ".codestable" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if configure_topic:
            config["wiki"]["topics"] = {
                "checkout-flow": {
                    "label": "Checkout flow",
                    "summary": "Links current checkout boundary cards without copying their conclusions.",
                    "aliases": [],
                    "replaces": [],
                }
            }
            config["wiki"]["topic_governance"]["mode"] = "manual"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        config = self.tool.load_config(root)
        self.tool.rebuild_indexes(root, config)
        return root, config

    def seed_retrieval_cards(self, root: Path, config: dict) -> tuple[str, str]:
        exact = card(
            "architecture",
            "Checkout adapter boundary",
            "Checkout orchestration depends on an adapter rather than a concrete payment client.",
            topics=["checkout-flow"],
        )
        noisy = card(
            "requirements",
            "Payment handoff performance compatibility security transaction interface acceptance architecture",
            "Payment handoff performance compatibility security transaction interface acceptance architecture must be reviewed.",
            scopes=[{"repository": "self", "path": "commerce/noisy.py", "symbol": "lexical_noise"}],
            topics=["checkout-flow"],
        )
        learned = self.tool.learn(root, config, {"task": task(), "items": [exact, noisy]})
        return learned["created_cards"][0]["id"], learned["created_cards"][1]["id"]

    def git_baseline(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Anonymous Fixture"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "anonymous baseline"], cwd=root, check=True)

    def test_brief_keeps_summaries_outside_card_quota_and_exact_scope_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary, configure_topic=True)
            exact_id, _ = self.seed_retrieval_cards(root, config)
            config["brief"]["max_items"] = 1
            summary = root / ".codestable" / "wiki" / "architecture" / "README.md"
            summary.write_text(
                "# Architecture\n\n<!-- codestable:canonical:start -->\n"
                "Payment handoff performance compatibility security transaction interface acceptance architecture summary.\n"
                "<!-- codestable:canonical:end -->\n",
                encoding="utf-8",
            )
            brief = self.tool.selected_brief_payload(
                root,
                config,
                "Payment handoff performance compatibility security transaction interface acceptance architecture",
                ["commerce/checkout.py"],
                ["create_checkout"],
                None,
                False,
                ["checkout-flow"],
                [],
            )
            self.assertEqual([item["id"] for item in brief["knowledge"]], [exact_id])
            self.assertEqual(brief["knowledge"][0]["match_precedence"], 6)
            kinds = {reason["kind"] for reason in brief["knowledge"][0]["match_reasons"]}
            self.assertIn("exact-path", kinds)
            self.assertTrue(brief["category_summaries"])
            self.assertTrue(all(item["type"] == "canonical-page" for item in brief["category_summaries"]))
            self.assertTrue(all(item["status"] == "navigation" for item in brief["category_summaries"]))
            self.assertTrue(all(item["confidence"] == "not-applicable" for item in brief["category_summaries"]))
            self.assertEqual(brief["coverage"]["architecture"], {"available": 1, "matched": 1})
            self.assertEqual(brief["receipt"]["claim"], "displayed-only")
            self.assertEqual(len(brief["receipt"]["knowledge_state"]), 64)
            self.assertEqual(brief["receipt"]["generated_at"], brief["generated_at"])
            self.assertEqual(brief["receipt"]["displayed_cards"][0]["revision"], 1)
            self.assertEqual(len(brief["receipt"]["displayed_cards"][0]["content_hash"]), 64)

    def test_unknown_brief_topic_warns_suggests_and_preserves_other_query_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary, configure_topic=True)
            exact_id, _ = self.seed_retrieval_cards(root, config)
            before = tree_digest(root / ".codestable")
            process = subprocess.run(
                [
                    sys.executable,
                    str(SHARED_TOOL),
                    "--root",
                    str(root),
                    "brief",
                    "--task",
                    "Review the anonymous checkout adapter",
                    "--topic",
                    "checkout-lookup",
                    "--path",
                    "commerce/checkout.py",
                    "--symbol",
                    "create_checkout",
                    "--scope",
                    "self:commerce/checkout.py#create_checkout",
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["topics"], [])
            self.assertEqual(payload["ignored_topics"], ["checkout-lookup"])
            warning = payload["topic_resolution"]["warnings"][0]
            self.assertEqual(warning["code"], "brief.topic.unknown")
            self.assertIn("checkout-flow", [value["name"] for value in warning["suggestions"]])
            self.assertEqual(payload["knowledge"][0]["id"], exact_id)
            reason_kinds = {value["kind"] for value in payload["knowledge"][0]["match_reasons"]}
            self.assertIn("exact-path", reason_kinds)
            self.assertIn("exact-symbol", reason_kinds)
            self.assertEqual(payload["receipt"]["requested_topics"], ["checkout-lookup"])
            self.assertEqual(payload["receipt"]["ignored_topics"], ["checkout-lookup"])
            strict_item = card(
                "interfaces",
                "Checkout write topic remains strict",
                "Durable topic metadata must use a configured canonical name or alias.",
                topics=["checkout-lookup"],
            )
            with self.assertRaisesRegex(self.tool.KnowledgeError, "unknown knowledge topics"):
                self.tool.learn(
                    root,
                    config,
                    {"task": task("Reject an unknown durable topic"), "items": [strict_item]},
                    dry_run=True,
                )
            self.assertEqual(before, tree_digest(root / ".codestable"))

    def test_topics_list_is_read_only_and_exposes_canonical_names_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary, configure_topic=True)
            config_path = root / ".codestable" / "config.json"
            raw_config = json.loads(config_path.read_text(encoding="utf-8"))
            raw_config["wiki"]["topics"]["checkout-flow"]["aliases"] = ["checkout-support"]
            config_path.write_text(json.dumps(raw_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            config = self.tool.load_config(root)
            self.seed_retrieval_cards(root, config)
            before = tree_digest(root / ".codestable")
            payload = self.tool.topics_list_payload(root, config)
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["topics"][0]["name"], "checkout-flow")
            self.assertEqual(payload["topics"][0]["aliases"], ["checkout-support"])
            self.assertEqual(payload["topics"][0]["current_cards"], 2)
            self.assertIn("architecture", payload["topics"][0]["categories"])
            rendered = self.tool.render_topics_list_text(payload)
            self.assertIn("`checkout-flow`", rendered)
            self.assertIn("`checkout-support`", rendered)
            self.assertEqual(before, tree_digest(root / ".codestable"))

    def test_doctor_treats_release_version_drift_as_informational(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            (root / ".codestable" / "VERSION").write_text("0.0.0\n", encoding="utf-8")
            result = self.tool.doctor(root, config)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["runtime_alignment"]["ok"])
            self.assertEqual(result["runtime_alignment"]["runtime_source"], "skill")
            self.assertFalse(result["runtime_alignment"]["versions_aligned"])
            self.assertEqual(result["runtime_alignment"]["version_status"], "compatible-release-drift")
            self.assertIn("optional", result["runtime_alignment"]["version_action"])
            self.assertFalse(result["runtime_alignment"]["distribution_reference_checked"])
            self.assertNotIn("runtime.data.incompatible", {value["code"] for value in result["warnings"]})

    def test_conclusion_similarity_is_deterministic_and_handles_empty_text(self) -> None:
        self.assertEqual(self.tool.conclusion_similarity("", "Checkout uses an adapter."), 0.0)
        self.assertEqual(self.tool.conclusion_similarity("Checkout uses an adapter.", "Checkout uses an adapter."), 1.0)
        self.assertAlmostEqual(self.tool.conclusion_similarity("alpha beta", "beta gamma"), 1 / 3)

    def test_anonymous_retrieval_eval_set_reports_machine_readable_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary, configure_topic=True)
            self.seed_retrieval_cards(root, config)
            for case in self.eval_cases:
                with self.subTest(case=case["name"]):
                    brief = self.tool.selected_brief_payload(
                        root,
                        config,
                        case["task"],
                        case["paths"],
                        case["symbols"],
                        None,
                        False,
                        case["topics"],
                        [],
                    )
                    match = next(item for item in brief["knowledge"] if item["title"] == case["expected_title"])
                    self.assertIn(case["expected_reason"], {value["kind"] for value in match["match_reasons"]})

    def test_unedited_template_and_generic_future_scenarios_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            with self.assertRaisesRegex(self.tool.KnowledgeError, "placeholder|generic"):
                self.tool.learn(root, config, self.tool.template_payload("Anonymous task", "task"), dry_run=True)
            duplicate = card("architecture", "Checkout boundary", "Checkout state is atomic.")
            duplicate["future_use"] = [future_use("Checkout state is atomic.")[0]] * 2
            with self.assertRaisesRegex(self.tool.KnowledgeError, "two concrete|distinct"):
                self.tool.learn(root, config, {"task": task(), "items": [duplicate]}, dry_run=True)
            missing_field = card("architecture", "Checkout evidence", "Checkout evidence is structured.")
            missing_field["evidence"] = [{"kind": "test", "artifact": "tests.test_checkout", "result": "passed"}]
            with self.assertRaisesRegex(self.tool.KnowledgeError, "requires artifact, result, and supports"):
                self.tool.learn(root, config, {"task": task(), "items": [missing_field]}, dry_run=True)

    def test_accepted_decision_authority_is_distinct_from_verified_behavior(self) -> None:
        accepted = card(
            "decisions",
            "Keep checkout local",
            "Checkout remains in one local transaction while its records share a database.",
            context="The anonymous records share a database.",
            alternatives=["distributed transaction", "post-commit repair"],
            consequences=["storage separation requires a new review"],
            confidence="accepted",
            evidence=evidence("The local transaction boundary is explicitly accepted.", "accepted-decision"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            result = self.tool.learn(root, config, {"task": task(), "items": [accepted]}, dry_run=True)
            self.assertTrue(result["apply_allowed"])
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            verified = dict(accepted)
            verified["confidence"] = "verified"
            with self.assertRaisesRegex(self.tool.KnowledgeError, "accepted-decision record alone"):
                self.tool.learn(root, config, {"task": task(), "items": [verified]}, dry_run=True)

    def test_knowledge_use_binds_the_card_revision_and_effect_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            learned = self.tool.learn(
                root,
                config,
                {"task": task(), "items": [card("architecture", "Checkout boundary", "Checkout uses an adapter boundary.")]},
            )
            card_id = learned["created_cards"][0]["id"]
            use_task = task("Review checkout boundary")
            use_task["knowledge_use"] = [
                {
                    "card_id": card_id,
                    "card_revision": 2,
                    "use": "tested",
                    "detail": "The card caused the review to retain the adapter boundary and add an adapter test.",
                    "evidence": [
                        {
                            "kind": "test",
                            "artifact": "tests.test_checkout.CheckoutTests.test_atomic_checkout",
                            "result": "the adapter-path check passed",
                            "supports": "checkout orchestration still uses the adapter boundary",
                        }
                    ],
                }
            ]
            with self.assertRaisesRegex(self.tool.KnowledgeError, "revision changed"):
                self.tool.learn(root, config, {"task": use_task, "items": []}, dry_run=True)
            use_task["knowledge_use"][0]["card_revision"] = 1
            applied = self.tool.learn(root, config, {"task": use_task, "items": []})
            note = (root / applied["task_note"]).read_text(encoding="utf-8")
            self.assertIn("revision 1", note)
            self.assertIn("adapter-path check passed", note)

    def test_task_update_preserves_historical_knowledge_use_after_card_revision_advances(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            learned = self.tool.learn(
                root,
                config,
                {
                    "task": task("Accept checkout boundary"),
                    "items": [
                        card(
                            "architecture",
                            "Checkout boundary",
                            "Checkout uses an adapter boundary.",
                        )
                    ],
                },
            )
            card_id = learned["created_cards"][0]["id"]
            use_task = task("Apply checkout boundary")
            use_task["knowledge_use"] = [
                {
                    "card_id": card_id,
                    "card_revision": 1,
                    "use": "tested",
                    "detail": "The boundary caused the implementation to retain the adapter and add its regression test.",
                    "evidence": [
                        {
                            "kind": "test",
                            "artifact": "tests.test_checkout.CheckoutTests.test_atomic_checkout",
                            "result": "the adapter-path check passed",
                            "supports": "checkout orchestration still uses the adapter boundary",
                        }
                    ],
                }
            ]
            use_result = self.tool.learn(root, config, {"task": use_task, "items": []})
            revised = card(
                "architecture",
                "Checkout boundary",
                "Checkout uses an adapter boundary.",
                operation="update",
                card_id=card_id,
                expected_revision=1,
                scopes=[
                    {"repository": "self", "path": "commerce/checkout.py", "symbol": "create_checkout"},
                    {"repository": "self", "path": "tests/test_checkout.py", "symbol": "test_atomic_checkout"},
                ],
            )
            revision_task = task("Refresh checkout boundary scope")
            revision_task["new_task_reason"] = "This task only refreshes the durable card scope after adding its regression test."
            self.tool.learn(root, config, {"task": revision_task, "items": [revised]})

            rewritten_history = dict(use_task)
            rewritten_history.update(
                {
                    "id": use_result["task_id"],
                    "update_existing": True,
                    "expected_revision": 1,
                    "summary": "Attempted to rewrite historical use evidence.",
                }
            )
            rewritten_history["knowledge_use"] = [dict(use_task["knowledge_use"][0])]
            rewritten_history["knowledge_use"][0]["detail"] = "Changed the old evidence after the card advanced."
            with self.assertRaisesRegex(self.tool.KnowledgeError, "revision changed"):
                self.tool.learn(root, config, {"task": rewritten_history, "items": []}, dry_run=True)

            explicit_update = dict(use_task)
            explicit_update.update(
                {
                    "id": use_result["task_id"],
                    "update_existing": True,
                    "expected_revision": 1,
                    "summary": "Retained the adapter boundary and expanded the final verification.",
                }
            )
            updated = self.tool.learn(root, config, {"task": explicit_update, "items": []})
            omitted_update = dict(explicit_update)
            omitted_update.update({"expected_revision": 2, "summary": "Retained the complete final verification."})
            omitted_update.pop("knowledge_use")
            final = self.tool.learn(root, config, {"task": omitted_update, "items": []})
            metadata, note, _ = self.tool.read_markdown(root / final["task_note"])

            self.assertEqual(updated["task_revision"], 2)
            self.assertEqual(final["task_revision"], 3)
            self.assertEqual(metadata["knowledge_use"][0]["card_revision"], 1)
            self.assertIn("revision 1", note)

    def test_task_update_template_prefills_current_snapshot_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            existing = task("Template existing task")
            existing["verification"] = [
                "python3 -m unittest tests.test_checkout",
                "python3 scripts/validate_release.py --source .",
            ]
            created = self.tool.learn(root, config, {"task": existing, "items": []})

            payload = self.tool.task_update_template(root, config, created["task_id"])

            self.assertEqual(payload["task"]["id"], created["task_id"])
            self.assertTrue(payload["task"]["update_existing"])
            self.assertEqual(payload["task"]["expected_revision"], 1)
            self.assertEqual(payload["task"]["kind"], "task")
            self.assertEqual(payload["task"]["summary"], task("Template existing task")["summary"])
            self.assertEqual(payload["task"]["verification"], existing["verification"])
            self.assertEqual(payload["items"], [])

    def test_compact_learn_is_default_full_is_explicit_and_templates_follow_knowledge_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            existing = task("CLI template task")
            created = self.tool.learn(root, config, {"task": existing, "items": []})
            template_process = subprocess.run(
                [
                    sys.executable,
                    str(SHARED_TOOL),
                    "--root",
                    str(root),
                    "template",
                    "--task-id",
                    created["task_id"],
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            template = json.loads(template_process.stdout)
            card_template_process = subprocess.run(
                [
                    sys.executable,
                    str(SHARED_TOOL),
                    "--root",
                    str(root),
                    "template",
                    "--title",
                    "CLI knowledge disposition",
                    "--card-category",
                    "architecture",
                    "--card-category",
                    "decisions",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            card_template = json.loads(card_template_process.stdout)
            learning = root / "compact-learning.json"
            compact_task = task("CLI compact learn")
            compact_task["new_task_reason"] = "This fixture validates a separate CLI output mode."
            learning.write_text(
                json.dumps({"task": compact_task, "items": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            learn_process = subprocess.run(
                [
                    sys.executable,
                    str(SHARED_TOOL),
                    "--root",
                    str(root),
                    "learn",
                    "--file",
                    str(learning),
                    "--dry-run",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            full_process = subprocess.run(
                [
                    sys.executable,
                    str(SHARED_TOOL),
                    "--root",
                    str(root),
                    "learn",
                    "--file",
                    str(learning),
                    "--dry-run",
                    "--full",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            plan = json.loads(learn_process.stdout)
            full_plan = json.loads(full_process.stdout)

            card_template["task"].update(
                {
                    "request": "Record durable checkout constraints without task-size classification.",
                    "summary": "Prepared one architecture fact and one accepted decision.",
                    "result": "The task-level scope is inherited by both durable cards.",
                    "scopes": [SELF_SCOPE],
                    "verification": ["python3 -m unittest tests.test_checkout"],
                    "knowledge_summary": "Added architecture and decision cards with explicit evidence.",
                }
            )
            card_template["items"][0].update(
                {
                    "title": "Checkout scope inheritance",
                    "knowledge": "Durable cards inherit the task scope unless they declare a narrower boundary.",
                    "rationale": "The task already names the verified implementation boundary.",
                    "implications": ["A narrower card must override the inherited task scope explicitly."],
                    "future_use": future_use("Keep card scope aligned with the task unless it is intentionally narrower."),
                    "evidence": evidence("The architecture card resolves to the task-level checkout scope."),
                }
            )
            card_template["items"][1].update(
                {
                    "title": "Knowledge disposition drives card scaffolding",
                    "knowledge": "Card templates are added by knowledge category, not by subjective task size.",
                    "context": "Task-size labels would introduce an avoidable classification decision.",
                    "rationale": "Knowledge disposition is observable from the final reusable conclusions.",
                    "implications": ["Every task keeps the same validation and traceability gates."],
                    "alternatives": ["Classify every task as small, medium, or large before work starts."],
                    "consequences": ["Only tasks with durable conclusions carry card fields."],
                    "future_use": future_use("Do not weaken gates based on a task-size label."),
                    "evidence": [
                        {
                            "kind": "accepted-decision",
                            "artifact": "CodeStable template contract fixture",
                            "result": "The fixture explicitly chooses knowledge disposition over task size.",
                            "supports": "Card scaffolding is selected by category only after a durable conclusion exists.",
                        }
                    ],
                }
            )
            scaffold_plan = self.tool.learn(root, config, card_template, dry_run=True)

            self.assertEqual(template["task"]["id"], created["task_id"])
            self.assertTrue(plan["plan_token"])
            self.assertEqual(plan["output_mode"], "compact")
            self.assertNotIn("verified", plan["reference_check"])
            self.assertIn("verified_count", plan["reference_check"])
            self.assertIn("verified", full_plan["reference_check"])
            self.assertNotIn("output_mode", full_plan)
            self.assertLess(len(learn_process.stdout), len(full_process.stdout))
            self.assertEqual(
                [item["category"] for item in card_template["items"]],
                ["architecture", "decisions"],
            )
            self.assertTrue(scaffold_plan["plan_token"])
            self.assertEqual(len(scaffold_plan["created_cards"]), 2)

    def test_default_compact_output_stays_bounded_with_many_verified_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _ = self.make_root(temporary)
            scopes: list[dict[str, str]] = []
            for index in range(80):
                relative = f"commerce/reference_{index:02d}.py"
                path = root / relative
                path.write_text(f"REFERENCE_{index} = True\n", encoding="utf-8")
                scopes.append({"repository": "self", "path": relative, "symbol": ""})
            learning = root / "many-references.json"
            many = task("Verify compact output bounds")
            many["scopes"] = scopes
            learning.write_text(json.dumps({"task": many, "items": []}, ensure_ascii=False), encoding="utf-8")
            common = [
                sys.executable,
                str(SHARED_TOOL),
                "--root",
                str(root),
                "learn",
                "--file",
                str(learning),
                "--dry-run",
            ]

            compact_process = subprocess.run(common, text=True, capture_output=True, check=True)
            full_process = subprocess.run([*common, "--full"], text=True, capture_output=True, check=True)
            compact = json.loads(compact_process.stdout)
            full = json.loads(full_process.stdout)

            self.assertEqual(compact["reference_check"]["verified_count"], 80)
            self.assertEqual(len(full["reference_check"]["verified"]), 80)
            self.assertNotIn("verified", compact["reference_check"])
            self.assertLess(len(compact_process.stdout) * 3, len(full_process.stdout))

    def test_anonymous_v3_changed_design_reuses_boundary_and_adds_orthogonal_outbox_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            design = root / "design" / "notification-v3.md"
            design.parent.mkdir(parents=True)
            design.write_text(
                "Business service selects recipients; gateways and mobile adapters only transport notifications.\n",
                encoding="utf-8",
            )
            boundary = card(
                "decisions",
                "Business service owns notification semantics",
                "The business service selects notification recipients; transport gateways only route to explicit targets.",
                context="A gateway previously mixed connection routing with mute and internal-note business rules.",
                alternatives=["keep all recipient rules in every transport gateway"],
                consequences=["new transport adapters receive explicit targets and do not duplicate business filtering"],
                confidence="accepted",
                evidence=[
                    {
                        "kind": "accepted-decision",
                        "artifact": "design/notification-v3.md",
                        "result": "the boundary is explicitly accepted in the anonymous design fixture",
                        "supports": "recipient selection remains in the business service",
                    }
                ],
            )
            first = self.tool.learn(root, config, {"task": task("Accept notification boundary"), "items": [boundary]})
            boundary_id = first["created_cards"][0]["id"]
            v3 = task("Add muted, internal-note, mobile, and retry behavior")
            v3["new_task_reason"] = "This is a separate accepted notification delivery change, not a continuation of the boundary record."
            v3["knowledge_use"] = [
                {
                    "card_id": boundary_id,
                    "card_revision": 1,
                    "use": "changed-design",
                    "detail": "The accepted boundary moved mute and internal-note filtering out of the gateway and kept mobile as a transport adapter.",
                    "before": "Put mute, internal-note, and mobile recipient rules in the realtime gateway.",
                    "after": "The business service constructs explicit targets; realtime and mobile adapters only transport them.",
                    "evidence": [
                        {
                            "kind": "design",
                            "artifact": "design/notification-v3.md",
                            "result": "the public design assigns recipient selection to the business service",
                            "supports": "the gateway has no mute or internal-note business branching",
                        }
                    ],
                }
            ]
            outbox = card(
                "decisions",
                "Persist notifications through a transactional outbox",
                "Business records and pending notifications share one transaction; a dispatcher retries and consumers deduplicate by event ID.",
                context="Direct post-commit publishing can lose a notification if the process exits before a retry.",
                alternatives=["direct publish with in-memory retry", "distributed two-phase commit"],
                consequences=["dispatch is at least once", "consumers require event-ID idempotency", "operations monitor outbox lag"],
                evidence=[
                    {
                        "kind": "test",
                        "artifact": "tests.test_checkout.CheckoutTests.test_atomic_checkout",
                        "result": "the anonymous atomic write check passed",
                        "supports": "business state and pending notification share one commit outcome",
                    }
                ],
            )
            plan = self.tool.learn(root, config, {"task": v3, "items": [outbox]}, dry_run=True)
            applied = self.tool.learn(
                root, config, {"task": v3, "items": [outbox]}, plan_token=plan["plan_token"]
            )
            note = (root / applied["task_note"]).read_text(encoding="utf-8")
            self.assertIn("Put mute, internal-note", note)
            self.assertIn("business service constructs explicit targets", note)
            new_id = applied["created_cards"][0]["id"]
            records = self.tool.scan_existing_records(
                self.tool.wiki_root(root, config), self.tool.configured_categories(config)
            )[0]
            self.assertEqual(records[new_id][1]["supersedes"], [])
            self.assertEqual(records[boundary_id][1]["status"], "current")

    def test_topic_modes_are_explicit_and_manual_empty_is_not_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            disabled = self.tool.doctor(root, config)
            self.assertEqual(disabled["topic_governance"]["mode"], "disabled")
            self.assertFalse(any(value["code"] == "topic.manual.unconfigured" for value in disabled["warnings"]))
            config["wiki"]["topic_governance"]["mode"] = "manual"
            manual = self.tool.doctor(root, config)
            self.assertTrue(any(value["code"] == "topic.manual.unconfigured" for value in manual["warnings"]))
            self.tool.learn(
                root, config, {"task": task(), "items": [card("architecture", "Checkout boundary", "Checkout uses an adapter.")]}
            )
            config["wiki"]["topic_governance"] = {
                "mode": "required",
                "minimum_coverage": 1.0,
                "review_max_age_days": 180,
            }
            required = self.tool.doctor(root, config)
            self.assertTrue(any(value["code"] == "topic.required.coverage" for value in required["warnings"]))
            governance = self.tool.governance_audit(root, config)
            self.assertEqual(governance["topic_status"], "incomplete")

    def test_topic_suggestions_are_deterministic_read_only_and_structured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            self.tool.learn(
                root,
                config,
                {
                    "task": task(),
                    "items": [
                        card("architecture", "Checkout boundary", "Checkout orchestration uses an adapter."),
                        card("acceptance", "Checkout acceptance", "Checkout failure leaves no partial record."),
                    ],
                },
            )
            before = tree_digest(root / ".codestable")
            first = self.tool.topics_suggest_payload(root, config)
            second = self.tool.topics_suggest_payload(root, config)
            self.assertEqual(first, second)
            self.assertEqual(before, tree_digest(root / ".codestable"))
            checkout = next(value for value in first["suggestions"] if value["name"] == "checkout")
            self.assertEqual(checkout["basis"], "shared-tag")
            self.assertGreaterEqual(len(checkout["categories"]), 2)

    def test_topics_update_uses_dry_run_token_revision_history_and_alias_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            learned = self.tool.learn(
                root,
                config,
                {
                    "task": task(),
                    "items": [
                        card("architecture", "Checkout boundary", "Checkout orchestration uses an adapter."),
                        card("acceptance", "Checkout acceptance", "Checkout failure leaves no partial record."),
                    ],
                },
            )
            card_ids = [value["id"] for value in learned["created_cards"]]
            update = {
                "mode": "manual",
                "minimum_coverage": 0.5,
                "upsert_topics": [
                    {
                        "name": "checkout-flow",
                        "label": "Checkout flow",
                        "summary": "Navigates current checkout constraints across categories.",
                        "aliases": [],
                        "replaces": [],
                    }
                ],
                "assignments": [
                    {"card_id": card_id, "expected_revision": 1, "topics": ["checkout-flow"]}
                    for card_id in card_ids
                ],
            }
            before = tree_digest(root / ".codestable")
            plan = self.tool.topics_update(root, config, update, dry_run=True)
            self.assertEqual(before, tree_digest(root / ".codestable"))
            self.assertEqual(len(plan["updated_cards"]), 2)
            applied = self.tool.topics_update(root, config, update, plan_token=plan["plan_token"])
            self.assertFalse(applied["dry_run"])
            config = self.tool.load_config(root)
            for card_id in card_ids:
                _, metadata, _ = self.tool.scan_existing_records(
                    self.tool.wiki_root(root, config), self.tool.configured_categories(config)
                )[0][card_id]
                self.assertEqual(metadata["revision"], 2)
                self.assertEqual(metadata["topics"], ["checkout-flow"])
                self.assertEqual(metadata["topic_history"][0]["topics"], [])
            with self.assertRaisesRegex(self.tool.KnowledgeError, "changed after topics dry-run"):
                self.tool.topics_update(root, config, update, plan_token=plan["plan_token"])

            rename = {
                "upsert_topics": [
                    {
                        "name": "purchase-flow",
                        "label": "Purchase flow",
                        "summary": "Navigates the renamed checkout topic while preserving old card metadata.",
                        "aliases": [],
                        "replaces": ["checkout-flow"],
                    }
                ],
                "assignments": [],
            }
            rename_plan = self.tool.topics_update(root, config, rename, dry_run=True)
            self.tool.topics_update(root, config, rename, plan_token=rename_plan["plan_token"])
            config = self.tool.load_config(root)
            self.assertNotIn("checkout-flow", config["wiki"]["topics"])
            self.assertEqual(self.tool.topic_aliases(config)["checkout-flow"], "purchase-flow")
            self.assertEqual(config["wiki"]["topic_history"][-1]["replaced_by"], "purchase-flow")
            topics_index = (root / ".codestable" / "wiki" / "TOPICS.md").read_text(encoding="utf-8")
            self.assertIn("Purchase flow", topics_index)

    def test_topics_update_rolls_back_a_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            learned = self.tool.learn(
                root, config, {"task": task(), "items": [card("architecture", "Checkout boundary", "Checkout uses an adapter.")]}
            )
            update = {
                "mode": "manual",
                "upsert_topics": [
                    {
                        "name": "checkout-flow",
                        "label": "Checkout flow",
                        "summary": "Navigates the current anonymous checkout boundary.",
                        "aliases": [],
                        "replaces": [],
                    }
                ],
                "assignments": [
                    {"card_id": learned["created_cards"][0]["id"], "expected_revision": 1, "topics": ["checkout-flow"]}
                ],
            }
            plan = self.tool.topics_update(root, config, update, dry_run=True)
            before = tree_digest(root / ".codestable")
            original = self.tool.atomic_write_text
            failed = False

            def fail_after_config(path: Path, content: str) -> None:
                nonlocal failed
                original(path, content)
                if not failed and path.name == "config.json" and path.parent.name == ".codestable":
                    failed = True
                    raise OSError("synthetic topic write failure")

            self.tool.atomic_write_text = fail_after_config
            try:
                with self.assertRaisesRegex(OSError, "synthetic topic write failure"):
                    self.tool.topics_update(root, config, update, plan_token=plan["plan_token"])
            finally:
                self.tool.atomic_write_text = original
            self.assertEqual(before, tree_digest(root / ".codestable"))
            self.assertFalse((root / ".codestable" / "wiki" / ".write.lock").exists())

    def test_topics_update_rejects_an_active_writer_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            update = {
                "mode": "manual",
                "upsert_topics": [
                    {
                        "name": "checkout-flow",
                        "label": "Checkout flow",
                        "summary": "Navigates current anonymous checkout constraints.",
                        "aliases": [],
                        "replaces": [],
                    }
                ],
                "assignments": [],
            }
            plan = self.tool.topics_update(root, config, update, dry_run=True)
            lock = self.tool.acquire_lock(root.resolve(), self.tool.wiki_root(root, config))
            try:
                with self.assertRaisesRegex(self.tool.KnowledgeError, "writer pid .* is active"):
                    self.tool.topics_update(root, config, update, plan_token=plan["plan_token"])
            finally:
                lock.unlink(missing_ok=True)

    def test_audit_is_read_only_passes_reviewed_fixture_and_disclaims_business_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            self.tool.learn(
                root,
                config,
                {
                    "task": task(),
                    "items": [card("transaction-boundaries", "Atomic checkout", "Checkout records share one commit point.")],
                },
            )
            cards = self.tool.scan_existing_records(
                self.tool.wiki_root(root, config), self.tool.configured_categories(config)
            )[0]
            values = [
                (identifier, metadata, body)
                for identifier, (_, metadata, body) in cards.items()
                if metadata["category"] == "transaction-boundaries" and metadata["status"] == "current"
            ]
            knowledge_hash = self.tool.category_knowledge_hash(values)
            readme = root / ".codestable" / "wiki" / "transaction-boundaries" / "README.md"
            readme.write_text(
                "# Transaction boundaries\n\n<!-- codestable:canonical:start -->\n"
                "Current checkout cards define the reviewed transaction boundary.\n"
                "<!-- codestable:canonical:end -->\n"
                f"<!-- codestable:summary-review {{\"knowledge_hash\":\"{knowledge_hash}\","
                f"\"reviewed_at\":\"{self.tool.now_iso()}\"}} -->\n",
                encoding="utf-8",
            )
            self.tool.rebuild_indexes(root, config)
            self.git_baseline(root)
            before = tree_digest(root / ".codestable")
            audit = self.tool.audit_payload(root, config)
            self.assertTrue(audit["ok"], audit)
            self.assertEqual(audit["business_truth"], "not-evaluated")
            self.assertEqual(audit["sections"]["structure"]["status"], "pass")
            self.assertEqual(audit["sections"]["current_references"]["status"], "pass")
            self.assertEqual(before, tree_digest(root / ".codestable"))

    def test_full_audit_uses_conclusion_similarity_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            self.tool.learn(
                root,
                config,
                {
                    "task": task(),
                    "items": [
                        card(
                            "architecture",
                            "Checkout adapter boundary",
                            "Checkout orchestration uses one payment adapter boundary.",
                        ),
                        card(
                            "requirements",
                            "Checkout inventory rule",
                            "A checkout request validates inventory before it creates a durable order.",
                        ),
                    ],
                },
            )
            process = subprocess.run(
                [sys.executable, str(SHARED_TOOL), "--root", str(root), "audit", "--format", "json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertIn(process.returncode, (0, 1), process.stderr + process.stdout)
            result = json.loads(process.stdout)
            self.assertIn("governance", result["sections"])
            self.assertNotIn("NameError", process.stderr)

    def test_audit_separates_structure_reference_governance_and_delivery_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            config["capture"]["strict_durable_cards"] = False
            self.tool.learn(
                root,
                config,
                {
                    "task": task(),
                    "items": [
                        {
                            "category": "architecture",
                            "title": "Legacy checkout note",
                            "knowledge": "A deleted adapter once handled checkout.",
                            "paths": ["commerce/deleted_adapter.py"],
                            "confidence": "verified",
                            "evidence": ["old text evidence"],
                        }
                    ],
                },
            )
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            before = tree_digest(root / ".codestable")
            audit = self.tool.audit_payload(root, config)
            self.assertFalse(audit["ok"])
            self.assertEqual(audit["sections"]["structure"]["status"], "pass")
            self.assertEqual(audit["sections"]["current_references"]["status"], "needs-attention")
            issues = {value["issue_type"] for value in audit["sections"]["governance"]["findings"]}
            self.assertIn("card-evidence-unstructured", issues)
            self.assertIn("future-use-unstructured", issues)
            self.assertEqual(audit["sections"]["delivery"]["git_writeback"]["status"], "incomplete")
            self.assertEqual(before, tree_digest(root / ".codestable"))

    def test_upgrade_syncs_managed_guidance_but_preserves_project_content_and_unknown_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _ = self.make_root(temporary)
            generic = root / ".codestable" / "wiki" / "README.md"
            project = root / ".codestable" / "wiki" / "PROJECT.md"
            category = root / ".codestable" / "wiki" / "architecture" / "README.md"
            unknown = root / ".codestable" / "wiki" / "project-owned" / "note.md"
            unknown.parent.mkdir(parents=True)
            generic.write_text("stale generic guidance\n", encoding="utf-8")
            project.write_text("project-owned overview\n", encoding="utf-8")
            category.write_text("project-owned category summary\n", encoding="utf-8")
            unknown.write_text("project-owned unknown data\n", encoding="utf-8")
            agents = root / "AGENTS.md"
            agents.write_text("Read .codestable/model/INDEX.md\n", encoding="utf-8")
            result = self.bootstrap.install(root, upgrade=True)
            self.assertNotEqual(generic.read_text(encoding="utf-8"), "stale generic guidance\n")
            self.assertEqual(project.read_text(encoding="utf-8"), "project-owned overview\n")
            self.assertEqual(category.read_text(encoding="utf-8"), "project-owned category summary\n")
            self.assertEqual(unknown.read_text(encoding="utf-8"), "project-owned unknown data\n")
            self.assertEqual(agents.read_text(encoding="utf-8"), "Read .codestable/model/INDEX.md\n")
            self.assertIn(".codestable/wiki/README.md", result["updated"])
            self.assertIn(".codestable/wiki/README.md", result["file_lifecycle"]["managed_versioned"])
            self.assertIn(".codestable/wiki/PROJECT.md", result["file_lifecycle"]["project_owned_after_creation"])
            self.assertNotIn("backup", result)
            self.assertNotIn("backed_up", result)
            self.assertFalse(result["file_lifecycle"]["automatic_backups"])
            self.assertFalse((root / ".codestable" / "backups").exists())

    def test_schema_two_upgrade_preserves_legacy_card_evidence_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            config["capture"]["strict_durable_cards"] = False
            learned = self.tool.learn(
                root,
                config,
                {
                    "task": task(),
                    "items": [
                        {
                            "category": "architecture",
                            "title": "Legacy checkout boundary",
                            "knowledge": "Checkout once used a local adapter boundary.",
                            "paths": ["commerce/checkout.py"],
                            "future_use": ["review when the adapter changes", "review when persistence changes"],
                            "confidence": "verified",
                            "evidence": ["legacy anonymous test passed"],
                        }
                    ],
                },
            )
            card_path = root / learned["created_cards"][0]["path"]
            before = card_path.read_bytes()
            config_path = root / ".codestable" / "config.json"
            old_config = json.loads(config_path.read_text(encoding="utf-8"))
            old_config["schema_version"] = 2
            old_config["version"] = "1.1.0"
            old_config["wiki"].pop("topic_governance", None)
            old_config["wiki"].pop("topic_history", None)
            config_path.write_text(json.dumps(old_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.bootstrap.install(root, upgrade=True)
            upgraded = self.tool.load_config(root)
            self.assertEqual(upgraded["schema_version"], 3)
            self.assertEqual(card_path.read_bytes(), before)
            findings = self.tool.governance_audit(root, upgraded)["findings"]
            self.assertTrue(any(value["issue_type"] == "card-evidence-unstructured" for value in findings))

    def test_generated_markdown_has_no_trailing_whitespace_and_reindex_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.make_root(temporary)
            self.git_baseline(root)
            self.tool.learn(
                root, config, {"task": task(), "items": [card("architecture", "Checkout boundary", "Checkout uses an adapter.")]}
            )
            subprocess.run(["git", "add", ".codestable"], cwd=root, check=True)
            check = subprocess.run(["git", "diff", "--cached", "--check"], cwd=root, text=True, capture_output=True)
            self.assertEqual(check.returncode, 0, check.stdout)
            self.assertEqual(self.tool.rebuild_indexes(root, config)["changed"], [])
            before = tree_digest(root / ".codestable")
            dry = self.tool.rebuild_indexes(root, config, dry_run=True)
            self.assertEqual(dry["changed"], [])
            self.assertEqual(before, tree_digest(root / ".codestable"))

    def test_generated_runtime_is_in_sync_and_cli_exposes_audit_and_topics(self) -> None:
        before = tree_digest(PACKAGE_ROOT / "skills" / "cs" / "runtime_src")
        process = subprocess.run(
            [sys.executable, str(PACKAGE_ROOT / "scripts" / "build_runtime.py"), "--check"],
            cwd=PACKAGE_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(before, tree_digest(PACKAGE_ROOT / "skills" / "cs" / "runtime_src"))
        parser = self.tool.build_parser()
        audit_args = parser.parse_args(["audit", "--cached"])
        self.assertEqual(audit_args.command, "audit")
        self.assertTrue(audit_args.cached)
        topics_args = parser.parse_args(["topics", "suggest"])
        self.assertEqual(topics_args.topics_command, "suggest")
        topics_list_args = parser.parse_args(["topics", "list"])
        self.assertEqual(topics_list_args.topics_command, "list")


if __name__ == "__main__":
    unittest.main()
