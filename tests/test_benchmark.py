from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from priorpacket.benchmark import compute_metrics, deterministic_digest, ratio, reproduce, run_benchmark, write_reports
from priorpacket.cli import main
from priorpacket.counterfactual import run_counterfactuals
from priorpacket.engine import analyze_request
from priorpacket.evidence_graph import build_evidence_graph
from priorpacket.fhir_validation import validate_fhir_bundle
from priorpacket.policy import validate_policy
from priorpacket.render import render_html
from priorpacket.server import ROOT as SERVER_ROOT
from priorpacket.server import _benchmark_payload, _examples_payload

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmark/v1/manifest.json"


def _case(case_id: str) -> tuple[dict, dict, str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    case = next(c for c in manifest["cases"] if c["id"] == case_id)
    policy = json.loads((MANIFEST.parent / case["policy"]).read_text(encoding="utf-8"))
    bundle = json.loads((MANIFEST.parent / case["bundle"]).read_text(encoding="utf-8"))
    return policy, bundle, str(case["service_code"])


def _run(case_id: str):
    policy, bundle, code = _case(case_id)
    return analyze_request(policy=policy, bundle=bundle, service_code=code, request_id="t")


@pytest.fixture(scope="module")
def report():
    return run_benchmark(MANIFEST)


def test_benchmark_has_required_scale_and_coverage(report):
    assert report["metrics"]["total_cases"] >= 30
    assert len(report["metrics"]["by_workflow"]) >= 2
    outcomes = {c["expected"]["outcome"] for c in report["cases"]}
    assert outcomes == {"READY", "INCOMPLETE", "NEEDS_REVIEW", "INVALID_INPUT", "POLICY_MISMATCH"}


def test_benchmark_matches_expectations(report):
    failures = [c["id"] for c in report["cases"] if not c["passed"]]
    assert failures == []
    assert report["metrics"]["false_ready"]["numerator"] == 0
    assert report["metrics"]["evidence_traceability"]["value"] == 1.0


def test_benchmark_is_deterministic(report):
    assert deterministic_digest(run_benchmark(MANIFEST)) == deterministic_digest(report)


def test_reproduce_matches_committed_reference(tmp_path):
    ok, differences = reproduce(MANIFEST, ROOT / "benchmark/v1/reference_metrics.json", tmp_path)
    assert ok, differences


def test_reports_are_written_with_checksums(report, tmp_path):
    paths = write_reports(report, tmp_path)
    for key in ("json", "csv", "markdown", "confusion_matrix", "checksums", "environment"):
        assert paths[key].exists()
    assert "benchmark_results.json" in paths["checksums"].read_text(encoding="utf-8")
    assert "synthetic" in paths["markdown"].read_text(encoding="utf-8").lower()


def test_counterfactuals_all_hold():
    cf = run_counterfactuals(MANIFEST)
    broken = [r for r in cf["records"] if not r["invariant_held"]]
    assert broken == []
    assert cf["checks"] >= 30


def test_generated_benchmark_files_are_current():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_benchmark.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_metrics_report_undefined_ratios_as_none():
    rows = [
        {
            "category": "x", "workflow": "w", "policy": "p",
            "expected": {"outcome": "READY", "missing_criteria": [], "score_percent": 100},
            "actual": {"outcome": "READY", "score_percent": 100, "missing_criteria": []},
            "checks": {"outcome": True, "risk_band": True, "issue_codes": True},
            "passed": True, "traceable_met_criteria": 0, "met_criteria": 0,
        }
    ]
    metrics = compute_metrics(rows)
    assert metrics["evidence_traceability"]["value"] is None
    assert metrics["false_ready"]["value"] is None
    assert metrics["per_class"]["INVALID_INPUT"]["precision"]["value"] is None
    assert ratio(1, 0)["value"] is None


def test_false_ready_is_counted():
    row = {
        "category": "x", "workflow": "w", "policy": "p",
        "expected": {"outcome": "INCOMPLETE", "missing_criteria": ["a"], "score_percent": 50},
        "actual": {"outcome": "READY", "score_percent": 100, "missing_criteria": []},
        "checks": {"outcome": False, "risk_band": False, "issue_codes": True},
        "passed": False, "traceable_met_criteria": 1, "met_criteria": 1,
    }
    metrics = compute_metrics([row])
    assert metrics["false_ready"] == {"value": 1.0, "numerator": 1, "denominator": 1}
    assert metrics["missing_criteria"]["recall"]["value"] == 0.0


# ---- semantics -------------------------------------------------------------------------
def test_optional_criterion_does_not_block_ready():
    result = _run("A03-cgm-ready")
    optional = next(c for c in result.criteria if c.criterion_id == "diabetes-education")
    assert optional.status == "missing" and not optional.required
    assert result.outcome == "READY"


def test_missing_evidence_is_not_proof_of_absence():
    result = _run("B07-cgm-missing-hba1c")
    criterion = next(c for c in result.criteria if c.criterion_id == "recent-hba1c")
    assert "not proof" in criterion.inference
    assert criterion.to_dict()["provenance"]["absence_of_evidence"] is True


def test_threshold_and_unit_semantics():
    assert _run("A04-cgm-boundary-value").outcome == "READY"
    assert _run("B08-cgm-hba1c-below-threshold").outcome == "INCOMPLETE"
    assert _run("C01-cgm-unit-mismatch").outcome == "NEEDS_REVIEW"


def test_window_is_inclusive():
    assert _run("A05-cgm-boundary-window").outcome == "READY"
    assert _run("B09-cgm-hba1c-expired").outcome == "INCOMPLETE"


def test_conflicting_evidence_is_never_ready():
    result = _run("C03-cgm-conflicting-values")
    assert result.outcome == "NEEDS_REVIEW"
    assert "CONFLICTING_EVIDENCE" in result.issue_codes


def test_invalid_input_never_raises_and_is_not_ready():
    for case_id in ("D01-input-not-a-bundle", "D02-input-empty-bundle", "D05-policy-unknown-field"):
        result = _run(case_id)
        assert result.outcome == "INVALID_INPUT"
        assert result.risk_band == "high"
        assert result.status == "invalid_input"


def test_precedence_policy_mismatch_over_incomplete():
    policy, bundle, _ = _case("B07-cgm-missing-hba1c")
    policy["status"] = "inactive"
    result = analyze_request(policy=policy, bundle=bundle, service_code="E2103")
    assert result.outcome == "POLICY_MISMATCH"


def test_precedence_incomplete_over_needs_review():
    policy, bundle, code = _case("C03-cgm-conflicting-values")
    bundle["entry"] = [e for e in bundle["entry"] if e["resource"]["id"] != "med-insulin"]
    result = analyze_request(policy=policy, bundle=bundle, service_code=code)
    assert result.outcome == "INCOMPLETE"


def test_input_is_not_mutated():
    policy, bundle, code = _case("A03-cgm-ready")
    snapshot = copy.deepcopy((policy, bundle))
    analyze_request(policy=policy, bundle=bundle, service_code=code)
    assert (policy, bundle) == snapshot


def test_entry_order_does_not_change_result():
    policy, bundle, code = _case("A01-msk-ready-standard")
    forward = analyze_request(policy=policy, bundle=bundle, service_code=code, request_id="r").to_dict()
    bundle["entry"].reverse()
    backward = analyze_request(policy=policy, bundle=bundle, service_code=code, request_id="r").to_dict()
    assert forward == backward


def test_default_request_id_is_deterministic():
    policy, bundle, code = _case("A03-cgm-ready")
    a = analyze_request(policy=policy, bundle=bundle, service_code=code)
    b = analyze_request(policy=policy, bundle=bundle, service_code=code)
    assert a.request_id == b.request_id


def test_evidence_graph_records_provenance_and_absence():
    graph = build_evidence_graph(_run("B07-cgm-missing-hba1c"))
    assert graph["schema"] == "priorpacket.evidence_graph.v1"
    assert any(n["type"] == "evidence_absence" for n in graph["nodes"])
    rejected = build_evidence_graph(_run("B08-cgm-hba1c-below-threshold"))
    assert any(e["relationship"] == "rejected_resource" and e["properties"]["reason"] == "VALUE_OUT_OF_RANGE"
               for e in rejected["edges"])


def test_html_escapes_untrusted_text():
    policy, bundle, code = _case("A03-cgm-ready")
    policy["criteria"][0]["label"] = "<script>alert(1)</script>"
    html = render_html(analyze_request(policy=policy, bundle=bundle, service_code=code))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---- policy validation -----------------------------------------------------------------
def _policy() -> dict:
    return _case("A03-cgm-ready")[0]


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda p: p["criteria"][0].update(bogus=1), "unknown criterion field"),
        (lambda p: p["criteria"][0].update(weight=0), "positive integer"),
        (lambda p: p["criteria"][0].update(weight=True), "positive integer"),
        (lambda p: p["criteria"][1].update(operator="~"), "operator"),
        (lambda p: p["criteria"][1].pop("value"), "value: required"),
        (lambda p: p["criteria"][1].update(value=float("nan")), "finite number"),
        (lambda p: p["criteria"][1].update(max_value=1.0), "contradictory"),
        (lambda p: p["criteria"][0].update(operator=">=", value=1), "only supported on observation"),
        (lambda p: p["criteria"][1].update(prerequisite="recent-hba1c"), "own prerequisite"),
        (lambda p: p["criteria"][1].update(prerequisite="nope"), "unknown criterion id"),
        (lambda p: p["pathways"][0].update(requires=["nope"]), "unknown criterion id"),
        (lambda p: p["pathways"][0].update(requires=["diabetes-education"]), "no mandatory criterion"),
        (lambda p: p.update(schema_version=2), "not supported"),
        (lambda p: p.update(status="weird"), "status"),
        (lambda p: p.update(effective_start="2027-01-01"), "must not be after"),
        (lambda p: p["service"].update(codes=["E2103", "E2103"]), "duplicate"),
        (lambda p: p["criteria"][0].update(codes=["12345"]), "valid code format"),
        (lambda p: p["criteria"].append(dict(p["criteria"][0])), "duplicate criterion id"),
    ],
)
def test_policy_validation_rejects(mutate, fragment):
    policy = _policy()
    mutate(policy)
    errors = validate_policy(policy)
    assert any(fragment in e for e in errors), errors


