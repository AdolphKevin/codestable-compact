from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta_support import MetaProject, evolve, meta, trusted_eval


class ManualEvolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = MetaProject(Path(self.temporary.name))
        self.root = self.project.root

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_full_meta_cycle_owner_checkpoint_promote_and_rollback(self) -> None:
        campaign, registered, validity = self.project.full_candidate("meta-owner", "candidate-owner")
        self.assertEqual(validity["status"], "pass")
        self.assertEqual(registered["candidate"]["promotion_authority"], "owner")

        _, imported = self.project.evaluate(campaign, "candidate-owner")
        self.assertTrue(imported["verified"])
        decision = meta.decide_campaign(self.root, campaign_id="meta-owner", candidate_id="candidate-owner")
        self.assertTrue(decision["accepted"])
        acceptance = self.project.quality_and_accept(campaign, "candidate-owner")
        self.assertTrue(acceptance["ready"])
        self.assertEqual(acceptance["status"], "pending_owner_checkpoint")

        with self.assertRaises(meta.MetaError):
            meta.promote_campaign(
                self.root,
                campaign_id="meta-owner",
                candidate_id="candidate-owner",
                approval_kind="agent",
                approved_by="agent",
                reason="owner policy may not be self-approved",
            )

        promotion = meta.promote_campaign(
            self.root,
            campaign_id="meta-owner",
            candidate_id="candidate-owner",
            approval_kind="owner",
            approved_by="maintainer",
            reason="measured improvement without regression",
        )
        version = promotion["event"]["to"]
        self.assertNotEqual(version, "seed")
        self.assertIn("candidate main", (self.root / ".codestable/reference/routing.md").read_text(encoding="utf-8"))
        version_meta = trusted_eval.read_json(self.root / ".codestable/harness/versions" / version / "version.json")
        self.assertEqual(version_meta["metadata"]["policy_ids"], ["entry.routing-and-continuation"])
        self.assertEqual(version_meta["metadata"]["validated_runtime_profiles"], [self.project.PROFILE])
        self.assertTrue(version_meta["metadata"]["evaluation_sha256"])

        rollback = evolve.rollback(self.root, "seed", reason="unit test", approved_by="maintainer")
        self.assertEqual(rollback["event"]["to"], "seed")
        self.assertEqual(
            (self.root / ".codestable/reference/routing.md").read_text(encoding="utf-8"),
            self.project.original_routing,
        )

    def test_prompt_copy_can_use_agent_checkpoint_after_measured_acceptance(self) -> None:
        campaign = self.project.create_campaign(
            "meta-copy",
            policy_ids=("interaction.route-summary-copy",),
            signal="entry.extra_turn",
        )
        hypothesis = self.project.diagnose_and_freeze(
            "meta-copy", surface_id="interaction-copy", mechanism="interaction.extra_turn"
        )
        registered = self.project.register_routing_candidate(
            campaign,
            hypothesis,
            candidate_id="candidate-copy",
            suffix="copy",
            change_type="prompt_copy",
            policy_ids=("interaction.route-summary-copy",),
            fixture_ids=("routing.auto-continue", "e2e.normal-run-no-meta"),
            surface_path=".codestable/harness/policies/interaction-copy.md",
        )
        self.assertEqual(registered["candidate"]["promotion_authority"], "agent")
        meta.validity_prepass(
            self.root,
            campaign_id="meta-copy",
            candidate_id="candidate-copy",
            repeats=5,
            judge_profile="isolated/judge",
            actor="validator",
        )
        self.project.evaluate(campaign, "candidate-copy")
        self.assertTrue(meta.decide_campaign(self.root, campaign_id="meta-copy", candidate_id="candidate-copy")["accepted"])
        acceptance = self.project.quality_and_accept(campaign, "candidate-copy")
        self.assertEqual(acceptance["status"], "ready_for_agent_promotion")
        promoted = meta.promote_campaign(
            self.root,
            campaign_id="meta-copy",
            candidate_id="candidate-copy",
            approval_kind="agent",
            approved_by="meta-agent",
            reason="agent-owned copy change passed measured gates",
        )
        self.assertEqual(promoted["event"]["approval_kind"], "agent")

    def test_proposal_must_be_agent_authored(self) -> None:
        campaign = self.project.create_campaign("meta-author")
        hypothesis = self.project.diagnose_and_freeze("meta-author")
        variant = self.root / "variant-bad.md"
        variant.write_text("# variant\n", encoding="utf-8")
        overlay = self.root / "overlay-bad"
        target = overlay / ".codestable/reference/routing.md"
        target.parent.mkdir(parents=True)
        target.write_text(self.project.original_routing + "\nchange\n", encoding="utf-8")
        proposal = {
            "schema_version": 1,
            "campaign_id": campaign["campaign_id"],
            "case_id": campaign["case_id"],
            "candidate_id": "bad-author",
            "authorship": {"kind": "script", "agent_id": "optimizer.py"},
            "title": "bad",
            "target_metric": {"id": "routing.user_corrected", "label": "measured"},
            "policy_ids": ["entry.routing-and-continuation"],
            "change_type": "workflow_routing",
            "fixture_ids": ["routing.performance-to-issue", "e2e.normal-run-no-meta"],
            "expected_effect": "bad",
            "regression_risks": [],
            "hypothesis": {"sha256": hypothesis["sha256"], "provenance_commit": hypothesis["provenance_commit"]},
            "variant_document": variant.name,
        }
        path = self.root / "bad-author.json"
        path.write_text(json.dumps(proposal), encoding="utf-8")
        with self.assertRaises(meta.MetaError):
            meta.register_proposal(self.root, campaign_id="meta-author", proposal_file=path, overlay=overlay)

    def test_proposal_without_required_fixture_layer_is_rejected(self) -> None:
        campaign = self.project.create_campaign("meta-coverage")
        hypothesis = self.project.diagnose_and_freeze("meta-coverage")
        with self.assertRaises(meta.MetaError):
            self.project.register_routing_candidate(
                campaign,
                hypothesis,
                candidate_id="candidate-no-e2e",
                fixture_ids=("routing.performance-to-issue",),
            )

    def test_underpowered_prepass_cannot_create_evaluation_challenge(self) -> None:
        campaign = self.project.create_campaign("meta-underpowered")
        hypothesis = self.project.diagnose_and_freeze("meta-underpowered")
        self.project.register_routing_candidate(campaign, hypothesis, candidate_id="candidate-underpowered")
        result = meta.validity_prepass(
            self.root,
            campaign_id="meta-underpowered",
            candidate_id="candidate-underpowered",
            repeats=1,
            judge_profile="isolated/judge",
            actor="validator",
        )
        self.assertEqual(result["status"], "underpowered")
        self.assertFalse(result["can_support_promotion"])
        with self.assertRaises(meta.MetaError):
            meta.create_evaluation_challenge(
                self.root,
                campaign_id="meta-underpowered",
                candidate_id="candidate-underpowered",
                model_profile=self.project.PROFILE,
                adapter=self.project.ADAPTER,
                evaluator=self.project.EVALUATOR,
                budget=self.project.BUDGET,
            )

    def test_holdout_regression_is_rejected(self) -> None:
        campaign, _, _ = self.project.full_candidate("meta-regression", "candidate-regression")
        self.project.evaluate(
            campaign,
            "candidate-regression",
            held_in=(6, 10, 7, 10),
            held_out=(8, 10, 7, 10),
            safety=(5, 5, 5, 5),
        )
        decision = meta.decide_campaign(self.root, campaign_id="meta-regression", candidate_id="candidate-regression")
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("held_out" in reason for reason in decision["reasons"]))

    def test_signed_result_rejects_tampering_raw_trace_and_replay(self) -> None:
        campaign, _, _ = self.project.full_candidate("meta-security", "candidate-security")
        signed_path, _ = self.project.evaluate(campaign, "candidate-security")
        # A second import is a replay.
        with self.assertRaises(trusted_eval.EvaluationError):
            trusted_eval.import_result(
                self.root,
                case_id=campaign["case_id"],
                candidate_id="candidate-security",
                result_file=signed_path,
                key=self.project.KEY,
            )

        campaign2, _, _ = self.project.full_candidate("meta-security-2", "candidate-security-2")
        challenge = meta.create_evaluation_challenge(
            self.root,
            campaign_id="meta-security-2",
            candidate_id="candidate-security-2",
            model_profile=self.project.PROFILE,
            adapter=self.project.ADAPTER,
            evaluator=self.project.EVALUATOR,
            budget=self.project.BUDGET,
        )
        payload = trusted_eval.read_json(self.root / challenge["template_path"])
        for name in ("held_in", "held_out", "safety"):
            total = 5 if name == "safety" else 10
            payload["splits"][name]["baseline"] = self.project.score(total, total)
            payload["splits"][name]["candidate"] = self.project.score(total, total)
        payload["task_traces"] = [{"private": True}]
        raw = trusted_eval.sign_result_payload(payload, key=self.project.KEY, key_id="unit")
        raw_path = self.root / "raw-result.json"
        trusted_eval.write_json(raw_path, raw)
        with self.assertRaises(trusted_eval.EvaluationError):
            trusted_eval.import_result(
                self.root,
                case_id=campaign2["case_id"],
                candidate_id="candidate-security-2",
                result_file=raw_path,
                key=self.project.KEY,
            )

    def test_candidate_definition_change_after_evaluation_blocks_decision(self) -> None:
        campaign, _, _ = self.project.full_candidate("meta-lock", "candidate-lock")
        self.project.evaluate(campaign, "candidate-lock")
        manifest_path = (
            self.root / ".codestable/evolution/cases" / campaign["case_id"]
            / "candidates/candidate-lock/manifest.json"
        )
        manifest = trusted_eval.read_json(manifest_path)
        manifest["expected_effect"] = "changed after evaluation"
        trusted_eval.write_json(manifest_path, manifest)
        with self.assertRaises(evolve.EvolutionError):
            evolve.decide_candidate(self.root, campaign["case_id"], "candidate-lock")

    def test_overlay_cannot_smuggle_undeclared_surface(self) -> None:
        campaign = self.project.create_campaign("meta-smuggle")
        hypothesis = self.project.diagnose_and_freeze("meta-smuggle")
        variant = self.root / "variant-smuggle.md"
        variant.write_text("# variant\n", encoding="utf-8")
        overlay = self.root / "overlay-smuggle"
        routing = overlay / ".codestable/reference/routing.md"
        routing.parent.mkdir(parents=True)
        routing.write_text(self.project.original_routing + "\nchange\n", encoding="utf-8")
        gates = overlay / ".codestable/reference/gates.md"
        gates.write_text("smuggled\n", encoding="utf-8")
        proposal = {
            "schema_version": 1,
            "campaign_id": campaign["campaign_id"],
            "case_id": campaign["case_id"],
            "candidate_id": "candidate-smuggle",
            "authorship": {"kind": "agent", "agent_id": "unit"},
            "title": "smuggle",
            "target_metric": {"id": "routing", "label": "measured"},
            "policy_ids": ["entry.routing-and-continuation"],
            "change_type": "workflow_routing",
            "fixture_ids": ["routing.performance-to-issue", "e2e.normal-run-no-meta"],
            "expected_effect": "none",
            "regression_risks": [],
            "hypothesis": {"sha256": hypothesis["sha256"], "provenance_commit": hypothesis["provenance_commit"]},
            "variant_document": variant.name,
        }
        path = self.root / "proposal-smuggle.json"
        path.write_text(json.dumps(proposal), encoding="utf-8")
        with self.assertRaises(meta.MetaError):
            meta.register_proposal(self.root, campaign_id="meta-smuggle", proposal_file=path, overlay=overlay)

    def test_corrupt_rollback_snapshot_blocks_promotion(self) -> None:
        campaign, _, _ = self.project.full_candidate("meta-snapshot", "candidate-snapshot")
        self.project.evaluate(campaign, "candidate-snapshot")
        self.assertTrue(meta.decide_campaign(self.root, campaign_id="meta-snapshot", candidate_id="candidate-snapshot")["accepted"])
        self.project.quality_and_accept(campaign, "candidate-snapshot")
        snapshot = self.root / ".codestable/harness/versions/seed/files/.codestable/reference/routing.md"
        snapshot.write_text("corrupted\n", encoding="utf-8")
        with self.assertRaises(meta.MetaError):
            meta.promote_campaign(
                self.root,
                campaign_id="meta-snapshot",
                candidate_id="candidate-snapshot",
                approval_kind="owner",
                approved_by="maintainer",
                reason="should fail",
            )


if __name__ == "__main__":
    unittest.main()
