from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from priorpacket.engine import PacketBuilder
from priorpacket.validator import CompletenessScorer


ROOT = Path(__file__).resolve().parents[1]


def load_example(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def bundle_resources(bundle: dict) -> list[dict]:
    return [entry["resource"] for entry in bundle["entry"]]


def test_builds_complete_oncology_pas_bundle() -> None:
    patient_record = load_example("oncology_patient.json")
    policy = load_example("oncology_policy_rule.json")

    packet = PacketBuilder().build(patient_record, policy).fhir_dump()
    resources = bundle_resources(packet)
    claim = next(resource for resource in resources if resource["resourceType"] == "Claim")

    assert claim["use"] == "preauthorization"
    assert claim["meta"]["profile"] == [
        "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim"
    ]
    assert claim["patient"]["reference"] == "Patient/pat-001"
    assert claim["item"][0]["productOrService"]["coding"][0]["code"] == "J9355"
    assert {resource["resourceType"] for resource in resources} >= {
        "Patient",
        "Coverage",
        "Condition",
        "Observation",
        "Encounter",
        "Claim",
    }

    audit = CompletenessScorer().audit(packet, policy)
    assert audit.passed is True
    assert audit.status == "pass"
    assert audit.score == 100
    assert audit.issues == []


def test_incomplete_packet_attributes_missing_lab() -> None:
    patient_record = load_example("oncology_patient.json")
    policy = load_example("oncology_policy_rule.json")
    incomplete = deepcopy(patient_record)
    incomplete["entry"] = [
        entry
        for entry in incomplete["entry"]
        if entry["resource"].get("id") != "obs-her2-001"
    ]

    packet = PacketBuilder().build(incomplete, policy).fhir_dump()
    audit = CompletenessScorer().audit(packet, policy)

    assert audit.passed is False
    assert audit.status == "incomplete"
    assert any(issue.code == "MISSING_LAB" and issue.criterion == "48642-3" for issue in audit.issues)


def test_successful_authorization_response_passes() -> None:
    patient_record = load_example("oncology_patient.json")
    policy = load_example("oncology_policy_rule.json")
    packet = PacketBuilder().build(patient_record, policy).fhir_dump()
    claim = next(resource for resource in bundle_resources(packet) if resource["resourceType"] == "Claim")
    packet["entry"].append(
        {
            "resource": {
                "resourceType": "ClaimResponse",
                "id": "cr-approved-001",
                "status": "active",
                "use": "preauthorization",
                "patient": {"reference": "Patient/pat-001"},
                "created": "2026-02-15T10:00:00Z",
                "request": {"reference": f"Claim/{claim['id']}"},
                "outcome": "complete",
                "disposition": "Approved for requested biologic therapy.",
                "preAuthRef": "AUTH-2026-0001",
            }
        }
    )

    audit = CompletenessScorer().audit(packet, policy)

    assert audit.passed is True
    assert audit.status == "pass"
    assert audit.score == 100


def test_rejected_authorization_response_is_attributed() -> None:
    patient_record = load_example("oncology_patient.json")
    policy = load_example("oncology_policy_rule.json")
    packet = PacketBuilder().build(patient_record, policy).fhir_dump()
    claim = next(resource for resource in bundle_resources(packet) if resource["resourceType"] == "Claim")
    packet["entry"].append(
        {
            "resource": {
                "resourceType": "ClaimResponse",
                "id": "cr-denial-001",
                "status": "active",
                "use": "preauthorization",
                "patient": {"reference": "Patient/pat-001"},
                "created": "2026-02-15T10:00:00Z",
                "request": {"reference": f"Claim/{claim['id']}"},
                "outcome": "error",
                "disposition": "Denied: payer requires manual review of molecular pathology attachment.",
            }
        }
    )

    audit = CompletenessScorer().audit(packet, policy)

    assert audit.passed is False
    assert audit.status == "rejected"
    rejection = next(issue for issue in audit.issues if issue.code == "AUTH_REJECTED")
    assert rejection.resource == "ClaimResponse/cr-denial-001"
    assert "Denied" in rejection.message


def test_cli_build_and_audit_success(tmp_path: Path) -> None:
    out_path = tmp_path / "packet.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "priorpacket.cli",
            "build",
            "--patient",
            str(ROOT / "examples" / "oncology_patient.json"),
            "--rule",
            str(ROOT / "examples" / "oncology_policy_rule.json"),
            "--out",
            str(out_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    assert out_path.exists()

    audit = subprocess.run(
        [
            sys.executable,
            "-m",
            "priorpacket.cli",
            "audit",
            str(out_path),
            "--policy",
            str(ROOT / "examples" / "oncology_policy_rule.json"),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert audit.returncode == 0, audit.stderr
    result = json.loads(audit.stdout)
    assert result["status"] == "pass"
    assert result["score"] == 100
