#!/usr/bin/env python3
"""Generate the PriorPacket synthetic benchmark (benchmark/v1).

All data is synthetic. Expected outcomes are authored here from the policy semantics
documented in docs/policy-semantics.md, independently of the engine; the benchmark runner
compares engine output against them. Run with --check to verify committed files are current.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmark" / "v1"

CPT = "http://www.ama-assn.org/go/cpt"
ICD = "http://hl7.org/fhir/sid/icd-10-cm"
LOINC = "http://loinc.org"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
HCPCS = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"
REQUEST_DATE = "2026-09-12"
PATIENT = "synthetic-001"
SUBJECT = {"reference": f"Patient/{PATIENT}"}


# --------------------------------------------------------------------------- policies
def msk_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy_id": "bench-msk-knee-mri",
        "policy_version": "1.0.0",
        "status": "active",
        "effective_start": "2026-01-01",
        "effective_end": "2026-12-31",
        "payer": "Synthetic Demo Health Plan",
        "service": {"name": "MRI lower extremity joint without contrast", "codes": ["73721"]},
        "criteria": [
            {
                "id": "knee-pain-diagnosis", "kind": "condition",
                "label": "Knee pain or internal derangement diagnosis",
                "codes": ["M25.561", "M23.91", "S83.91XA"], "code_systems": [ICD], "weight": 20,
                "missing_action": "Add a current diagnosis supporting the requested knee MRI.",
            },
            {
                "id": "recent-xray", "kind": "procedure", "label": "Recent knee radiograph",
                "codes": ["73560", "73562", "73564"], "code_systems": [CPT],
                "within_days": 90, "weight": 20,
                "missing_action": "Attach a knee radiograph report from the last 90 days.",
            },
            {
                "id": "prior-treatment-evidence", "kind": "document",
                "label": "Documented prior treatment attempt",
                "keywords": ["physical therapy", "six weeks", "nsaid"],
                "require_all_keywords": True,
                "conflict_keywords": ["refused physical therapy", "did not attend physical therapy"],
                "within_days": 180, "weight": 30,
                "missing_action": "Collect notes documenting the required prior treatment attempt.",
            },
            {
                "id": "mechanical-symptoms", "kind": "document",
                "label": "Mechanical symptoms or functional limitation",
                "keywords": ["locking", "catching", "instability", "limited range of motion"],
                "weight": 15,
                "missing_action": "Document mechanical symptoms or functional limitation.",
            },
            {
                "id": "acute-trauma", "kind": "condition", "label": "Acute knee trauma",
                "codes": ["S83.91XA", "S89.91XA"], "code_systems": [ICD], "weight": 25,
                "missing_action": "Add a trauma diagnosis if the urgent pathway is used.",
            },
        ],
        "pathways": [
            {"id": "standard-pathway", "label": "Standard MRI pathway",
             "requires": ["knee-pain-diagnosis", "recent-xray", "prior-treatment-evidence", "mechanical-symptoms"]},
            {"id": "trauma-pathway", "label": "Urgent MRI after acute trauma",
             "requires": ["knee-pain-diagnosis", "recent-xray", "acute-trauma", "mechanical-symptoms"]},
        ],
    }


def cgm_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy_id": "bench-diabetes-cgm",
        "policy_version": "1.0.0",
        "status": "active",
        "effective_start": "2026-01-01",
        "effective_end": "2026-12-31",
        "payer": "Synthetic Demo Health Plan",
        "service": {"name": "Continuous glucose monitor", "codes": ["E2103"]},
        "criteria": [
            {
                "id": "diabetes-diagnosis", "kind": "condition", "label": "Type 2 diabetes diagnosis",
                "codes": ["E11.65", "E11.9", "E11.8"], "code_systems": [ICD], "weight": 20,
                "missing_action": "Add a current diabetes diagnosis.",
            },
            {
                "id": "recent-hba1c", "kind": "observation",
                "label": "Hemoglobin A1c at or above 7.0 % within 90 days",
                "codes": ["4548-4"], "code_systems": [LOINC], "operator": ">=", "value": 7.0,
                "unit": "%", "unit_aliases": ["percent"], "within_days": 90, "weight": 30,
                "missing_action": "Attach an HbA1c result of at least 7.0 % from the last 90 days.",
            },
            {
                "id": "insulin-therapy", "kind": "medication", "label": "Current insulin therapy",
                "codes": ["261551", "253182"], "code_systems": [RXNORM], "within_days": 365,
                "weight": 25, "missing_action": "Document current insulin therapy.",
            },
            {
                "id": "diabetes-education", "kind": "document", "label": "Diabetes education (optional)",
                "keywords": ["diabetes education"], "weight": 10, "required": False,
                "missing_action": "Consider documenting diabetes self-management education.",
            },
        ],
        "pathways": [
            {"id": "standard-pathway", "label": "Insulin-treated diabetes pathway",
             "requires": ["diabetes-diagnosis", "recent-hba1c", "insulin-therapy", "diabetes-education"]},
        ],
    }


# --------------------------------------------------------------------------- bundles
def bundle(*resources: dict[str, Any]) -> dict[str, Any]:
    return {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": r} for r in resources]}


def patient(pid: str = PATIENT) -> dict[str, Any]:
    return {"resourceType": "Patient", "id": pid, "name": [{"given": ["Synthetic"], "family": "Patient"}],
            "gender": "unknown", "birthDate": "1970-01-01"}


def service_request(code: str, system: str, date: str = REQUEST_DATE, rid: str = "sr-1") -> dict[str, Any]:
    return {"resourceType": "ServiceRequest", "id": rid, "status": "active", "intent": "order",
            "authoredOn": date, "subject": SUBJECT, "code": {"coding": [{"system": system, "code": code}]}}


def condition(code: str, rid: str, date: str = "2026-08-01") -> dict[str, Any]:
    return {"resourceType": "Condition", "id": rid, "subject": SUBJECT, "recordedDate": date,
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "code": {"coding": [{"system": ICD, "code": code}]}}


def procedure(code: str, rid: str, date: str, subject: Any = SUBJECT) -> dict[str, Any]:
    return {"resourceType": "Procedure", "id": rid, "status": "completed", "subject": subject,
            "performedDateTime": date, "code": {"coding": [{"system": CPT, "code": code}]}}


def document(text: str, rid: str, date: str = "2026-09-01", subject: Any = SUBJECT) -> dict[str, Any]:
    doc = {"resourceType": "DocumentReference", "id": rid, "status": "current", "date": date,
           "type": {"coding": [{"system": LOINC, "code": "11506-3"}]}, "description": text}
    if subject is not None:
        doc["subject"] = subject
    return doc


def hba1c(value: float, rid: str = "obs-a1c", date: str = "2026-08-20", unit: str | None = "%",
          system: str = LOINC) -> dict[str, Any]:
    quantity: dict[str, Any] = {"value": value}
    if unit is not None:
        quantity["unit"] = unit
    return {"resourceType": "Observation", "id": rid, "status": "final", "subject": SUBJECT,
            "effectiveDateTime": date, "code": {"coding": [{"system": system, "code": "4548-4"}]},
            "valueQuantity": quantity}


def insulin(rid: str = "med-insulin", date: str = "2026-06-01") -> dict[str, Any]:
    return {"resourceType": "MedicationRequest", "id": rid, "status": "active", "intent": "order",
            "subject": SUBJECT, "authoredOn": date,
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "261551"}]}}


def msk_ready() -> dict[str, Any]:
    return bundle(
        patient(), service_request("73721", CPT), condition("M25.561", "cond-knee"),
        procedure("73562", "proc-xray", "2026-08-15"),
        document("Physical therapy completed for six weeks with NSAID trial. Persistent pain with "
                 "catching and limited range of motion.", "doc-pt"),
    )


def cgm_ready() -> dict[str, Any]:
    return bundle(
        patient(), service_request("E2103", HCPCS), condition("E11.65", "cond-t2dm"),
        hba1c(8.2), insulin(),
    )


def find(b: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(e["resource"] for e in b["entry"] if e["resource"].get("id") == rid)


def drop(b: dict[str, Any], *rids: str) -> dict[str, Any]:
    b = copy.deepcopy(b)
    b["entry"] = [e for e in b["entry"] if e["resource"].get("id") not in rids]
    return b


def with_(b: dict[str, Any], *resources: Any) -> dict[str, Any]:
    b = copy.deepcopy(b)
    b["entry"].extend({"resource": r} for r in resources)
    return b


def replace(b: dict[str, Any], rid: str, new: dict[str, Any]) -> dict[str, Any]:
    return with_(drop(b, rid), new)


# --------------------------------------------------------------------------- cases
CASES: list[dict[str, Any]] = []


def case(cid: str, category: str, workflow: str, desc: str, bundle_: Any, outcome: str, risk: str,
         score: int | None, missing: list[str] | None = None, issues: list[str] | None = None,
         service: str | None = None, policy_obj: Any = None) -> None:
    CASES.append({
        "id": cid, "category": category, "workflow": workflow, "description": desc,
        "policy": {"msk": "msk_knee_mri", "cgm": "diabetes_cgm"}[workflow],
        "policy_override": policy_obj, "bundle_data": bundle_,
        "service_code": service or {"msk": "73721", "cgm": "E2103"}[workflow],
        "expected": {"outcome": outcome, "risk_band": risk, "score_percent": score,
                     "missing_criteria": missing or [], "issue_codes": sorted(issues or [])},
    })


def build_cases() -> None:
    mr, cr = msk_ready(), cgm_ready()
    # A. positive
    case("A01-msk-ready-standard", "A_positive", "msk", "All standard-pathway criteria met.", mr, "READY", "low", 100)
    case("A02-msk-ready-trauma", "A_positive", "msk", "Urgent trauma pathway satisfied without prior-treatment notes.",
         bundle(patient(), service_request("73721", CPT), condition("S83.91XA", "cond-trauma"),
                procedure("73562", "proc-xray", "2026-08-15"),
                document("Knee instability and locking after a fall.", "doc-mech")),
         "READY", "low", 100)
    case("A03-cgm-ready", "A_positive", "cgm", "All mandatory criteria met; optional education absent.", cr, "READY", "low", 100)
    case("A04-cgm-boundary-value", "A_positive", "cgm", "HbA1c exactly at the 7.0 % threshold qualifies (>=).",
         replace(cr, "obs-a1c", hba1c(7.0)), "READY", "low", 100)
    case("A05-cgm-boundary-window", "A_positive", "cgm", "HbA1c exactly 90 days old is inside the inclusive window.",
         replace(cr, "obs-a1c", hba1c(8.2, date="2026-06-14")), "READY", "low", 100)
    case("A06-cgm-unit-alias", "A_positive", "cgm", "Unit alias 'percent' is accepted.",
         replace(cr, "obs-a1c", hba1c(8.2, unit="percent")), "READY", "low", 100)
    case("A07-msk-duplicate-identical", "A_positive", "msk", "An exact duplicate resource is de-duplicated, not penalized.",
         with_(mr, copy.deepcopy(find(mr, "cond-knee"))), "READY", "low", 100, [], ["DUPLICATE_RESOURCE"])
    # B. missing evidence
    case("B01-msk-missing-xray", "B_missing", "msk", "No radiograph.", drop(mr, "proc-xray"),
         "INCOMPLETE", "moderate", 76, ["recent-xray"], ["MISSING_EVIDENCE"])
    case("B02-msk-missing-prior-treatment", "B_missing", "msk", "No prior-treatment document.",
         replace(mr, "doc-pt", document("Knee catching and limited range of motion.", "doc-pt")),
         "INCOMPLETE", "moderate", 65, ["prior-treatment-evidence"], ["MISSING_EVIDENCE"])
    case("B03-msk-missing-diagnosis", "B_missing", "msk", "No qualifying diagnosis.", drop(mr, "cond-knee"),
         "INCOMPLETE", "moderate", 76, ["knee-pain-diagnosis"], ["MISSING_EVIDENCE"])
    case("B04-msk-missing-mechanical", "B_missing", "msk", "Prior treatment documented but no mechanical symptoms.",
         replace(mr, "doc-pt", document("Physical therapy completed for six weeks with NSAID trial.", "doc-pt")),
         "INCOMPLETE", "moderate", 82, ["mechanical-symptoms"], ["MISSING_EVIDENCE"])
    case("B05-msk-only-patient-and-request", "B_missing", "msk", "Only patient and order; no clinical evidence.",
         bundle(patient(), service_request("73721", CPT)), "INCOMPLETE", "high", 0,
         ["knee-pain-diagnosis", "recent-xray", "prior-treatment-evidence", "mechanical-symptoms"], ["MISSING_EVIDENCE"])
    case("B06-msk-xray-expired", "B_missing", "msk", "Radiograph 91 days old, outside the 90-day window.",
         replace(mr, "proc-xray", procedure("73562", "proc-xray", "2026-06-13")),
         "INCOMPLETE", "moderate", 76, ["recent-xray"], ["EVIDENCE_OUTSIDE_WINDOW"])
    case("B07-cgm-missing-hba1c", "B_missing", "cgm", "No HbA1c result.", drop(cr, "obs-a1c"),
         "INCOMPLETE", "high", 60, ["recent-hba1c"], ["MISSING_EVIDENCE"])
    case("B08-cgm-hba1c-below-threshold", "B_missing", "cgm", "HbA1c 6.8 % does not meet >= 7.0.",
         replace(cr, "obs-a1c", hba1c(6.8)), "INCOMPLETE", "high", 60, ["recent-hba1c"], ["VALUE_OUT_OF_RANGE"])
    case("B09-cgm-hba1c-expired", "B_missing", "cgm", "Qualifying HbA1c is 91 days old.",
         replace(cr, "obs-a1c", hba1c(8.2, date="2026-06-13")), "INCOMPLETE", "high", 60,
         ["recent-hba1c"], ["EVIDENCE_OUTSIDE_WINDOW"])
    case("B10-cgm-missing-insulin", "B_missing", "cgm", "No insulin therapy documented.", drop(cr, "med-insulin"),
         "INCOMPLETE", "high", 67, ["insulin-therapy"], ["MISSING_EVIDENCE"])
    case("B11-cgm-missing-diagnosis", "B_missing", "cgm", "No diabetes diagnosis.", drop(cr, "cond-t2dm"),
         "INCOMPLETE", "high", 73, ["diabetes-diagnosis"], ["MISSING_EVIDENCE"])
    case("B12-cgm-request-for-other-service", "B_missing", "cgm", "Packet orders a different service code.",
         replace(cr, "sr-1", service_request("E0607", HCPCS)), "INCOMPLETE", "moderate", 100, [],
         ["SERVICE_CODE_MISMATCH"])
    case("B13-cgm-no-service-request", "B_missing", "cgm", "Packet has no ServiceRequest.", drop(cr, "sr-1"),
         "INCOMPLETE", "high", 27, [],
         ["MISSING_SERVICE_REQUEST", "NO_REFERENCE_DATE", "POLICY_EFFECTIVE_DATE_UNVERIFIABLE"])
    case("B14-cgm-entered-in-error", "B_missing", "cgm", "The only HbA1c is marked entered-in-error.",
         replace(cr, "obs-a1c", {**hba1c(8.2), "status": "entered-in-error"}), "INCOMPLETE", "high", 60,
         ["recent-hba1c"], ["RESOURCE_STATUS_INVALID"])
    # C. needs review (ambiguous, conflicting, or unverifiable evidence)
    case("C01-cgm-unit-mismatch", "C_review", "cgm", "HbA1c reported in mg/dL, not %.",
         replace(cr, "obs-a1c", hba1c(8.2, unit="mg/dL")), "NEEDS_REVIEW", "high", 60, [], ["UNIT_MISMATCH"])
    case("C02-cgm-unit-missing", "C_review", "cgm", "HbA1c has no unit.",
         replace(cr, "obs-a1c", hba1c(8.2, unit=None)), "NEEDS_REVIEW", "high", 60, [], ["UNIT_MISSING"])
    case("C03-cgm-conflicting-values", "C_review", "cgm", "Two in-window HbA1c values straddle the threshold.",
         with_(cr, hba1c(6.5, rid="obs-a1c-2", date="2026-08-25")), "NEEDS_REVIEW", "high", 60, [],
         ["CONFLICTING_EVIDENCE", "VALUE_OUT_OF_RANGE"])
    case("C04-cgm-code-system-mismatch", "C_review", "cgm", "HbA1c coded in a non-LOINC system.",
         replace(cr, "obs-a1c", hba1c(8.2, system="http://example.org/local-codes")), "NEEDS_REVIEW", "high", 60,
         [], ["CODE_SYSTEM_MISMATCH"])
    case("C05-msk-wrong-patient-xray", "C_review", "msk", "Radiograph belongs to a different patient.",
         replace(mr, "proc-xray", procedure("73562", "proc-xray", "2026-08-15", {"reference": "Patient/other-999"})),
         "NEEDS_REVIEW", "moderate", 76, [], ["UNRESOLVED_REFERENCE", "WRONG_PATIENT"])
    case("C06-msk-contradicted-treatment", "C_review", "msk", "A note says the patient refused physical therapy.",
         with_(mr, document("Patient refused physical therapy.", "doc-refused")), "NEEDS_REVIEW", "moderate", 65, [],
         ["CONFLICTING_EVIDENCE", "CONTRADICTED_BY_RECORD"])
    case("C07-msk-undated-xray", "C_review", "msk", "Radiograph has no date, so the window cannot be checked.",
         replace(mr, "proc-xray", {k: v for k, v in find(mr, "proc-xray").items() if k != "performedDateTime"}),
         "NEEDS_REVIEW", "moderate", 76, [], ["MISSING_DATE"])
    case("C08-cgm-duplicate-id-conflict", "C_review", "cgm", "Two different resources share one id.",
         with_(cr, {**hba1c(6.5), "id": "obs-a1c"}), "NEEDS_REVIEW", "high", 60, [], ["DUPLICATE_ID_CONFLICT"])
    case("C09-cgm-unresolved-reference", "C_review", "cgm", "A report cites a result that is not in the packet.",
         with_(cr, {"resourceType": "DiagnosticReport", "id": "dr-1", "status": "final", "subject": SUBJECT,
                    "code": {"coding": [{"system": LOINC, "code": "4548-4"}]},
                    "result": [{"reference": "Observation/missing-obs"}]}),
         "NEEDS_REVIEW", "moderate", 100, [], ["UNRESOLVED_REFERENCE"])
    # D. invalid input
    case("D01-input-not-a-bundle", "D_invalid", "cgm", "Input is a JSON array, not a Bundle.", [], "INVALID_INPUT",
         "high", 0, [], ["NOT_A_BUNDLE"])
    case("D02-input-empty-bundle", "D_invalid", "cgm", "Bundle has no entries.",
         {"resourceType": "Bundle", "type": "collection", "entry": []}, "INVALID_INPUT", "high", 0, [], ["EMPTY_BUNDLE"])
    case("D03-input-no-patient", "D_invalid", "cgm", "Bundle has no Patient.", drop(cr, PATIENT),
         "INVALID_INPUT", "high", 0, [], ["MISSING_PATIENT"])
    malformed = copy.deepcopy(cr)
    malformed["entry"].append({"resource": "oops"})
    case("D04-input-malformed-resource", "D_invalid", "cgm", "An entry resource is not an object.", malformed,
         "INVALID_INPUT", "high", 0, [], ["MALFORMED_RESOURCE"])
    bad = cgm_policy(); bad["criteria"][1]["bogus_rule"] = 1
    case("D05-policy-unknown-field", "D_invalid", "cgm", "Policy has an unknown rule field.", cr, "INVALID_INPUT",
         "high", 0, [], ["POLICY_INVALID"], policy_obj=bad)
    bad = cgm_policy(); bad["schema_version"] = 99
    case("D06-policy-unsupported-schema", "D_invalid", "cgm", "Policy schema_version is unsupported.", cr,
         "INVALID_INPUT", "high", 0, [], ["POLICY_UNSUPPORTED_SCHEMA_VERSION"], policy_obj=bad)
    bad = cgm_policy(); bad["criteria"][1]["max_value"] = 5.0
    case("D07-policy-contradictory-range", "D_invalid", "cgm", "Policy value range can never be satisfied.", cr,
         "INVALID_INPUT", "high", 0, [], ["POLICY_INVALID"], policy_obj=bad)
    bad = cgm_policy(); del bad["pathways"]
    case("D08-policy-missing-field", "D_invalid", "cgm", "Policy is missing 'pathways'.", cr, "INVALID_INPUT",
         "high", 0, [], ["POLICY_INVALID"], policy_obj=bad)
    # E. policy mismatch
    case("E01-msk-service-not-in-policy", "E_mismatch", "msk", "Requested code is not covered by the policy.",
         replace(mr, "sr-1", service_request("72148", CPT)), "POLICY_MISMATCH", "high", 100, [],
         ["SERVICE_NOT_IN_POLICY"], service="72148")
    bad = cgm_policy(); bad["status"] = "inactive"
    case("E02-policy-inactive", "E_mismatch", "cgm", "Policy is inactive.", cr, "POLICY_MISMATCH", "high", 100, [],
         ["POLICY_NOT_ACTIVE"], policy_obj=bad)
    case("E03-policy-not-yet-effective", "E_mismatch", "cgm", "Request predates the effective period.",
         replace(cr, "sr-1", service_request("E2103", HCPCS, date="2025-12-30")), "POLICY_MISMATCH", "high", 27,
         [], ["DATE_AFTER_REQUEST", "POLICY_NOT_EFFECTIVE"])
    case("E04-policy-expired", "E_mismatch", "cgm", "Request is after the effective period.",
         replace(cr, "sr-1", service_request("E2103", HCPCS, date="2027-01-02")), "POLICY_MISMATCH", "high", 60,
         ["recent-hba1c"], ["EVIDENCE_OUTSIDE_WINDOW", "POLICY_NOT_EFFECTIVE"])
    bad = cgm_policy(); bad["status"] = "retired"
    case("E05-policy-retired", "E_mismatch", "cgm", "Policy is retired.", cr, "POLICY_MISMATCH", "high", 100, [],
         ["POLICY_NOT_ACTIVE"], policy_obj=bad)
    # F. robustness
    case("F01-cgm-irrelevant-extras", "F_robustness", "cgm", "Unrelated resources must not change the outcome.",
         with_(cr, condition("I10", "cond-htn"), document("Routine visit note.", "doc-routine")), "READY", "low", 100)
    case("F02-msk-unattributed-document", "F_robustness", "msk",
         "Legacy documents without a subject are accepted with a warning.",
         replace(mr, "doc-pt", document("Physical therapy completed for six weeks with NSAID trial. Catching.",
                                        "doc-pt", subject=None)),
         "READY", "low", 100, [], ["UNATTRIBUTED_EVIDENCE"])


# --------------------------------------------------------------------------- output
def dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render() -> dict[str, str]:
    CASES.clear()
    build_cases()
    files: dict[str, str] = {
        "policies/msk_knee_mri.json": dumps(msk_policy()),
        "policies/diabetes_cgm.json": dumps(cgm_policy()),
    }
    manifest_cases = []
    for c in CASES:
        bundle_path = f"bundles/{c['id']}.json"
        files[bundle_path] = dumps(c["bundle_data"])
        policy_path = f"policies/{c['policy']}.json"
        if c["policy_override"] is not None:
            policy_path = f"policies/{c['id']}.policy.json"
            files[policy_path] = dumps(c["policy_override"])
        manifest_cases.append({
            "id": c["id"], "category": c["category"], "workflow": c["workflow"],
            "description": c["description"], "policy": policy_path, "bundle": bundle_path,
            "service_code": c["service_code"], "expected": c["expected"],
        })
    files["manifest.json"] = dumps({
        "benchmark": "PriorPacket synthetic benchmark",
        "version": "1.0.0",
        "synthetic": True,
        "note": "All patients, resources, and policies are synthetic. Not clinical or payer guidance.",
        "cases": manifest_cases,
    })
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if committed files differ")
    args = parser.parse_args()
    files = render()
    if args.check:
        stale = [p for p, text in files.items() if not (OUT / p).exists() or (OUT / p).read_text() != text]
        extra = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*.json")} - set(files) - {"reference_metrics.json"}
        if stale or extra:
            print("benchmark files out of date:", sorted(stale), sorted(extra))
            return 1
        print(f"benchmark up to date ({len(CASES)} cases)")
        return 0
    for rel, text in files.items():
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(files)} files ({len(CASES)} cases) to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
