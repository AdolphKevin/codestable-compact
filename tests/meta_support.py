from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO / "skills" / "cs" / "assets" / "project"
TOOLS = ASSET_ROOT / ".codestable" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cs_eval as trusted_eval  # type: ignore
import cs_evolve as evolve  # type: ignore
import cs_feedback as feedback  # type: ignore
import cs_meta as meta  # type: ignore
import cs_observe as observe  # type: ignore
import cs_policy as policy  # type: ignore


class MetaProject:
    KEY = b"unit-test-evaluator-key"
    MODEL = "fixed-model"
    ADAPTER = "fixed-adapter"
    PROFILE = f"{ADAPTER}/{MODEL}"
    EVALUATOR = "external-evaluator-v1"
    BUDGET = "budget-v1"

    def __init__(self, root: Path, *, surface_overrides: dict[str, str] | None = None) -> None:
        self.root = root
        shutil.copytree(ASSET_ROOT, root, dirs_exist_ok=True)
        for relative, content in (surface_overrides or {}).items():
            (root / relative).write_text(content, encoding="utf-8")
        evolve.init_runtime(root)
        meta.init_runtime(root)
        self.original_routing = (root / ".codestable/reference/routing.md").read_text(encoding="utf-8")
        self.original_interaction = (root / ".codestable/harness/policies/interaction-copy.md").read_text(encoding="utf-8")
        self.git("init")
        self.git("config", "user.email", "tests@codestable.invalid")
        self.git("config", "user.name", "CodeStable Tests")
        self.git("add", ".codestable")
        self.git("commit", "-m", "initial runtime")

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=self.root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return completed.stdout.strip()

    def add_finished_observation(
        self,
        run_id: str,
        *,
        signal: str = "routing.user_corrected",
        route: str = "cs-feat",
        status: str = "failed",
    ) -> None:
        observe.start_observation(
            self.root,
            work=f"work-{run_id}",
            task_id=run_id,
            kind="issue",
            risk_level=1,
            entry="cs",
            route=route,
            model_profile=self.MODEL,
            adapter=self.ADAPTER,
            start_action="inspect",
            run_id=run_id,
        )
        observe.append_event(self.root, run_id, "action_selected", {"action": "inspect"})
        observe.append_event(
            self.root, run_id, "gate_evaluated",
            {"gate_id": "route", "outcome": "rejected", "reason_code": "user-corrected"},
        )
        observe.append_event(
            self.root, run_id, "human_intervention",
            {"intervention_type": "correction", "reason_code": "wrong-route"},
        )
        observe.append_event(self.root, run_id, "token_usage", {"total_tokens": 1000})
        observe.append_event(self.root, run_id, "knowledge_read", {"path": ".codestable/model/domain.md"})
        observe.finish_observation(
            self.root,
            run_id,
            status=status,
            end_action="inspect",
            task_validation={
                "status": "failed" if status == "failed" else "passed",
                "verifier_id": "task-verifier",
                "command": "project-test",
                "exit_code": 1 if status == "failed" else 0,
                "evidence": [],
                "issued_by": "task-runner",
            },
            signals=(signal,),
            metrics={"tool_calls": 12, "context_bytes": 5000},
            note="route was corrected by the user",
        )

    def triage(
        self,
        run_id: str,
        *,
        feedback_id: str | None = None,
        classification: str = "harness_policy",
        signal: str = "routing.user_corrected",
        policy_ids: tuple[str, ...] = ("entry.routing-and-continuation",),
    ) -> dict[str, Any]:
        return feedback.triage_feedback(
            self.root,
            run_id=run_id,
            classification=classification,
            signal=signal,
            summary="The performance request was routed to the wrong execution policy.",
            policy_ids=policy_ids if classification == "harness_policy" else (),
            actor="owner",
            feedback_id=feedback_id,
        )

    def create_campaign(
        self,
        campaign_id: str = "meta-routing",
        *,
        feedback_count: int = 3,
        policy_ids: tuple[str, ...] = ("entry.routing-and-continuation",),
        signal: str = "routing.user_corrected",
        runtime_profiles: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        feedback_ids: list[str] = []
        for index in range(feedback_count):
            run_id = f"{campaign_id}-run-{index + 1}"
            self.add_finished_observation(run_id, signal=signal)
            feedback_ids.append(
                self.triage(run_id, feedback_id=f"{campaign_id}-fb-{index + 1}", signal=signal, policy_ids=policy_ids)["feedback_id"]
            )
        campaign = meta.create_campaign(
            self.root,
            title="Correct repeated routing failure",
            feedback_ids=feedback_ids,
            signal=signal,
            policy_ids=policy_ids,
            runtime_profiles=list(runtime_profiles or (self.PROFILE,)),
            budget_id=self.BUDGET,
            source="unit_test",
            campaign_id=campaign_id,
        )
        return campaign

    def diagnose_and_freeze(
        self,
        campaign_id: str,
        *,
        surface_id: str = "routing-policy",
        mechanism: str = "routing.misclassification",
        hypothesis_content: str | None = None,
    ) -> dict[str, Any]:
        meta.diagnose_campaign(
            self.root,
            campaign_id=campaign_id,
            classification="harness",
            summary="The Harness policy does not represent this repeated production case.",
            mechanism=mechanism,
            surface_id=surface_id,
            confidence=0.9,
        )
        hypothesis = self.root / f"hypothesis-{campaign_id}.md"
        hypothesis.write_text(
            hypothesis_content or "# Frozen hypothesis\n\nA bounded policy change should reduce the repeated signal without regression.\n",
            encoding="utf-8",
        )
        self.git("add", hypothesis.name)
        self.git("commit", "-m", f"freeze hypothesis for {campaign_id}")
        return meta.freeze_hypothesis(
            self.root,
            campaign_id=campaign_id,
            hypothesis_file=hypothesis,
            actor="owner",
        )

    def register_routing_candidate(
        self,
        campaign: dict[str, Any],
        hypothesis: dict[str, Any],
        *,
        candidate_id: str = "candidate-routing",
        suffix: str = "main",
        change_type: str = "workflow_routing",
        policy_ids: tuple[str, ...] = ("entry.routing-and-continuation",),
        fixture_ids: tuple[str, ...] = ("routing.performance-to-issue", "e2e.normal-run-no-meta"),
        surface_path: str = ".codestable/reference/routing.md",
        surface_content: str | None = None,
        variant_content: str | None = None,
        target_metric_id: str = "routing.user_corrected",
    ) -> dict[str, Any]:
        variant = self.root / f"variant-{candidate_id}.md"
        variant.write_text(
            variant_content or f"# Agent variant {candidate_id}\n\nTarget the repeated production mechanism; suffix={suffix}.\n",
            encoding="utf-8",
        )
        overlay = self.root / f"overlay-{candidate_id}"
        target = overlay / surface_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if surface_path.endswith("routing.md"):
            base = self.original_routing
        elif surface_path.endswith("interaction-copy.md"):
            base = self.original_interaction
        else:
            base = (self.root / surface_path).read_text(encoding="utf-8")
        target.write_text(surface_content if surface_content is not None else base + f"\n<!-- candidate {suffix} -->\n", encoding="utf-8")
        proposal = {
            "schema_version": 1,
            "campaign_id": campaign["campaign_id"],
            "case_id": campaign["case_id"],
            "candidate_id": candidate_id,
            "authorship": {"kind": "agent", "agent_id": "unit-agent"},
            "title": "Improve repeated routing behavior",
            "target_metric": {"id": target_metric_id, "label": "measured"},
            "policy_ids": list(policy_ids),
            "change_type": change_type,
            "fixture_ids": list(fixture_ids),
            "expected_effect": "Reduce user route corrections",
            "regression_risks": ["May over-classify ambiguous requests"],
            "hypothesis": {
                "sha256": hypothesis["sha256"],
                "provenance_commit": hypothesis["provenance_commit"],
            },
            "variant_document": variant.name,
        }
        proposal_file = self.root / f"proposal-{candidate_id}.json"
        proposal_file.write_text(json.dumps(proposal), encoding="utf-8")
        return meta.register_proposal(
            self.root,
            campaign_id=campaign["campaign_id"],
            proposal_file=proposal_file,
            overlay=overlay,
        )

    @staticmethod
    def score(passed: int, total: int, *, multiplier: float = 1.0) -> dict[str, Any]:
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

    def evaluate(
        self,
        campaign: dict[str, Any],
        candidate_id: str,
        *,
        held_in: tuple[int, int, int, int] = (6, 10, 7, 10),
        held_out: tuple[int, int, int, int] = (8, 10, 8, 10),
        safety: tuple[int, int, int, int] = (5, 5, 5, 5),
    ) -> tuple[Path, dict[str, Any]]:
        challenge = meta.create_evaluation_challenge(
            self.root,
            campaign_id=campaign["campaign_id"],
            candidate_id=candidate_id,
            model_profile=self.PROFILE,
            adapter=self.ADAPTER,
            evaluator=self.EVALUATOR,
            budget=self.BUDGET,
            challenge_id=f"eval-{campaign['campaign_id']}-{candidate_id}",
        )
        payload = trusted_eval.read_json(self.root / challenge["template_path"])
        for name, values in {"held_in": held_in, "held_out": held_out, "safety": safety}.items():
            bp, bt, cp, ct = values
            payload["splits"][name]["baseline"] = self.score(bp, bt)
            payload["splits"][name]["candidate"] = self.score(cp, ct)
        signed = trusted_eval.sign_result_payload(payload, key=self.KEY, key_id="unit-evaluator")
        path = self.root / f"signed-{campaign['campaign_id']}-{candidate_id}.json"
        trusted_eval.write_json(path, signed)
        imported = trusted_eval.import_result(
            self.root,
            case_id=campaign["case_id"],
            candidate_id=candidate_id,
            result_file=path,
            key=self.KEY,
        )
        return path, imported

    def quality_and_accept(self, campaign: dict[str, Any], candidate_id: str) -> dict[str, Any]:
        for name in ("regression", "package"):
            evidence = self.root / f"{campaign['campaign_id']}-{candidate_id}-{name}.json"
            evidence.write_text(json.dumps({"ok": True, "gate": name}), encoding="utf-8")
            meta.record_quality_gate(
                self.root,
                campaign_id=campaign["campaign_id"],
                name=name,
                status="passed",
                label="measured",
                actor="ci",
                command=name,
                evidence_path=evidence,
            )
        return meta.acceptance_check(self.root, campaign_id=campaign["campaign_id"], candidate_id=candidate_id)

    def full_candidate(
        self,
        campaign_id: str = "meta-routing",
        candidate_id: str = "candidate-routing",
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        campaign = self.create_campaign(campaign_id)
        hypothesis = self.diagnose_and_freeze(campaign_id)
        registered = self.register_routing_candidate(campaign, hypothesis, candidate_id=candidate_id)
        validity = meta.validity_prepass(
            self.root,
            campaign_id=campaign_id,
            candidate_id=candidate_id,
            repeats=5,
            judge_profile="isolated-judge/profile",
            actor="validity-owner",
        )
        return campaign, registered, validity
