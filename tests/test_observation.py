from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO / "skills" / "cs" / "assets" / "project"
OBSERVE_PATH = ASSET_ROOT / ".codestable" / "tools" / "cs_observe.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observe = load_module("codestable_compact_observe_test", OBSERVE_PATH)


class PassiveObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(ASSET_ROOT, self.root, dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def start(self, run_id: str = "run-normal") -> dict:
        return observe.start_observation(
            self.root,
            work="2026-07-10-slow-stage",
            task_id="slow-stage",
            kind="issue",
            risk_level=1,
            entry="cs",
            route="cs-issue",
            model_profile="fixed-model",
            adapter="fixed-adapter",
            start_action="inspect",
            repository_commit="abc123",
            run_id=run_id,
        )

    def finish_passed(self, run_id: str, *, signals: tuple[str, ...] = ()) -> dict:
        return observe.finish_observation(
            self.root,
            run_id,
            status="completed",
            end_action="verify",
            task_validation={
                "status": "passed",
                "verifier_id": "project-tests",
                "command": "python3 -m unittest",
                "exit_code": 0,
                "evidence": [],
                "issued_by": "task-runner",
            },
            signals=signals,
            metrics={"tool_calls": 8, "context_bytes": 42000},
            note="normal task completed",
        )

    def test_normal_run_only_writes_temporary_observation(self) -> None:
        registry_path = self.root / ".codestable" / "harness" / "registry.json"
        registry_before = registry_path.read_text(encoding="utf-8")
        evolution_index = self.root / ".codestable" / "evolution" / "index.jsonl"
        evolution_before = evolution_index.read_text(encoding="utf-8")

        started = self.start()
        self.assertTrue(started["recorded"])
        event = observe.append_event(
            self.root,
            "run-normal",
            "action_selected",
            {"action": "inspect"},
        )
        self.assertTrue(event["recorded"])
        finished = self.finish_passed("run-normal")

        self.assertIn("observations/pending/run-normal", finished["path"])
        item = observe.load_observation(self.root, "run-normal")
        self.assertEqual(item["state"], "pending")
        self.assertEqual(item["meta"]["status"], "finished")
        self.assertEqual(item["outcome"]["task_validation"]["status"], "passed")
        self.assertFalse(item["outcome"]["selected_for_evolution"])

        # Passive recording must not create a case, snapshot, proposal, or evaluation.
        self.assertEqual(registry_path.read_text(encoding="utf-8"), registry_before)
        self.assertEqual(evolution_index.read_text(encoding="utf-8"), evolution_before)
        cases = list((self.root / ".codestable" / "evolution" / "cases").glob("*/case.json"))
        self.assertEqual(cases, [])

    def test_signal_flags_but_never_starts_evolution(self) -> None:
        self.start("run-flagged")
        finished = self.finish_passed(
            "run-flagged",
            signals=("routing.user_corrected",),
        )
        self.assertIn("observations/flagged/run-flagged", finished["path"])
        item = observe.load_observation(self.root, "run-flagged")
        self.assertEqual(item["state"], "flagged")
        self.assertEqual(item["meta"]["signals"], ["routing.user_corrected"])
        self.assertEqual(list((self.root / ".codestable" / "evolution" / "cases").glob("*/case.json")), [])

    def test_raw_content_fields_are_rejected(self) -> None:
        self.start("run-private")
        for payload in (
            {"raw_prompt": "do not store"},
            {"nested": {"diff": "--- a\n+++ b"}},
            {"credentials": {"token": "secret"}},
            {"private_holdout": ["hidden-task"]},
            {"stdout": "full command output"},
            {"nested": {"stderr": "stack trace"}},
            {"tool_output": "unbounded output"},
        ):
            with self.assertRaises(observe.ObservationError):
                observe.append_event(self.root, "run-private", "tool_called", payload)

    def test_only_finished_observations_can_be_selected(self) -> None:
        self.start("run-selection")
        with self.assertRaises(observe.ObservationError):
            observe.select_observation(self.root, "run-selection", case_id="case-a")
        self.finish_passed("run-selection")
        selected = observe.select_observation(self.root, "run-selection", case_id="case-a")
        self.assertEqual(selected["state"], "selected")
        item = observe.load_observation(self.root, "run-selection")
        self.assertTrue(item["outcome"]["selected_for_evolution"])
        self.assertEqual(item["meta"]["selection"]["case_ids"], ["case-a"])

    def test_validation_is_strongly_typed(self) -> None:
        self.start("run-validation")
        with self.assertRaises(observe.ObservationError):
            observe.finish_observation(
                self.root,
                "run-validation",
                status="completed",
                end_action="verify",
                task_validation={
                    "status": "passed",
                    "verifier_id": None,
                    "exit_code": 0,
                    "evidence": [],
                },
            )

    def test_cli_end_keeps_validation_command_separate_from_dispatch(self) -> None:
        self.start("run-cli-end")
        completed = subprocess.run(
            [
                sys.executable,
                str(OBSERVE_PATH),
                "end",
                "--root",
                str(self.root),
                "--run",
                "run-cli-end",
                "--status",
                "completed",
                "--end-action",
                "verify",
                "--validation-status",
                "passed",
                "--verifier-id",
                "project-tests",
                "--command",
                "python3 -m unittest",
                "--exit-code",
                "0",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        item = observe.load_observation(self.root, "run-cli-end")
        self.assertEqual(item["outcome"]["task_validation"]["command"], "python3 -m unittest")

    def test_event_budget_drops_metadata_without_failing_run(self) -> None:
        config_path = self.root / ".codestable" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["observability"]["limits"]["max_events"] = 1
        config_path.write_text(json.dumps(config), encoding="utf-8")
        self.start("run-budget")
        first = observe.append_event(self.root, "run-budget", "action_selected", {"action": "inspect"})
        second = observe.append_event(self.root, "run-budget", "action_selected", {"action": "verify"})
        self.assertTrue(first["recorded"])
        self.assertFalse(second["recorded"])
        self.assertEqual(second["reason"], "event_limit")
        self.finish_passed("run-budget")

    def test_legacy_shared_index_is_not_mutated(self) -> None:
        index = self.root / ".codestable" / "observations" / "index.jsonl"
        index.write_text("legacy tracked content\n", encoding="utf-8")

        self.start("run-indexless")
        self.finish_passed("run-indexless")
        observe.flag_observation(
            self.root, "run-indexless", signals=("routing.user_corrected",)
        )
        observe.select_observation(self.root, "run-indexless", case_id="case-a")

        self.assertEqual(index.read_text(encoding="utf-8"), "legacy tracked content\n")


if __name__ == "__main__":
    unittest.main()
