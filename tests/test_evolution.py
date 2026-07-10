from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO / "skills" / "cs" / "assets" / "project"
EVOLVE_PATH = ASSET_ROOT / ".codestable" / "tools" / "cs_evolve.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evolve = load_module("codestable_compact_evolution_test", EVOLVE_PATH)
observe = evolve.cs_observe
trusted_eval = evolve.cs_eval


class ManualEvolutionTest(unittest.TestCase):
    KEY = b"unit-test-evaluator-key"
    MODEL = "fixed-model"
    ADAPTER = "fixed-adapter"
    EVALUATOR = "external-evaluator-v1"
    BUDGET = "budget-v1"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(ASSET_ROOT, self.root, dirs_exist_ok=True)
        evolve.init_runtime(self.root)
        self.original_routing = (
            self.root / ".codestable" / "reference" / "routing.md"
        ).read_text(encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def add_flagged_observation(self, run_id: str, signal: str = "routing.user_corrected") -> None:
        observe.start_observation(
            self.root,
            work=f"work-{run_id}",
            task_id=run_id,
            kind="issue",
            lane="standard",
            entry="cs",
            route="cs-issue",
            model_profile=self.MODEL,
            adapter=self.ADAPTER,
            start_stage="intake",
            run_id=run_id,
        )
        observe.append_event(
            self.root,
            run_id,
            "user_corrected",
            {"category": "route"},
        )
        observe.finish_observation(
            self.root,
            run_id,
            status="failed",
            end_stage="analyze",
            task_validation={
                "status": "failed",
                "verifier_id": "task-verifier",
                "command": "project-test",
                "exit_code": 1,
                "evidence": [],
                "issued_by": "task-runner",
            },
            signals=(signal,),
            metrics={"tool_calls": 12, "context_bytes": 5000},
            note="route was corrected by the user",
        )

    def create_harness_case(self, case_id: str = "case-routing") -> dict:
        self.add_flagged_observation(f"{case_id}-run-1")
        self.add_flagged_observation(f"{case_id}-run-2")
        created = evolve.create_case(
            self.root,
            title="correct repeated route mistake",
            run_ids=(f"{case_id}-run-1", f"{case_id}-run-2"),
            case_id=case_id,
        )
        evolve.record_diagnosis(
            self.root,
            case_id=case_id,
            classification="harness",
            summary="The route policy misses this repeated issue signature.",
            mechanism="routing.misclassification",
            surface_id="routing-policy",
            confidence=0.9,
        )
        return created

    def candidate_overlay(self, suffix: str) -> Path:
        overlay = self.root / f"overlay-{suffix}"
        path = overlay / ".codestable" / "reference" / "routing.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            self.original_routing
            + f"\n<!-- candidate {suffix}: classify observed regressions before feature wording -->\n",
            encoding="utf-8",
        )
        return overlay

    def add_candidate(self, case_id: str, candidate_id: str, suffix: str = "main") -> dict:
        return evolve.add_candidate(
            self.root,
            case_id,
            candidate_id=candidate_id,
            title="improve repeated route classification",
            surface_ids=("routing-policy",),
            overlay=self.candidate_overlay(suffix),
            expected_effect="reduce user route corrections",
            regression_risks=("may over-classify ambiguous requests as issues",),
        )

    @staticmethod
    def score(passed: int, total: int, *, multiplier: float = 1.0) -> dict:
        return {
            "pass_count": passed,
            "total": total,
            "metrics": {
                "median_tokens": 1000.0 * multiplier,
                "median_duration_seconds": 10.0 * multiplier,
                "human_interrupt_rate": 0.1 * multiplier,
                "context_bytes": 5000.0 * multiplier,
            },
        }

    def signed_result(
        self,
        case_id: str,
        candidate_id: str,
        *,
        held_in=(6, 10, 7, 10),
        held_out=(8, 10, 8, 10),
        safety=(5, 5, 5, 5),
    ) -> Path:
        challenge = trusted_eval.create_challenge(
            self.root,
            case_id=case_id,
            candidate_id=candidate_id,
            model_profile=self.MODEL,
            adapter=self.ADAPTER,
            evaluator=self.EVALUATOR,
            budget=self.BUDGET,
            challenge_id=f"eval-{case_id}-{candidate_id}",
        )
        template_path = self.root / challenge["template_path"]
        payload = trusted_eval.read_json(template_path)
        for name, values in {
            "held_in": held_in,
            "held_out": held_out,
            "safety": safety,
        }.items():
            bp, bt, cp, ct = values
            payload["splits"][name]["baseline"] = self.score(bp, bt)
            payload["splits"][name]["candidate"] = self.score(cp, ct)
        signed = trusted_eval.sign_result_payload(payload, key=self.KEY, key_id="unit-evaluator")
        result_path = self.root / f"signed-{case_id}-{candidate_id}.json"
        trusted_eval.write_json(result_path, signed)
        return result_path

    def import_result(self, case_id: str, candidate_id: str, path: Path) -> dict:
        return trusted_eval.import_result(
            self.root,
            case_id=case_id,
            candidate_id=candidate_id,
            result_file=path,
            key=self.KEY,
        )

    def test_manual_select_diagnose_evaluate_gate_promote_and_rollback(self) -> None:
        case_id = "case-main"
        candidate_id = "candidate-routing"
        created = self.create_harness_case(case_id)
        self.assertEqual(created["case"]["stage"], "diagnose")
        for run_id in created["case"]["selected_run_ids"]:
            self.assertEqual(observe.load_observation(self.root, run_id)["state"], "selected")

        manifest = self.add_candidate(case_id, candidate_id)
        self.assertTrue(manifest["promotion_gate_required"])
        signed_path = self.signed_result(case_id, candidate_id)
        challenge = trusted_eval.read_json(
            self.root / ".codestable" / "evolution" / "cases" / case_id
            / "evaluations" / candidate_id / "challenge.json"
        )
        self.assertEqual(challenge["baseline_content_sha256"], created["case"]["baseline_content_sha256"])
        self.assertEqual(challenge["candidate_content_sha256"], manifest["candidate_content_sha256"])
        self.assertTrue(challenge["candidate_definition_sha256"])
        imported = self.import_result(case_id, candidate_id, signed_path)
        self.assertTrue(imported["verified"])

        decision = evolve.decide_candidate(self.root, case_id, candidate_id)
        self.assertTrue(decision["accepted"])
        self.assertTrue(decision["promotion_gate_required"])
        self.assertIn("held_in", decision["improved_splits"])
        self.assertEqual(decision["challenge_sha256"], challenge["challenge_sha256"])
        self.assertEqual(decision["candidate_definition_sha256"], challenge["candidate_definition_sha256"])

        with self.assertRaises(evolve.EvolutionError):
            evolve.promote_candidate(
                self.root,
                case_id,
                candidate_id,
                human_approved=False,
                approved_by=None,
                reason=None,
            )

        promotion = evolve.promote_candidate(
            self.root,
            case_id,
            candidate_id,
            human_approved=True,
            approved_by="maintainer",
            reason="trusted evaluation improved held-in without regression",
        )
        version = promotion["event"]["to"]
        self.assertNotEqual(version, "seed")
        changed = (self.root / ".codestable" / "reference" / "routing.md").read_text(encoding="utf-8")
        self.assertIn("candidate main", changed)

        rollback = evolve.rollback(
            self.root,
            "seed",
            reason="unit-test rollback",
            approved_by="maintainer",
        )
        self.assertEqual(rollback["event"]["to"], "seed")
        restored = (self.root / ".codestable" / "reference" / "routing.md").read_text(encoding="utf-8")
        self.assertEqual(restored, self.original_routing)

    def test_signed_result_rejects_tampering_raw_traces_and_replay(self) -> None:
        case_id = "case-security"
        candidate_id = "candidate-security"
        self.create_harness_case(case_id)
        self.add_candidate(case_id, candidate_id, "security")
        signed_path = self.signed_result(case_id, candidate_id)

        tampered = trusted_eval.read_json(signed_path)
        tampered["splits"]["held_in"]["candidate"]["pass_count"] = 10
        tampered_path = self.root / "tampered.json"
        trusted_eval.write_json(tampered_path, tampered)
        with self.assertRaises(trusted_eval.EvaluationError):
            self.import_result(case_id, candidate_id, tampered_path)

        raw = trusted_eval.read_json(signed_path)
        raw["task_traces"] = [{"task": "hidden"}]
        raw = trusted_eval.sign_result_payload(raw, key=self.KEY, key_id="unit-evaluator")
        raw_path = self.root / "raw-traces.json"
        trusted_eval.write_json(raw_path, raw)
        with self.assertRaises(trusted_eval.EvaluationError):
            self.import_result(case_id, candidate_id, raw_path)

        self.import_result(case_id, candidate_id, signed_path)
        with self.assertRaises(trusted_eval.EvaluationError):
            self.import_result(case_id, candidate_id, signed_path)

    def test_candidate_and_challenge_are_immutable_across_trusted_evaluation(self) -> None:
        case_id = "case-candidate-lock"
        candidate_id = "candidate-lock"
        self.create_harness_case(case_id)
        self.add_candidate(case_id, candidate_id, "candidate-lock")
        signed_path = self.signed_result(case_id, candidate_id)

        manifest_path = (
            self.root / ".codestable" / "evolution" / "cases" / case_id
            / "candidates" / candidate_id / "manifest.json"
        )
        manifest = trusted_eval.read_json(manifest_path)
        manifest["expected_effect"] = "changed after evaluator challenge"
        trusted_eval.write_json(manifest_path, manifest)
        with self.assertRaises(trusted_eval.EvaluationError):
            self.import_result(case_id, candidate_id, signed_path)

        case_id = "case-challenge-lock"
        candidate_id = "candidate-challenge-lock"
        self.create_harness_case(case_id)
        self.add_candidate(case_id, candidate_id, "challenge-lock")
        signed_path = self.signed_result(case_id, candidate_id)
        challenge_path = (
            self.root / ".codestable" / "evolution" / "cases" / case_id
            / "evaluations" / candidate_id / "challenge.json"
        )
        challenge = trusted_eval.read_json(challenge_path)
        challenge["repeats"] += 1
        trusted_eval.write_json(challenge_path, challenge)
        with self.assertRaises(trusted_eval.EvaluationError):
            self.import_result(case_id, candidate_id, signed_path)

    def test_candidate_definition_cannot_change_after_decision(self) -> None:
        case_id = "case-post-decision-lock"
        candidate_id = "candidate-post-decision-lock"
        self.create_harness_case(case_id)
        self.add_candidate(case_id, candidate_id, "post-decision")
        signed_path = self.signed_result(case_id, candidate_id)
        self.import_result(case_id, candidate_id, signed_path)
        decision = evolve.decide_candidate(self.root, case_id, candidate_id)
        self.assertTrue(decision["accepted"])

        manifest_path = (
            self.root / ".codestable" / "evolution" / "cases" / case_id
            / "candidates" / candidate_id / "manifest.json"
        )
        manifest = trusted_eval.read_json(manifest_path)
        manifest["regression_risks"].append("new risk added after evaluation")
        trusted_eval.write_json(manifest_path, manifest)
        with self.assertRaises(evolve.EvolutionError):
            evolve.promote_candidate(
                self.root,
                case_id,
                candidate_id,
                human_approved=True,
                approved_by="maintainer",
                reason="must be rejected because the candidate changed",
            )

    def test_holdout_regression_is_rejected(self) -> None:
        case_id = "case-regression"
        candidate_id = "candidate-regression"
        self.create_harness_case(case_id)
        self.add_candidate(case_id, candidate_id, "regression")
        signed_path = self.signed_result(
            case_id,
            candidate_id,
            held_in=(6, 10, 7, 10),
            held_out=(8, 10, 7, 10),
            safety=(5, 5, 5, 5),
        )
        self.import_result(case_id, candidate_id, signed_path)
        decision = evolve.decide_candidate(self.root, case_id, candidate_id)
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("held_out" in reason for reason in decision["reasons"]))

    def test_overlay_cannot_smuggle_protected_or_undeclared_file(self) -> None:
        case_id = "case-smuggle"
        self.create_harness_case(case_id)
        overlay = self.candidate_overlay("smuggle")
        gate = overlay / ".codestable" / "reference" / "gates.md"
        gate.write_text("unsafe replacement\n", encoding="utf-8")
        with self.assertRaises(evolve.EvolutionError):
            evolve.add_candidate(
                self.root,
                case_id,
                candidate_id="candidate-smuggle",
                title="smuggle protected change",
                surface_ids=("routing-policy",),
                overlay=overlay,
                expected_effect="unsafe",
            )

    def test_corrupted_baseline_snapshot_blocks_promotion(self) -> None:
        case_id = "case-corrupt-snapshot"
        candidate_id = "candidate-corrupt-snapshot"
        self.create_harness_case(case_id)
        self.add_candidate(case_id, candidate_id, "corrupt-snapshot")
        signed_path = self.signed_result(case_id, candidate_id)
        self.import_result(case_id, candidate_id, signed_path)
        self.assertTrue(evolve.decide_candidate(self.root, case_id, candidate_id)["accepted"])

        snapshot = (
            self.root / ".codestable" / "harness" / "versions" / "seed" / "files"
            / ".codestable" / "reference" / "routing.md"
        )
        snapshot.write_text("corrupted snapshot\n", encoding="utf-8")
        with self.assertRaises(evolve.EvolutionError):
            evolve.promote_candidate(
                self.root,
                case_id,
                candidate_id,
                human_approved=True,
                approved_by="maintainer",
                reason="must not promote with a broken rollback snapshot",
            )

    def test_non_harness_diagnosis_closes_without_candidate(self) -> None:
        self.add_flagged_observation("run-project-knowledge", "context.constraint_missed")
        evolve.create_case(
            self.root,
            title="missing project contract",
            run_ids=("run-project-knowledge",),
            case_id="case-knowledge",
        )
        result = evolve.record_diagnosis(
            self.root,
            case_id="case-knowledge",
            classification="project_knowledge",
            summary="The project contract was missing; the Harness itself is not defective.",
        )
        self.assertEqual(result["case"]["stage"], "closed")
        with self.assertRaises(evolve.EvolutionError):
            evolve.add_candidate(
                self.root,
                "case-knowledge",
                candidate_id="candidate-invalid",
                title="should not exist",
                surface_ids=("routing-policy",),
                overlay=self.candidate_overlay("invalid"),
                expected_effect="none",
            )

    def test_result_template_splits_are_independent(self) -> None:
        case_id = "case-template"
        candidate_id = "candidate-template"
        self.create_harness_case(case_id)
        self.add_candidate(case_id, candidate_id, "template")
        created = trusted_eval.create_challenge(
            self.root,
            case_id=case_id,
            candidate_id=candidate_id,
            model_profile=self.MODEL,
            adapter=self.ADAPTER,
            evaluator=self.EVALUATOR,
            budget=self.BUDGET,
        )
        payload = trusted_eval.read_json(self.root / created["template_path"])
        payload["splits"]["held_in"]["baseline"]["pass_count"] = 3
        self.assertEqual(payload["splits"]["held_out"]["baseline"]["pass_count"], 0)


if __name__ == "__main__":
    unittest.main()
