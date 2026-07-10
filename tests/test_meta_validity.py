from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta_support import MetaProject

import cs_meta as meta  # type: ignore


class MetaValidityAndAuthorityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = MetaProject(Path(self.temporary.name))
        self.root = self.project.root

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def candidate(self, campaign_id: str, candidate_id: str):
        campaign = self.project.create_campaign(campaign_id)
        hypothesis = self.project.diagnose_and_freeze(campaign_id)
        self.project.register_routing_candidate(campaign, hypothesis, candidate_id=candidate_id)
        return campaign

    def fixture_path(self) -> Path:
        return self.root / ".codestable/evals/fixtures/routing/routing.performance-to-issue/fixture.json"

    def rewrite_fixture(self, mutator) -> None:
        path = self.fixture_path()
        value = json.loads(path.read_text(encoding="utf-8"))
        mutator(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_required_context_blocks_attribution(self) -> None:
        self.candidate("meta-missing-context", "candidate-missing-context")
        self.rewrite_fixture(
            lambda value: value["context"]["required_refs"].append("docs/does-not-exist.md")
        )
        result = meta.validity_prepass(
            self.root,
            campaign_id="meta-missing-context",
            candidate_id="candidate-missing-context",
            repeats=5,
            judge_profile="isolated/judge",
            actor="validator",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["can_attribute_negative_verdict"])
        check = next(item for item in result["checks"] if item.get("check") == "context_complete" and item.get("fixture_id") == "routing.performance-to-issue")
        self.assertIn("docs/does-not-exist.md", check["detail"]["missing_refs"])

    def test_brittle_oracle_blocks_evaluation(self) -> None:
        self.candidate("meta-brittle", "candidate-brittle")

        def mutate(value):
            value["oracle"] = {"deterministic": False, "type": "exact_text", "tolerance": ""}

        self.rewrite_fixture(mutate)
        result = meta.validity_prepass(
            self.root,
            campaign_id="meta-brittle",
            candidate_id="candidate-brittle",
            repeats=5,
            judge_profile="isolated/judge",
            actor="validator",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item["check"] == "oracle_tolerance" and item["status"] == "blocked" for item in result["checks"]))

    def test_uncalibrated_scorer_blocks_evaluation(self) -> None:
        self.candidate("meta-scorer", "candidate-scorer")

        def mutate(value):
            value["scorer"]["calibrated"] = False
            value["scorer"]["calibration_evidence"] = ""

        self.rewrite_fixture(mutate)
        result = meta.validity_prepass(
            self.root,
            campaign_id="meta-scorer",
            candidate_id="candidate-scorer",
            repeats=5,
            judge_profile="isolated/judge",
            actor="validator",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item["check"] == "scorer_calibrated" and item["status"] == "blocked" for item in result["checks"]))

    def test_same_profile_judge_is_rejected(self) -> None:
        self.candidate("meta-judge", "candidate-judge")

        def mutate(value):
            value["oracle"] = {"deterministic": False, "type": "judge", "tolerance": "rubric_with_equivalent_outputs"}
            value["scorer"]["type"] = "judge"

        self.rewrite_fixture(mutate)
        result = meta.validity_prepass(
            self.root,
            campaign_id="meta-judge",
            candidate_id="candidate-judge",
            repeats=5,
            judge_profile=self.project.PROFILE,
            actor="validator",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item["check"] == "judge_isolation" and item["status"] == "blocked" for item in result["checks"]))

    def test_missing_measured_quality_gates_block_acceptance(self) -> None:
        campaign, _, validity = self.project.full_candidate("meta-gates", "candidate-gates")
        self.assertEqual(validity["status"], "pass")
        self.project.evaluate(campaign, "candidate-gates")
        self.assertTrue(meta.decide_campaign(self.root, campaign_id="meta-gates", candidate_id="candidate-gates")["accepted"])
        acceptance = meta.acceptance_check(self.root, campaign_id="meta-gates", candidate_id="candidate-gates")
        self.assertFalse(acceptance["ready"])
        self.assertEqual(acceptance["status"], "blocked")
        self.assertTrue(any("regression" in reason for reason in acceptance["reasons"]))
        self.assertTrue(any("package" in reason for reason in acceptance["reasons"]))

    def test_owner_checkpoint_cannot_be_downgraded_and_meta_rollback_works(self) -> None:
        campaign, _, _ = self.project.full_candidate("meta-owner", "candidate-owner")
        self.project.evaluate(campaign, "candidate-owner")
        self.assertTrue(meta.decide_campaign(self.root, campaign_id="meta-owner", candidate_id="candidate-owner")["accepted"])
        acceptance = self.project.quality_and_accept(campaign, "candidate-owner")
        self.assertEqual(acceptance["promotion_authority"], "owner")
        with self.assertRaises(meta.MetaError):
            meta.promote_campaign(
                self.root,
                campaign_id="meta-owner",
                candidate_id="candidate-owner",
                approval_kind="agent",
                approved_by="proposal-agent",
                reason="attempt to lower checkpoint",
            )
        promoted = meta.promote_campaign(
            self.root,
            campaign_id="meta-owner",
            candidate_id="candidate-owner",
            approval_kind="owner",
            approved_by="maintainer",
            reason="measured evidence and owner approval",
        )
        self.assertNotEqual(promoted["event"]["to"], "seed")
        rolled_back = meta.rollback_harness(
            self.root,
            version_id="seed",
            approved_by="maintainer",
            reason="verified rollback path",
        )
        self.assertEqual(rolled_back["event"]["to"], "seed")


if __name__ == "__main__":
    unittest.main()
