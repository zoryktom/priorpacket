"""One-command demonstration over three representative synthetic benchmark cases."""
from __future__ import annotations

import json
from pathlib import Path

from .audit import write_audit_manifest
from .benchmark import DEFAULT_MANIFEST, evaluate, load_manifest
from .render import write_outputs

DEMO_CASES = ("A03-cgm-ready", "B07-cgm-missing-hba1c", "C01-cgm-unit-mismatch")


def run_demo(out_dir: str | Path = "reports/demo", manifest_path: str | Path = DEFAULT_MANIFEST) -> list[dict[str, str]]:
    manifest = load_manifest(manifest_path)
    root = Path(manifest["_root"])
    cases = {case["id"]: case for case in manifest["cases"]}
    summary: list[dict[str, str]] = []
    for case_id in DEMO_CASES:
        case = cases[case_id]
        policy_path = root / case["policy"]
        bundle_path = root / case["bundle"]
        result = evaluate(
            json.loads(policy_path.read_text(encoding="utf-8")),
            json.loads(bundle_path.read_text(encoding="utf-8")),
            str(case["service_code"]),
            request_id=case_id,
        )
        case_dir = Path(out_dir) / case_id
        outputs = write_outputs(result, case_dir)
        write_audit_manifest(
            result=result, policy_path=policy_path, bundle_path=bundle_path, output_paths=outputs, out_dir=case_dir
        )
        summary.append(
            {
                "case": case_id,
                "description": case["description"],
                "outcome": result.outcome,
                "expected_outcome": case["expected"]["outcome"],
                "output": str(case_dir),
            }
        )
    return summary
