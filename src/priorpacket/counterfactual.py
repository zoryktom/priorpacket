"""Counterfactual and metamorphic checks.

Each check starts from a benchmark case that is expected to be READY, applies exactly one
controlled change, and states the outcome that change must produce. Invariance checks
(reordering, irrelevant evidence, repeated runs) must leave the result unchanged.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from .benchmark import canonical_json, evaluate, load_manifest, ratio

Scenario = tuple[Any, Any, str]  # bundle, policy, service_code
Perturbation = Callable[[Any, Any, str], Scenario]

OTHER_SUBJECT = {"reference": "Patient/other-999"}


def _resources(bundle: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(e["resource"] for e in bundle["entry"] if e["resource"].get("id") == rid)


def _remove(rid: str) -> Perturbation:
    def apply(bundle: Any, policy: Any, code: str) -> Scenario:
        b = copy.deepcopy(bundle)
        b["entry"] = [e for e in b["entry"] if e["resource"].get("id") != rid]
        return b, policy, code

    return apply


def _edit(rid: str, change: Callable[[dict[str, Any]], None]) -> Perturbation:
    def apply(bundle: Any, policy: Any, code: str) -> Scenario:
        b = copy.deepcopy(bundle)
        change(_resources(b, rid))
        return b, policy, code

    return apply


def _add(*resources: dict[str, Any]) -> Perturbation:
    def apply(bundle: Any, policy: Any, code: str) -> Scenario:
        b = copy.deepcopy(bundle)
        b["entry"].extend({"resource": copy.deepcopy(r)} for r in resources)
        return b, policy, code

    return apply


def _policy(change: Callable[[dict[str, Any]], None]) -> Perturbation:
    def apply(bundle: Any, policy: Any, code: str) -> Scenario:
        p = copy.deepcopy(policy)
        change(p)
        return bundle, p, code

    return apply


def _reverse(bundle: Any, policy: Any, code: str) -> Scenario:
    b = copy.deepcopy(bundle)
    b["entry"].reverse()
    return b, policy, code


def _identity(bundle: Any, policy: Any, code: str) -> Scenario:
    return copy.deepcopy(bundle), copy.deepcopy(policy), code


def _other_code(bundle: Any, policy: Any, code: str) -> Scenario:
    return bundle, policy, "99999"


def _set(path: tuple[str, ...], value: Any) -> Callable[[dict[str, Any]], None]:
    def change(resource: dict[str, Any]) -> None:
        node = resource
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return change


def _delete(key: str) -> Callable[[dict[str, Any]], None]:
    return lambda resource: resource.pop(key)


IRRELEVANT = {"resourceType": "Condition", "id": "cf-irrelevant", "subject": {"reference": "Patient/synthetic-001"},
              "recordedDate": "2026-08-02", "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm",
                                                                    "code": "I10"}]}}

# (name, perturbation, expected outcome, invariance kind)
# kind "outcome": outcome must equal expected. "identical": whole result must equal baseline.
CGM_CHECKS: list[tuple[str, Perturbation, str, str]] = [
    ("remove_hba1c", _remove("obs-a1c"), "INCOMPLETE", "outcome"),
    ("remove_insulin", _remove("med-insulin"), "INCOMPLETE", "outcome"),
    ("remove_diagnosis", _remove("cond-t2dm"), "INCOMPLETE", "outcome"),
    ("change_service_code", _other_code, "POLICY_MISMATCH", "outcome"),
    ("hba1c_below_threshold", _edit("obs-a1c", _set(("valueQuantity", "value"), 6.9)), "INCOMPLETE", "outcome"),
    ("hba1c_at_threshold", _edit("obs-a1c", _set(("valueQuantity", "value"), 7.0)), "READY", "outcome"),
    ("hba1c_wrong_unit", _edit("obs-a1c", _set(("valueQuantity", "unit"), "mg/dL")), "NEEDS_REVIEW", "outcome"),
    ("hba1c_unit_removed", _edit("obs-a1c", lambda r: r["valueQuantity"].pop("unit")), "NEEDS_REVIEW", "outcome"),
    ("hba1c_beyond_window", _edit("obs-a1c", _set(("effectiveDateTime",), "2026-06-13")), "INCOMPLETE", "outcome"),
    ("hba1c_at_window_edge", _edit("obs-a1c", _set(("effectiveDateTime",), "2026-06-14")), "READY", "outcome"),
    ("hba1c_date_removed", _edit("obs-a1c", _delete("effectiveDateTime")), "NEEDS_REVIEW", "outcome"),
    ("hba1c_code_system_changed", _edit("obs-a1c", lambda r: r["code"]["coding"][0].update(system="http://example.org/x")),
     "NEEDS_REVIEW", "outcome"),
    ("hba1c_wrong_patient", _edit("obs-a1c", _set(("subject",), OTHER_SUBJECT)), "NEEDS_REVIEW", "outcome"),
    ("hba1c_entered_in_error", _edit("obs-a1c", _set(("status",), "entered-in-error")), "INCOMPLETE", "outcome"),
    ("add_conflicting_hba1c", None, "NEEDS_REVIEW", "outcome"),
    ("policy_inactive", _policy(lambda p: p.update(status="inactive")), "POLICY_MISMATCH", "outcome"),
    ("policy_unsupported_schema", _policy(lambda p: p.update(schema_version=2)), "INVALID_INPUT", "outcome"),
    ("policy_unknown_field", _policy(lambda p: p["criteria"][0].update(surprise=True)), "INVALID_INPUT", "outcome"),
    ("policy_version_bump", _policy(lambda p: p.update(policy_version="1.0.1")), "READY", "outcome"),
    ("add_irrelevant_evidence", _add(IRRELEVANT), "READY", "outcome"),
    ("add_identical_duplicate", None, "READY", "outcome"),
    ("add_unresolved_reference", _add({"resourceType": "DiagnosticReport", "id": "cf-dr", "status": "final",
                                       "subject": {"reference": "Patient/synthetic-001"},
                                       "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
                                       "result": [{"reference": "Observation/absent"}]}), "NEEDS_REVIEW", "outcome"),
    ("reorder_entries", _reverse, "READY", "identical"),
    ("repeat_run", _identity, "READY", "identical"),
]

MSK_CHECKS: list[tuple[str, Perturbation, str, str]] = [
    ("remove_xray", _remove("proc-xray"), "INCOMPLETE", "outcome"),
    ("remove_prior_treatment", _remove("doc-pt"), "INCOMPLETE", "outcome"),
    ("remove_diagnosis", _remove("cond-knee"), "INCOMPLETE", "outcome"),
    ("xray_beyond_window", _edit("proc-xray", _set(("performedDateTime",), "2026-06-13")), "INCOMPLETE", "outcome"),
    ("xray_at_window_edge", _edit("proc-xray", _set(("performedDateTime",), "2026-06-14")), "READY", "outcome"),
    ("xray_wrong_patient", _edit("proc-xray", _set(("subject",), OTHER_SUBJECT)), "NEEDS_REVIEW", "outcome"),
    ("change_service_code", _other_code, "POLICY_MISMATCH", "outcome"),
    ("contradictory_treatment_note", _add({"resourceType": "DocumentReference", "id": "cf-refused", "status": "current",
                                           "date": "2026-09-02", "subject": {"reference": "Patient/synthetic-001"},
                                           "type": {"coding": [{"system": "http://loinc.org", "code": "11506-3"}]},
                                           "description": "Patient refused physical therapy."}),
     "NEEDS_REVIEW", "outcome"),
    ("add_irrelevant_evidence", _add(IRRELEVANT), "READY", "outcome"),
    ("reorder_entries", _reverse, "READY", "identical"),
    ("repeat_run", _identity, "READY", "identical"),
]


def _special(name: str, bundle: dict[str, Any]) -> Perturbation:
    if name == "add_conflicting_hba1c":
        base = copy.deepcopy(_resources(bundle, "obs-a1c"))
        base.update(id="cf-a1c-low", effectiveDateTime="2026-08-25")
        base["valueQuantity"] = {"value": 6.5, "unit": "%"}
        return _add(base)
    if name == "add_identical_duplicate":
        return _add(copy.deepcopy(_resources(bundle, "cond-t2dm")))
    raise KeyError(name)


def run_counterfactuals(manifest_path: str | Path = "benchmark/v1/manifest.json") -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    cases = {c["id"]: c for c in manifest["cases"]}
    parents = [("A03-cgm-ready", CGM_CHECKS), ("A01-msk-ready-standard", MSK_CHECKS)]
    records: list[dict[str, Any]] = []
    for parent_id, checks in parents:
        parent = cases[parent_id]
        root = Path(manifest["_root"])
        policy = json.loads((root / parent["policy"]).read_text(encoding="utf-8"))
        bundle = json.loads((root / parent["bundle"]).read_text(encoding="utf-8"))
        code = str(parent["service_code"])
        baseline = evaluate(policy, bundle, code, "cf-baseline")
        baseline_dict = baseline.to_dict()
        for name, perturbation, expected, kind in checks:
            perturbation = perturbation or _special(name, bundle)
            new_bundle, new_policy, new_code = perturbation(bundle, policy, code)
            result = evaluate(new_policy, new_bundle, new_code, "cf-baseline")
            if kind == "identical":
                held = result.to_dict() == baseline_dict
            else:
                held = result.outcome == expected
            records.append({
                "parent_id": parent_id,
                "perturbation": name,
                "kind": kind,
                "baseline_outcome": baseline.outcome,
                "expected_outcome": expected,
                "actual_outcome": result.outcome,
                "invariant_held": held,
                "issue_codes": list(result.issue_codes),
            })
    return {
        "schema": "priorpacket.counterfactual.v1",
        "checks": len(records),
        "held": sum(r["invariant_held"] for r in records),
        "invariant_hold_rate": ratio(sum(r["invariant_held"] for r in records), len(records)),
        "records": records,
    }


def write_counterfactual_report(report: dict[str, Any], out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "counterfactual_results.json"
    path.write_text(canonical_json(report), encoding="utf-8")
    return path
