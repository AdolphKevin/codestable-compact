from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta_support import MetaProject, policy


class PolicyRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = MetaProject(Path(self.temporary.name))
        self.root = self.project.root

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_shipped_policy_registry_has_complete_fixture_coverage(self) -> None:
        audit = policy.audit_policies(self.root)
        self.assertTrue(audit["ok"])
        self.assertEqual(audit["policy_count"], 9)
        self.assertGreaterEqual(audit["fixture_count"], 12)
        self.assertTrue(all(item["evolvable"] for item in audit["coverage"].values()))

    def test_historical_contracts_layer_alias_is_canonicalized(self) -> None:
        audit = policy.audit_policies(self.root)
        covered = audit["coverage"]["context.selective-loading"]["covered_layers"]
        self.assertIn("contract", covered)
        self.assertNotIn("contracts", covered)

    def test_no_fixture_coverage_no_evolution(self) -> None:
        registry_path = self.root / ".codestable/meta/policy-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        target = next(item for item in registry["policies"] if item["id"] == "entry.routing-and-continuation")
        target["fixture_ids"] = []
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        audit = policy.audit_policies(self.root)
        self.assertFalse(audit["ok"])
        self.assertTrue(any(item["code"] == "whitelisted_without_fixture" for item in audit["issues"]))
        with self.assertRaises(policy.PolicyError):
            policy.proposal_requirements(
                self.root,
                policy_ids=["entry.routing-and-continuation"],
                change_type="workflow_routing",
                fixture_ids=["routing.performance-to-issue", "e2e.normal-run-no-meta"],
            )

    def test_owner_authority_comes_from_policy_not_proposer(self) -> None:
        routing = policy.proposal_requirements(
            self.root,
            policy_ids=["entry.routing-and-continuation"],
            change_type="workflow_routing",
            fixture_ids=["routing.performance-to-issue", "e2e.normal-run-no-meta"],
        )
        self.assertEqual(routing["promotion_authority"], "owner")
        copy = policy.proposal_requirements(
            self.root,
            policy_ids=["interaction.route-summary-copy"],
            change_type="prompt_copy",
            fixture_ids=["routing.auto-continue", "e2e.normal-run-no-meta"],
        )
        self.assertEqual(copy["promotion_authority"], "agent")

    def test_fixture_set_hash_changes_when_fixture_changes(self) -> None:
        ids = ["routing.performance-to-issue", "e2e.normal-run-no-meta"]
        before = policy.fixture_set_sha256(self.root, ids)
        fixture = self.root / ".codestable/evals/fixtures/routing/routing.performance-to-issue/fixture.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        data["title"] += " changed"
        fixture.write_text(json.dumps(data), encoding="utf-8")
        after = policy.fixture_set_sha256(self.root, ids)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
