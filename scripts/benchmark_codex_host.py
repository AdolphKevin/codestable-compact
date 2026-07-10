#!/usr/bin/env python3
"""Measure CodeStable HEAD versus the current tree with the real Codex CLI."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK = """/cs `dedupe` became too slow for large integer ID batches. Fix the root cause while preserving first-seen order and the public function signature. Verify the result."""


def snapshot(source: Path, target: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name == "__pycache__" or name.endswith(".pyc")}
        if Path(directory).resolve() == source.resolve():
            ignored.update({".git", ".codestable"})
        return ignored

    shutil.copytree(
        source,
        target,
        ignore=ignore,
    )


def baseline(target: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "HEAD"], cwd=ROOT, check=True, stdout=subprocess.PIPE
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(target)], input=archive, check=True)


def seed(workspace: Path, package: Path) -> None:
    (workspace / "dedupe.py").write_text(
        """def dedupe(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
""",
        encoding="utf-8",
    )
    eval_root = workspace / ".eval" / "codestable"
    shutil.copytree(package, eval_root)
    (workspace / "AGENTS.md").write_text(
        """Use the CodeStable entry skill at .eval/codestable/skills/cs/SKILL.md for the user request. Read it completely, initialize its runtime when required, and continue through the routed lifecycle in this invocation. Do not modify .eval/.\n""",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(
        ["git", "-c", "user.name=benchmark", "-c", "user.email=benchmark@invalid", "commit", "-qm", "seed"],
        cwd=workspace,
        check=True,
    )


def verify(workspace: Path) -> tuple[bool, str | None]:
    check = subprocess.run(
        [
            "python3",
            "-c",
            "from dedupe import dedupe; "
            "assert dedupe([3,1,3,2,1]) == [3,1,2]; "
            "assert dedupe([]) == []; "
            "assert len(dedupe(list(range(50000)) * 2)) == 50000",
        ],
        cwd=workspace,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    if check.returncode:
        return False, "verifier_failed"
    if subprocess.run(["git", "diff", "--quiet", "--", ".eval"], cwd=workspace).returncode:
        return False, "evaluation_package_modified"
    return True, None


def run_once(package: Path, model: str, timeout: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="codestable-codex-run-") as raw:
        workspace = Path(raw)
        seed(workspace, package)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [
                    "codex", "-a", "never", "-s", "workspace-write", "-m", model,
                    "exec", "--json", "--ephemeral", "--ignore-user-config",
                    "-C", str(workspace), TASK,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"passed": False, "failure": "timeout", "duration_seconds": time.monotonic() - started}
        usage: dict[str, int] = {}
        tool_calls = 0
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "turn.completed":
                usage = event.get("usage") or {}
            item = event.get("item") or {}
            if event.get("type") == "item.completed" and item.get("type") in {
                "command_execution", "mcp_tool_call", "file_change"
            }:
                tool_calls += 1
        passed, failure = verify(workspace) if completed.returncode == 0 else (False, "codex_failed")
        work = workspace / ".codestable" / "work"
        state_files = list((work / "active").glob("*/state.json")) + list((work / "archive").glob("*/state.json"))
        route = None
        if state_files:
            try:
                route = json.loads(state_files[0].read_text(encoding="utf-8")).get("kind")
            except (OSError, json.JSONDecodeError):
                pass
        input_tokens = int(usage.get("input_tokens", 0))
        cached_tokens = int(usage.get("cached_input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        return {
            "passed": passed,
            "failure": failure,
            "route": route,
            "duration_seconds": time.monotonic() - started,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_tokens,
            "output_tokens": output_tokens,
            "uncached_tokens": max(0, input_tokens - cached_tokens) + output_tokens,
            "tool_calls": tool_calls,
            "codex_exit_code": completed.returncode,
        }


def aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    numeric = ("duration_seconds", "input_tokens", "cached_input_tokens", "output_tokens", "uncached_tokens", "tool_calls")
    return {
        "runs": len(rows),
        "passed": sum(bool(row.get("passed")) for row in rows),
        "routes_observed": sum(row.get("route") is not None for row in rows),
        "issue_routes": sum(row.get("route") == "issue" for row in rows),
        "failures": sorted(str(row["failure"]) for row in rows if row.get("failure")),
        **{
            f"median_{name}": statistics.median(float(row.get(name, 0)) for row in rows)
            for name in numeric
        },
    }


def comparison(left: dict[str, object], right: dict[str, object]) -> dict[str, float]:
    result = {
        "pass_rate_delta": float(right["passed"]) / float(right["runs"]) - float(left["passed"]) / float(left["runs"])
    }
    for name in ("duration_seconds", "uncached_tokens", "input_tokens", "output_tokens", "tool_calls"):
        baseline_value = float(left[f"median_{name}"])
        if baseline_value:
            result[f"median_{name}_change"] = float(right[f"median_{name}"]) / baseline_value - 1.0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-runs", type=int, default=5)
    parser.add_argument("--candidate-runs", type=int, default=5)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="validation/codex-host-benchmark.json")
    args = parser.parse_args()
    if min(args.baseline_runs, args.candidate_runs, args.jobs) < 1:
        parser.error("run counts and jobs must be positive")

    with tempfile.TemporaryDirectory(prefix="codestable-codex-packages-") as raw:
        temporary = Path(raw)
        base = temporary / "baseline"
        base.mkdir()
        baseline(base)
        candidate = temporary / "candidate"
        snapshot(ROOT, candidate)
        groups: dict[str, list[dict[str, object]]] = {"baseline": [], "candidate": []}
        schedule = [("baseline", base)] * args.baseline_runs + [("candidate", candidate)] * args.candidate_runs
        random.Random(0).shuffle(schedule)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            pending = [(name, pool.submit(run_once, package, args.model, args.timeout)) for name, package in schedule]
            for index, (name, future) in enumerate(pending, 1):
                print(f"[{index}/{len(schedule)}] {name}", flush=True)
                groups[name].append(future.result())

    baseline_result = {"version": "0.3.0", **aggregate(groups["baseline"])}
    candidate_result = {
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        **aggregate(groups["candidate"]),
    }
    result = {
        "schema_version": 1,
        "label": "measured" if min(args.baseline_runs, args.candidate_runs) >= 5 else "underpowered",
        "runtime_profile": {
            "host": "codex-cli",
            "host_version": subprocess.check_output(["codex", "--version"], text=True).strip(),
            "model": args.model,
            "adapter": "scripts/benchmark_codex_host.py@1",
            "sandbox": "workspace-write",
            "user_config": "ignored",
        },
        "task": {"id": "issue.performance-dedupe", "expected_route": "issue"},
        "baseline": baseline_result,
        "candidate": candidate_result,
        "comparison": comparison(baseline_result, candidate_result),
        "limitations": [
            "one synthetic task does not establish cross-task quality",
            "ChatGPT login does not expose a trustworthy USD price",
            "route state was not emitted, so route and Gate behavior remain underpowered",
        ],
    }
    if args.baseline_runs >= 10:
        first = aggregate(groups["baseline"][::2])
        second = aggregate(groups["baseline"][1::2])
        result["aa_calibration"] = {"baseline_a": first, "baseline_b": second, "comparison": comparison(first, second)}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    complete = all(group["passed"] == group["runs"] for group in (baseline_result, candidate_result))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
