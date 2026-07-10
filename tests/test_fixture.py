from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta_support import MetaProject, REPO

import cs_fixture as fixture_runner  # type: ignore


class PublicFixtureRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = MetaProject(Path(self.temporary.name))
        self.root = self.project.root

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_file_predicate_is_measured(self) -> None:
        result = fixture_runner.run_suite(
            self.root,
            suite_root=REPO,
            fixture_ids=["contract.minimality-ladder"],
            policy_ids=[],
            all_active=False,
            timeout=120,
            host_adapter_result=None,
        )
        self.assertEqual(result["counts"], {"passed": 1, "failed": 0, "underpowered": 0})
        self.assertTrue(result["promotion_eligible"])
        self.assertEqual(result["results"][0]["label"], "measured")

    def test_python_unittest_fixture_executes_real_package_test(self) -> None:
        result = fixture_runner.run_suite(
            self.root,
            suite_root=REPO,
            fixture_ids=["contract.normal-context-isolation"],
            policy_ids=[],
            all_active=False,
            timeout=120,
            host_adapter_result=None,
        )
        self.assertEqual(result["counts"]["passed"], 1)
        self.assertEqual(result["results"][0]["runner_type"], "python_unittest")
        self.assertEqual(result["results"][0]["measurement"]["exit_code"], 0)

    def test_real_host_fixture_is_underpowered_without_adapter(self) -> None:
        result = fixture_runner.run_suite(
            self.root,
            suite_root=REPO,
            fixture_ids=["routing.performance-to-issue"],
            policy_ids=[],
            all_active=False,
            timeout=120,
            host_adapter_result=None,
        )
        self.assertEqual(result["counts"]["underpowered"], 1)
        self.assertFalse(result["promotion_eligible"])
        self.assertIn("real host/model", result["results"][0]["reason"])

    def test_host_adapter_result_is_never_silently_upgraded_to_measured(self) -> None:
        host = self.root / "host-result.json"
        host.write_text(
            json.dumps({
                "routing.performance-to-issue": {
                    "status": "passed",
                    "label": "soft",
                    "measurement": {"profile": self.project.PROFILE, "runs": 5},
                }
            }),
            encoding="utf-8",
        )
        result = fixture_runner.run_suite(
            self.root,
            suite_root=REPO,
            fixture_ids=["routing.performance-to-issue"],
            policy_ids=[],
            all_active=False,
            timeout=120,
            host_adapter_result=host,
        )
        self.assertEqual(result["results"][0]["label"], "soft")
        self.assertEqual(result["labels"]["measured"], 0)


if __name__ == "__main__":
    unittest.main()
