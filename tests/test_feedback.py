from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta_support import MetaProject, feedback, meta, observe


class FeedbackPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = MetaProject(Path(self.temporary.name))
        self.root = self.project.root

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_triage_captures_trace_runtime_and_harness_identity(self) -> None:
        self.project.add_finished_observation("run-triage")
        item = self.project.triage("run-triage", feedback_id="fb-triage")
        self.assertEqual(item["classification"], "harness_policy")
        self.assertEqual(item["runtime_profile"]["model_profile"], self.project.MODEL)
        self.assertEqual(item["runtime_profile"]["adapter"], self.project.ADAPTER)
        self.assertTrue(item["harness"]["content_sha256"])
        self.assertEqual(item["trace_summary"]["gates"]["counts"]["rejected"], 1)
        self.assertEqual(item["trace_summary"]["human_interventions"]["total"], 1)
        self.assertEqual(item["trace_summary"]["tokens"]["total_tokens"], 1000)
        self.assertEqual(item["trace_summary"]["knowledge"]["reads"], 1)

    def test_only_finished_observation_can_be_triaged(self) -> None:
        observe.start_observation(
            self.root,
            work="work-running",
            task_id="running",
            kind="issue",
            lane="standard",
            entry="cs",
            route="cs-issue",
            model_profile=self.project.MODEL,
            adapter=self.project.ADAPTER,
            start_stage="intake",
            run_id="run-running",
        )
        with self.assertRaises(feedback.FeedbackError):
            self.project.triage("run-running", feedback_id="fb-running")

    def test_non_harness_feedback_cannot_claim_policy(self) -> None:
        self.project.add_finished_observation("run-product")
        with self.assertRaises(feedback.FeedbackError):
            feedback.triage_feedback(
                self.root,
                run_id="run-product",
                classification="product_code",
                signal="routing.user_corrected",
                summary="product bug",
                policy_ids=["entry.routing-and-continuation"],
                actor="owner",
            )

    def test_agent_authored_feedback_fixture_is_registered_with_provenance(self) -> None:
        self.project.add_finished_observation("run-fixture")
        item = self.project.triage("run-fixture", feedback_id="fb-fixture")
        fixture = {
            "schema_version": 1,
            "id": "production.routing.fixture-one",
            "title": "production routing fixture",
            "layers": ["routing"],
            "covers_policies": ["entry.routing-and-continuation"],
            "status": "active",
            "context": {
                "complete": True,
                "required_refs": [".codestable/reference/routing.md"],
                "subject_matter_refs": [".codestable/reference/lifecycle.md"],
            },
            "oracle": {"type": "predicate", "deterministic": False, "tolerance": "structured_predicate"},
            "scorer": {"id": "production.route", "calibrated": True, "calibration_evidence": "feedback/fb-fixture"},
            "execution": {"minimum_repeats": 5, "variance": "stochastic"},
            "runner": {"type": "host_adapter"},
            "expected": {"acceptable_routes": ["cs-issue"]},
        }
        source = self.root / "agent-fixture.json"
        source.write_text(json.dumps(fixture), encoding="utf-8")
        registered = feedback.register_fixture(
            self.root,
            feedback_id=item["feedback_id"],
            fixture_file=source,
            actor="fixture-agent",
        )
        self.assertIn("fb-fixture", registered["fixture"]["source_feedback_ids"])
        self.assertTrue((self.root / registered["fixture_path"]).is_file())
        updated = feedback.load_feedback(self.root, "fb-fixture")
        self.assertEqual(updated["status"], "fixture_registered")

    def test_trigger_accumulates_matching_profile_signals_but_dry_run_only_scans(self) -> None:
        for index in range(3):
            run_id = f"run-trigger-{index}"
            self.project.add_finished_observation(run_id)
            self.project.triage(run_id, feedback_id=f"fb-trigger-{index}")
        preview = meta.trigger_scan(self.root, apply=False)
        self.assertEqual(len(preview["eligible"]), 1)
        self.assertEqual(preview["created"], [])
        self.assertEqual(meta.open_campaigns(self.root), [])
        applied = meta.trigger_scan(self.root, apply=True)
        self.assertEqual(len(applied["created"]), 1)
        self.assertEqual(applied["created"][0]["status"], "diagnose")
        self.assertIn("never proposes, evaluates, or promotes", applied["guard"])


if __name__ == "__main__":
    unittest.main()
