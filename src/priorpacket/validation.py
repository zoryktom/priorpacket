from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .engine import analyze_request
from .policy import load_bundle, load_policy


@dataclass(frozen=True)
class ValidationCaseResult:
    case_id: str
    passed: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "notes": list(self.notes),
        }


def run_validation_suite(manifest_path: str | Path, out_dir: str | Path) -> dict[str, Path]:
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    root = manifest_file.parent.parent.parent
    results: list[ValidationCaseResult] = []
    for case in manifest["cases"]:
        policy = load_policy(root / case["policy"])
        bundle = load_bundle(root / case["bundle"])
        result = analyze_request(
            policy=policy,
            bundle=bundle,
            service_code=case["service_code"],
            request_id=case["id"],
        )
        results.append(_evaluate_case(case, result.to_dict()))

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "validation_report.json"
    md_path = target / "validation_report.md"
    payload = {
        "suite": manifest.get("suite", "PriorPacket validation suite"),
        "passed": all(result.passed for result in results),
        "total_cases": len(results),
        "passed_cases": sum(1 for result in results if result.passed),
        "metrics": _metrics(results),
        "results": [result.to_dict() for result in results],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def _evaluate_case(case: dict[str, Any], actual: dict[str, Any]) -> ValidationCaseResult:
    expected = case["expected"]
    notes: list[str] = []
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            notes.append(f"{key}: expected {expected_value!r}, got {actual_value!r}")
    expected_missing = tuple(case.get("expected_missing_criteria", []))
    actual_missing = tuple(actual.get("best_pathway", {}).get("missing_criteria", []))
    if expected_missing and actual_missing != expected_missing:
        notes.append(f"missing_criteria: expected {expected_missing!r}, got {actual_missing!r}")
    expected_warnings = tuple(case.get("expected_warnings", []))
    actual_warnings = tuple(actual.get("warnings", []))
    if expected_warnings and actual_warnings != expected_warnings:
        notes.append(f"warnings: expected {expected_warnings!r}, got {actual_warnings!r}")
    return ValidationCaseResult(
        case_id=case["id"],
        passed=not notes,
        expected=expected,
        actual={
            "status": actual.get("status"),
            "risk_band": actual.get("risk_band"),
            "score_percent": actual.get("score_percent"),
            "missing_criteria": actual_missing,
            "warnings": actual_warnings,
        },
        notes=tuple(notes),
    )


def _render_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        f"# {payload['suite']}",
        "",
        f"- Passed: {payload['passed']}",
        f"- Cases: {payload['passed_cases']}/{payload['total_cases']}",
        f"- Status accuracy: {metrics['status_accuracy']:.3f}",
        f"- Risk accuracy: {metrics['risk_accuracy']:.3f}",
        f"- Score exact-match rate: {metrics['score_exact_match_rate']:.3f}",
        f"- Missing-criteria exact-match rate: {metrics['missing_criteria_exact_match_rate']:.3f}",
        "",
        "| Case | Passed | Status | Risk | Score | Notes |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for result in payload["results"]:
        actual = result["actual"]
        notes = "; ".join(result["notes"]) or "None"
        lines.append(
            f"| {result['case_id']} | {result['passed']} | {actual['status']} | "
            f"{actual['risk_band']} | {actual['score_percent']}% | {notes} |"
        )
    lines.append("")
    lines.extend(["## Status Confusion Matrix", ""])
    statuses = metrics["status_labels"]
    lines.append("| Expected \\ Actual | " + " | ".join(statuses) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in statuses) + " |")
    for expected in statuses:
        row = metrics["status_confusion_matrix"].get(expected, {})
        counts = [str(row.get(actual, 0)) for actual in statuses]
        lines.append("| " + expected + " | " + " | ".join(counts) + " |")
    lines.append("")
    return "\n".join(lines)


def _metrics(results: list[ValidationCaseResult]) -> dict[str, Any]:
    total = len(results) or 1
    status_matches = 0
    risk_matches = 0
    score_matches = 0
    missing_matches = 0
    labels: set[str] = set()
    matrix: dict[str, dict[str, int]] = {}

    for result in results:
        expected_status = str(result.expected.get("status"))
        actual_status = str(result.actual.get("status"))
        expected_risk = str(result.expected.get("risk_band"))
        actual_risk = str(result.actual.get("risk_band"))
        expected_score = result.expected.get("score_percent")
        actual_score = result.actual.get("score_percent")

        labels.update([expected_status, actual_status])
        matrix.setdefault(expected_status, {})
        matrix[expected_status][actual_status] = matrix[expected_status].get(actual_status, 0) + 1

        if expected_status == actual_status:
            status_matches += 1
        if expected_risk == actual_risk:
            risk_matches += 1
        if expected_score == actual_score:
            score_matches += 1
        if not any(note.startswith("missing_criteria:") for note in result.notes):
            missing_matches += 1

    sorted_labels = sorted(labels)
    return {
        "status_accuracy": status_matches / total,
        "risk_accuracy": risk_matches / total,
        "score_exact_match_rate": score_matches / total,
        "missing_criteria_exact_match_rate": missing_matches / total,
        "status_labels": sorted_labels,
        "status_confusion_matrix": {
            expected: {actual: matrix.get(expected, {}).get(actual, 0) for actual in sorted_labels}
            for expected in sorted_labels
        },
    }
