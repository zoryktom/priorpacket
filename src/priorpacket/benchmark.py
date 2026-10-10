"""Synthetic benchmark runner, metrics, and reproducible report writer.

Metric definitions live in docs/metrics.md. Every ratio carries its numerator and
denominator, and undefined ratios are reported as ``null`` rather than silently as 0 or 1.
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import __version__
from .context import resource_key
from .engine import analyze_request
from .models import OUTCOMES, AnalysisResult

BENCHMARK_SCHEMA = "priorpacket.benchmark.v1"
DEFAULT_MANIFEST = "benchmark/v1/manifest.json"
REFERENCE_METRICS = "benchmark/v1/reference_metrics.json"


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ratio(numerator: int | float, denominator: int | float, digits: int = 4) -> dict[str, Any]:
    value = None if denominator == 0 else round(numerator / denominator, digits)
    return {"value": value, "numerator": numerator, "denominator": denominator}


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["_root"] = str(manifest_path.resolve().parent)
    return manifest


def _read_json(root: str, relative: str) -> Any:
    return json.loads((Path(root) / relative).read_text(encoding="utf-8"))


def evaluate(policy: Any, bundle: Any, service_code: str, request_id: str) -> AnalysisResult:
    return analyze_request(policy=policy, bundle=bundle, service_code=service_code, request_id=request_id)


def traceability(result: AnalysisResult, bundle: Any) -> tuple[int, int]:
    """Return (traceable, total) over criteria reported as met.

    A met criterion is traceable when it cites at least one resource and every cited
    resource exists in the submitted bundle.
    """
    present: set[str] = set()
    if isinstance(bundle, dict) and isinstance(bundle.get("entry"), list):
        for entry in bundle["entry"]:
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if isinstance(resource, dict) and isinstance(resource.get("resourceType"), str):
                present.add(resource_key(resource))
    total = traceable = 0
    for criterion in result.criteria:
        if criterion.status != "met":
            continue
        total += 1
        refs = [hit.source_reference or f"{hit.resource_type}/{hit.resource_id}" for hit in criterion.evidence]
        if refs and all(ref in present for ref in refs):
            traceable += 1
    return traceable, total


def run_case(case: dict[str, Any], root: str) -> dict[str, Any]:
    expected = case["expected"]
    policy = _read_json(root, case["policy"])
    bundle = _read_json(root, case["bundle"])
    result = evaluate(policy, bundle, str(case["service_code"]), request_id=case["id"])
    actual_missing = sorted(result.best_pathway.missing_criteria)
    actual = {
        "outcome": result.outcome,
        "risk_band": result.risk_band,
        "score_percent": result.score_percent,
        "missing_criteria": actual_missing,
        "issue_codes": list(result.issue_codes),
    }
    expected_score = expected.get("score_percent")
    checks = {
        "outcome": actual["outcome"] == expected["outcome"],
        "risk_band": actual["risk_band"] == expected["risk_band"],
        "score": expected_score is None or actual["score_percent"] == expected_score,
        "missing_criteria": actual_missing == sorted(expected.get("missing_criteria", [])),
        "issue_codes": actual["issue_codes"] == sorted(expected.get("issue_codes", [])),
    }
    traceable, met_total = traceability(result, bundle)
    return {
        "id": case["id"],
        "category": case.get("category", "uncategorized"),
        "workflow": case.get("workflow", "unknown"),
        "policy": Path(case["policy"]).name,
        "description": case.get("description", ""),
        "expected": expected,
        "actual": actual,
        "checks": checks,
        "passed": all(checks.values()),
        "traceable_met_criteria": traceable,
        "met_criteria": met_total,
    }


def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    p, r = precision["value"], recall["value"]
    f1 = None if p is None or r is None or (p + r) == 0 else round(2 * p * r / (p + r), 4)
    return {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}


def compute_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    labels = list(OUTCOMES)
    matrix = {e: {a: 0 for a in labels} for e in labels}
    for item in results:
        matrix[item["expected"]["outcome"]][item["actual"]["outcome"]] += 1

    per_class = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[e][label] for e in labels if e != label)
        fn = sum(matrix[label][a] for a in labels if a != label)
        per_class[label] = _prf(tp, fp, fn)
    defined = [v["f1"] for v in per_class.values() if v["f1"] is not None]
    macro_f1 = round(sum(defined) / len(defined), 4) if defined else None

    expected_ready = [r for r in results if r["expected"]["outcome"] == "READY"]
    expected_not_ready = [r for r in results if r["expected"]["outcome"] != "READY"]
    false_ready = [r for r in expected_not_ready if r["actual"]["outcome"] == "READY"]
    false_blocked = [r for r in expected_ready if r["actual"]["outcome"] != "READY"]

    tp = fp = fn = exact = 0
    for item in results:
        exp = set(item["expected"].get("missing_criteria", []))
        act = set(item["actual"]["missing_criteria"])
        tp += len(exp & act)
        fp += len(act - exp)
        fn += len(exp - act)
        exact += exp == act

    scored = [r for r in results if r["expected"].get("score_percent") is not None]
    score_errors = [abs(r["actual"]["score_percent"] - r["expected"]["score_percent"]) for r in scored]

    traceable = sum(r["traceable_met_criteria"] for r in results)
    met = sum(r["met_criteria"] for r in results)

    def rate(expected_label: str) -> dict[str, Any]:
        rows = [r for r in results if r["expected"]["outcome"] == expected_label]
        return ratio(sum(r["actual"]["outcome"] == expected_label for r in rows), len(rows))

    def breakdown(key: str) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in results:
            groups[item[key]].append(item)
        return {
            name: {
                "cases": len(rows),
                "outcome_accuracy": ratio(sum(r["checks"]["outcome"] for r in rows), len(rows)),
                "cases_passed": ratio(sum(r["passed"] for r in rows), len(rows)),
            }
            for name, rows in sorted(groups.items())
        }

    return {
        "total_cases": total,
        "cases_passed": ratio(sum(r["passed"] for r in results), total),
        "outcome_accuracy": ratio(sum(r["checks"]["outcome"] for r in results), total),
        "risk_band_accuracy": ratio(sum(r["checks"]["risk_band"] for r in results), total),
        "issue_code_exact_match": ratio(sum(r["checks"]["issue_codes"] for r in results), total),
        "per_class": per_class,
        "macro_f1_defined_classes": macro_f1,
        "confusion_matrix": {"labels": labels, "rows_expected_cols_actual": matrix},
        "false_ready": ratio(len(false_ready), len(expected_not_ready)),
        "false_blocked": ratio(len(false_blocked), len(expected_ready)),
        "missing_criteria": {
            **_prf(tp, fp, fn),
            "exact_match": ratio(exact, total),
        },
        "score_mean_absolute_error": {
            "value": round(sum(score_errors) / len(score_errors), 4) if score_errors else None,
            "cases_scored": len(score_errors),
        },
        "evidence_traceability": ratio(traceable, met),
        "invalid_input_detection": rate("INVALID_INPUT"),
        "policy_mismatch_detection": rate("POLICY_MISMATCH"),
        "by_category": breakdown("category"),
        "by_workflow": breakdown("workflow"),
        "by_policy": breakdown("policy"),
    }


def run_benchmark(manifest_path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    results = [run_case(case, manifest["_root"]) for case in manifest["cases"]]
    return {
        "schema": BENCHMARK_SCHEMA,
        "benchmark": manifest.get("benchmark"),
        "benchmark_version": manifest.get("version"),
        "engine_version": __version__,
        "synthetic": True,
        "metrics": compute_metrics(results),
        "cases": results,
    }


def deterministic_digest(report: dict[str, Any]) -> str:
    """Digest of every deterministic field; excludes environment and runtime information."""
    return sha256_text(canonical_json(report))


def environment_info() -> dict[str, str]:
    return {
        "priorpacket": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }


def _markdown(report: dict[str, Any], digest: str) -> str:
    m = report["metrics"]

    def pct(item: dict[str, Any]) -> str:
        value = item["value"]
        shown = "n/a (undefined)" if value is None else f"{value:.4f}"
        return f"{shown} ({item['numerator']}/{item['denominator']})"

    lines = [
        f"# PriorPacket benchmark report ({report['benchmark_version']})",
        "",
        "All data is synthetic. Results describe agreement with author-defined expected outcomes on "
        "this benchmark only; they are not clinical, payer, or real-world performance estimates.",
        "",
        f"- Engine version: {report['engine_version']}",
        f"- Cases: {m['total_cases']}",
        f"- Deterministic result digest (SHA-256): `{digest}`",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Cases fully matching expectations | {pct(m['cases_passed'])} |",
        f"| Outcome accuracy | {pct(m['outcome_accuracy'])} |",
        f"| Risk-band accuracy | {pct(m['risk_band_accuracy'])} |",
        f"| Issue-code exact match | {pct(m['issue_code_exact_match'])} |",
        f"| False READY rate (of expected non-READY) | {pct(m['false_ready'])} |",
        f"| False blocked rate (of expected READY) | {pct(m['false_blocked'])} |",
        f"| Missing-criterion precision | {pct(m['missing_criteria']['precision'])} |",
        f"| Missing-criterion recall | {pct(m['missing_criteria']['recall'])} |",
        f"| Missing-criteria exact match | {pct(m['missing_criteria']['exact_match'])} |",
        f"| Evidence traceability | {pct(m['evidence_traceability'])} |",
        f"| Invalid-input detection | {pct(m['invalid_input_detection'])} |",
        f"| Policy-mismatch detection | {pct(m['policy_mismatch_detection'])} |",
        f"| Score MAE (percentage points) | {m['score_mean_absolute_error']['value']} "
        f"over {m['score_mean_absolute_error']['cases_scored']} scored cases |",
        f"| Macro F1 (defined classes) | {m['macro_f1_defined_classes']} |",
        "",
        "## Per-class precision / recall / F1",
        "",
        "| Outcome | Precision | Recall | F1 | Support |",
        "|---|---|---|---|---|",
    ]
    for label, stats in m["per_class"].items():
        lines.append(
            f"| {label} | {pct(stats['precision'])} | {pct(stats['recall'])} | "
            f"{'n/a' if stats['f1'] is None else stats['f1']} | {stats['support']} |"
        )
    labels = m["confusion_matrix"]["labels"]
    lines += ["", "## Confusion matrix (rows expected, columns actual)", "",
              "| expected \\ actual | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for expected in labels:
        row = m["confusion_matrix"]["rows_expected_cols_actual"][expected]
        lines.append(f"| {expected} | " + " | ".join(str(row[a]) for a in labels) + " |")
    for title, key in (("Category", "by_category"), ("Workflow", "by_workflow"), ("Policy", "by_policy")):
        lines += ["", f"## By {title.lower()}", "", f"| {title} | Cases | Outcome accuracy | Cases fully matching |",
                  "|---|---|---|---|"]
        for name, stats in m[key].items():
            lines.append(f"| {name} | {stats['cases']} | {pct(stats['outcome_accuracy'])} | {pct(stats['cases_passed'])} |")
    failures = [c for c in report["cases"] if not c["passed"]]
    lines += ["", "## Failures", ""]
    if not failures:
        lines.append("None.")
    for case in failures:
        failed = ", ".join(name for name, ok in case["checks"].items() if not ok)
        lines.append(f"- **{case['id']}** — mismatched: {failed}; expected {case['expected']}, actual {case['actual']}")
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    digest = deterministic_digest(report)
    paths: dict[str, Path] = {}

    paths["json"] = out / "benchmark_results.json"
    paths["json"].write_text(canonical_json({**report, "result_digest_sha256": digest}), encoding="utf-8")

    paths["csv"] = out / "benchmark_cases.csv"
    with paths["csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "category", "workflow", "policy", "expected_outcome", "actual_outcome", "passed",
                         "expected_risk", "actual_risk", "expected_score", "actual_score",
                         "expected_missing", "actual_missing", "expected_issues", "actual_issues"])
        for case in report["cases"]:
            e, a = case["expected"], case["actual"]
            writer.writerow([
                case["id"], case["category"], case["workflow"], case["policy"], e["outcome"], a["outcome"],
                case["passed"], e["risk_band"], a["risk_band"], e.get("score_percent"), a["score_percent"],
                ";".join(e.get("missing_criteria", [])), ";".join(a["missing_criteria"]),
                ";".join(e.get("issue_codes", [])), ";".join(a["issue_codes"]),
            ])

    paths["confusion_matrix"] = out / "confusion_matrix.csv"
    matrix = report["metrics"]["confusion_matrix"]
    with paths["confusion_matrix"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["expected\\actual", *matrix["labels"]])
        for label in matrix["labels"]:
            writer.writerow([label, *(matrix["rows_expected_cols_actual"][label][a] for a in matrix["labels"])])

    paths["markdown"] = out / "benchmark_report.md"
    paths["markdown"].write_text(_markdown(report, digest), encoding="utf-8")

    paths["environment"] = out / "environment.json"
    paths["environment"].write_text(canonical_json(environment_info()), encoding="utf-8")

    paths["checksums"] = out / "SHA256SUMS"
    paths["checksums"].write_text(
        "".join(f"{sha256_file(p)}  {p.name}\n" for key, p in sorted(paths.items()) if key != "checksums"),
        encoding="utf-8",
    )
    return paths


def reference_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": BENCHMARK_SCHEMA,
        "benchmark_version": report["benchmark_version"],
        "engine_version": report["engine_version"],
        "result_digest_sha256": deterministic_digest(report),
        "metrics": report["metrics"],
    }


def reproduce(
    manifest_path: str | Path = DEFAULT_MANIFEST,
    reference_path: str | Path = REFERENCE_METRICS,
    out_dir: str | Path | None = None,
) -> tuple[bool, list[str]]:
    """Re-run the benchmark and compare to the committed reference. Returns (ok, differences)."""
    report = run_benchmark(manifest_path)
    if out_dir is not None:
        write_reports(report, out_dir)
    reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    current = reference_summary(report)
    differences: list[str] = []
    for key in ("benchmark_version", "result_digest_sha256", "metrics"):
        if current[key] != reference.get(key):
            differences.append(f"{key} differs from {reference_path}")
    return not differences, differences