def test_policy_prerequisite_cycle_detected():
    policy = _policy()
    policy["criteria"][0]["prerequisite"] = "recent-hba1c"
    policy["criteria"][1]["prerequisite"] = "diabetes-diagnosis"
    assert any("circular" in e for e in validate_policy(policy))


def test_valid_benchmark_policies_pass():
    for name in ("msk_knee_mri", "diabetes_cgm"):
        policy = json.loads((ROOT / f"benchmark/v1/policies/{name}.json").read_text(encoding="utf-8"))
        assert validate_policy(policy) == []


def test_prerequisite_downgrades_dependent_criterion():
    policy, bundle, code = _case("A03-cgm-ready")
    policy["criteria"][2]["prerequisite"] = "diabetes-education"
    result = analyze_request(policy=policy, bundle=bundle, service_code=code)
    assert result.outcome == "INCOMPLETE"
    assert "PREREQUISITE_UNMET" in result.issue_codes


# ---- FHIR validation, server, CLI ------------------------------------------------------
def test_fhir_validation_flags_reference_and_pas_problems():
    _, bundle, _ = _case("C09-cgm-unresolved-reference")
    report = validate_fhir_bundle(bundle)
    assert not report["valid"]
    assert any(f["code"] == "UNRESOLVED_REFERENCE" for f in report["findings"])
    pas = validate_fhir_bundle(_case("A03-cgm-ready")[1], expect_pas=True)
    assert any(f["code"] == "FIRST_ENTRY_NOT_CLAIM" for f in pas["findings"])
    assert report["not_checked"]


def test_server_root_points_at_repository_root():
    assert (SERVER_ROOT / "examples/cases/manifest.json").exists()
    payload = _examples_payload()
    assert len(payload["cases"]) >= 35
    assert _benchmark_payload()["available"] is True


def test_cli_benchmark_and_reproduce(tmp_path, capsys):
    main(["benchmark", "--manifest", str(MANIFEST), "--out", str(tmp_path / "b")])
    assert "Cases fully matching: 45/45" in capsys.readouterr().out
    main(["reproduce", "--manifest", str(MANIFEST), "--out", str(tmp_path / "r")])
    assert "Reproduction OK" in capsys.readouterr().out


def test_cli_reproduce_fails_on_mismatch(tmp_path):
    reference = tmp_path / "ref.json"
    reference.write_text(json.dumps({"benchmark_version": "x", "result_digest_sha256": "0", "metrics": {}}))
    with pytest.raises(SystemExit) as exc:
        main(["reproduce", "--manifest", str(MANIFEST), "--reference", str(reference), "--out", str(tmp_path)])
    assert exc.value.code == 1


def test_cli_demo(tmp_path, capsys):
    main(["demo", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert "READY" in out and "NEEDS_REVIEW" in out and "INCOMPLETE" in out
