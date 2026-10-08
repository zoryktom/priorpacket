from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from priorpacket.audit import write_audit_manifest
from priorpacket.batch import write_batch_report
from priorpacket.engine import analyze_request
from priorpacket.policy import load_bundle, load_policy, validate_policy
from priorpacket.render import write_outputs
from priorpacket.validation import run_validation_suite


ROOT = Path(__file__).resolve().parents[1]


class ProductWorkflowTests(unittest.TestCase):
    def test_policy_pack_validation_passes_demo_policy(self) -> None:
        policy = load_policy(ROOT / "examples/policies/knee_mri_policy.json")
        self.assertEqual(validate_policy(policy), [])

    def test_product_validation_suite_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = run_validation_suite(ROOT / "examples/cases/manifest.json", tmp)
            payload = json.loads(outputs["json"].read_text(encoding="utf-8"))

        self.assertTrue(payload["passed"])
        self.assertEqual(payload["passed_cases"], 5)
        self.assertEqual(payload["total_cases"], 5)

    def test_batch_report_contains_missing_proof_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_batch_report(
                policy_path=ROOT / "examples/policies/knee_mri_policy.json",
                bundles_dir=ROOT / "examples/cases/fhir",
                service_code="73721",
                out_dir=tmp,
            )
            with outputs["csv"].open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        by_request = {row["request_id"]: row for row in rows}
        self.assertEqual(by_request["missing_xray"]["status"], "needs_evidence")
        self.assertIn("radiograph", by_request["missing_xray"]["missing_actions"])
        self.assertEqual(
            by_request["missing_prior_treatment_evidence"]["missing_criteria"],
            "prior-treatment-evidence",
        )

    def test_audit_manifest_hashes_inputs_and_outputs(self) -> None:
        policy_path = ROOT / "examples/policies/knee_mri_policy.json"
        bundle_path = ROOT / "examples/fhir/knee_mri_bundle.json"
        policy = load_policy(policy_path)
        bundle = load_bundle(bundle_path)
        result = analyze_request(policy=policy, bundle=bundle, service_code="73721")

        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(result, tmp)
            manifest_path = write_audit_manifest(
                result=result,
                policy_path=policy_path,
                bundle_path=bundle_path,
                output_paths=outputs,
                out_dir=tmp,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["status"], "ready_for_review")
        self.assertEqual(len(manifest["inputs"]["policy"]["sha256"]), 64)
        self.assertEqual(len(manifest["outputs"]["html"]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
