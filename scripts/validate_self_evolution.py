#!/usr/bin/env python3
"""Run a controlled real-Codex Harness recovery experiment."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from meta_support import MetaProject, evolve, meta, trusted_eval  # type: ignore


ARTIFACTS = ROOT / "validation" / "self-evolution"
SURFACE = ".codestable/harness/policies/interaction-copy.md"
MARKER = "[ROUTE_CONFIRMATION_REQUIRED]"
TASKS = {
    "held_in": ("/cs route 数据导入升级后从 2 秒变成 30 秒，请定位并修复。", "issue"),
    "held_out": ("/cs route 请新增 CSV 导出能力。", "feature"),
    "safety": ("/cs route 在不改变行为的前提下整理缓存模块结构。", "refactor"),
}


def seed(workspace: Path, policy: str) -> None:
    package = workspace / ".eval" / "codestable"
    package.mkdir(parents=True)
    shutil.copytree(ROOT / "skills", package / "skills")
    subprocess.run(
        ["python3", str(package / "skills/cs/scripts/bootstrap.py"), "--root", str(workspace)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (workspace / SURFACE).write_text(policy, encoding="utf-8")
    (workspace / "AGENTS.md").write_text(
        """Use .eval/codestable/skills/cs/SKILL.md as the entry skill. For this route-only request, read the active presentation policy by running `python3 .codestable/tools/cs_harness.py interaction-copy` and obey it exactly. Do not read observations, Meta/evolution/evaluation state, rejected variants, or version history. Return only the compact route summary required by the active policy.\n""",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(
        ["git", "-c", "user.name=benchmark", "-c", "user.email=benchmark@invalid", "commit", "-qm", "seed"],
        cwd=workspace,
        check=True,
    )


def run_once(split: str, variant: str, policy: str, model: str, timeout: int) -> dict[str, Any]:
    prompt, expected_route = TASKS[split]
    with tempfile.TemporaryDirectory(prefix="codestable-evolution-host-") as raw:
        workspace = Path(raw)
        seed(workspace, policy)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [
                    "codex", "-a", "never", "-s", "workspace-write", "-m", model,
                    "exec", "--json", "--ephemeral", "--ignore-user-config",
                    "-C", str(workspace), prompt,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"split": split, "variant": variant, "passed": False, "failure": "timeout"}
        usage: dict[str, int] = {}
        final = ""
        tool_calls = 0
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "turn.completed":
                usage = event.get("usage") or {}
            item = event.get("item") or {}
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                final = str(item.get("text") or "")
            if event.get("type") == "item.completed" and item.get("type") in {
                "command_execution", "mcp_tool_call", "file_change"
            }:
                tool_calls += 1
        route = parse_route(final)
        marker_present = MARKER in final
        input_tokens = int(usage.get("input_tokens", 0))
        cached_tokens = int(usage.get("cached_input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        return {
            "split": split,
            "variant": variant,
            "passed": completed.returncode == 0 and route == expected_route and not marker_present,
            "route_correct": route == expected_route,
            "marker_present": marker_present,
            "duration_seconds": time.monotonic() - started,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "uncached_tokens": max(0, input_tokens - cached_tokens) + output_tokens,
            "context_bytes": input_tokens * 4,
            "tool_calls": tool_calls,
            "failure": None if completed.returncode == 0 else "codex_failed",
        }


def parse_route(value: str) -> str | None:
    match = re.search(r"(?<![a-z])(issue|feature|feat|refactor)(?![a-z])", value.casefold())
    if not match:
        return None
    return "feature" if match.group(1) == "feat" else match.group(1)


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    return {
        "pass_count": sum(bool(row.get("passed")) for row in rows),
        "total": total,
        "metrics": {
            "median_tokens": statistics.median(row["total_tokens"] for row in rows),
            "median_duration_seconds": statistics.median(row["duration_seconds"] for row in rows),
            "human_interrupt_rate": sum(bool(row["marker_present"]) for row in rows) / total,
            "context_bytes": statistics.median(row["context_bytes"] for row in rows),
        },
    }


def compact(rows: list[dict[str, Any]]) -> dict[str, Any]:
    value = score(rows)
    value["route_correct"] = sum(bool(row.get("route_correct")) for row in rows)
    value["marker_present"] = sum(bool(row.get("marker_present")) for row in rows)
    value["median_tool_calls"] = statistics.median(row["tool_calls"] for row in rows)
    value["median_uncached_tokens"] = statistics.median(row["uncached_tokens"] for row in rows)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--output", default="validation/self-evolution-report.json")
    args = parser.parse_args()
    if min(args.repeats, args.jobs, args.timeout) < 1:
        parser.error("repeats, jobs, and timeout must be positive")
    assert parse_route("→ feat · micro") == "feature"
    assert parse_route("→ cs-issue · standard") == "issue"
    assert parse_route("→ refactor · micro") == "refactor"

    degraded = (ARTIFACTS / "degraded-interaction-copy.md").read_text(encoding="utf-8")
    evolved = (ARTIFACTS / "evolved-interaction-copy.md").read_text(encoding="utf-8")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codestable-meta-recovery-") as raw:
        project = MetaProject(Path(raw), surface_overrides={SURFACE: degraded})
        campaign = project.create_campaign(
            "controlled-copy-recovery",
            policy_ids=("interaction.route-summary-copy",),
            signal="entry.extra_turn",
            runtime_profiles=(f"codex-cli/{args.model}",),
        )
        hypothesis = project.diagnose_and_freeze(
            campaign["campaign_id"],
            surface_id="interaction-copy",
            mechanism="interaction.extra_turn",
            hypothesis_content=(ARTIFACTS / "hypothesis.md").read_text(encoding="utf-8"),
        )
        registered = project.register_routing_candidate(
            campaign,
            hypothesis,
            candidate_id="remove-route-confirmation",
            change_type="prompt_copy",
            policy_ids=("interaction.route-summary-copy",),
            fixture_ids=("routing.auto-continue", "e2e.normal-run-no-meta"),
            surface_path=SURFACE,
            surface_content=evolved,
            variant_content=(ARTIFACTS / "variant.md").read_text(encoding="utf-8"),
            target_metric_id="entry.extra_turn",
        )
        validity = meta.validity_prepass(
            project.root,
            campaign_id=campaign["campaign_id"],
            candidate_id="remove-route-confirmation",
            repeats=args.repeats,
            judge_profile="isolated-judge/profile",
            actor="validity-owner",
        )
        challenge = meta.create_evaluation_challenge(
            project.root,
            campaign_id=campaign["campaign_id"],
            candidate_id="remove-route-confirmation",
            model_profile=f"codex-cli/{args.model}",
            adapter="controlled-codex-host-v1",
            evaluator="isolated-local-evaluator-v1",
            budget="route-only-v1",
        )
        schedule = [
            (split, variant, policy)
            for split in TASKS
            for variant, policy in (("degraded", degraded), ("evolved", evolved))
            for _ in range(args.repeats)
        ]
        random.Random(0).shuffle(schedule)
        rows: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run_once, split, variant, policy, args.model, args.timeout) for split, variant, policy in schedule]
            for index, future in enumerate(futures, 1):
                print(f"[{index}/{len(futures)}]", flush=True)
                rows.append(future.result())

        payload = trusted_eval.read_json(project.root / challenge["template_path"])
        aggregates: dict[str, Any] = {}
        for split in TASKS:
            baseline_rows = [row for row in rows if row["split"] == split and row["variant"] == "degraded"]
            candidate_rows = [row for row in rows if row["split"] == split and row["variant"] == "evolved"]
            payload["splits"][split]["baseline"] = score(baseline_rows)
            payload["splits"][split]["candidate"] = score(candidate_rows)
            aggregates[split] = {"degraded": compact(baseline_rows), "evolved": compact(candidate_rows)}
        signed = trusted_eval.sign_result_payload(payload, key=project.KEY, key_id="controlled-evaluator")
        signed_path = project.root / "signed-host-result.json"
        trusted_eval.write_json(signed_path, signed)
        imported = trusted_eval.import_result(
            project.root,
            case_id=campaign["case_id"],
            candidate_id="remove-route-confirmation",
            result_file=signed_path,
            key=project.KEY,
        )
        decision = meta.decide_campaign(
            project.root, campaign_id=campaign["campaign_id"], candidate_id="remove-route-confirmation"
        )
        acceptance: dict[str, Any] = {"ready": False}
        promoted = False
        rolled_back = False
        if decision["accepted"]:
            acceptance = project.quality_and_accept(campaign, "remove-route-confirmation")
            promotion = meta.promote_campaign(
                project.root,
                campaign_id=campaign["campaign_id"],
                candidate_id="remove-route-confirmation",
                approval_kind="agent",
                approved_by="codex-agent",
                reason="controlled held-out and safety improvement passed measured gates",
            )
            promoted = (project.root / SURFACE).read_text(encoding="utf-8") == evolved
            evolve.rollback(project.root, "seed", reason="controlled experiment complete", approved_by="codex-agent")
            rolled_back = (project.root / SURFACE).read_text(encoding="utf-8") == degraded

    result = {
        "schema_version": 1,
        "verdict": "SELF_EVOLUTION_MEASURED_PASS" if decision["accepted"] and promoted and rolled_back else "SELF_EVOLUTION_NOT_PROVEN",
        "runtime_profile": {
            "host": subprocess.check_output(["codex", "--version"], text=True).strip(),
            "model": args.model,
            "repeats": args.repeats,
            "adapter": "controlled-codex-host-v1",
        },
        "pipeline": {
            "feedback_count": 3,
            "candidate_authority": registered["candidate"]["promotion_authority"],
            "validity_status": validity["status"],
            "signed_result_verified": imported["verified"],
            "decision_accepted": decision["accepted"],
            "decision_reasons": decision["reasons"],
            "acceptance_ready": acceptance.get("ready", False),
            "promoted_in_isolated_project": promoted,
            "rolled_back_in_isolated_project": rolled_back,
        },
        "splits": aggregates,
        "wall_seconds": time.monotonic() - started,
        "limitations": [
            "controlled recovery proves mechanism capability, not autonomous discovery of an unknown production defect",
            "one policy surface and three route tasks do not establish cross-policy generalization",
            "context_bytes is estimated as four bytes per input token",
            "the proposer was the current Agent; scripts only locked, measured, signed, recorded, promoted, and rolled back",
        ],
    }
    output = ROOT / args.output
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "SELF_EVOLUTION_MEASURED_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
