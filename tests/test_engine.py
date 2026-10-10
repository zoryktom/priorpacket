from __future__ import annotations

import json
import unittest
from pathlib import Path

from priorpacket.davinci import build_gap_task
from priorpacket.engine import analyze_request
from priorpacket.policy import load_bundle, load_policy

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def test_demo_bundle_is_ready_for_review(self) -> None:
        policy = load_policy(ROOT / "examples/policies/knee_mri_policy.json")
        bundle = load_bundle(ROOT / "examples/fhir/knee_mri_bundle.json")

        result = analyze_request(policy=policy, bundle=bundle, service_code="73721")

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(result.risk_band, "low")
        self.assertEqual(result.score_percent, 100)
        self.assertEqual(result.missing_actions, ())

        task = build_gap_task(result)
        self.assertEqual(task["resourceType"], "Task")
        self.assertEqual(task["status"], "ready")

    def test_missing_documentation_is_flagged(self) -> None:
        policy = load_policy(ROOT / "examples/policies/knee_mri_policy.json")
        bundle = load_bundle(ROOT / "examples/fhir/knee_mri_bundle.json")
        bundle["entry"] = [
            entry
            for entry in bundle["entry"]
            if entry["resource"]["resourceType"] != "DocumentReference"
        ]

        result = analyze_request(policy=policy, bundle=bundle, service_code="73721")

        self.assertEqual(result.status, "not_ready")
        self.assertEqual(result.risk_band, "high")
        self.assertTrue(
            any("PT" in action or "locking" in action for action in result.missing_actions)
        )

        serialized = json.dumps(result.to_dict())
        self.assertIn("prior-treatment-evidence", serialized)


if __name__ == "__main__":
    unittest.main()
