from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .engine import analyze_request
from .models import AnalysisResult
from .policy import load_bundle, load_policy


def analyze_bundle_file(
    *,
    policy: dict[str, Any],
    bundle_path: str | Path,
    service_code: str,
) -> AnalysisResult:
    path = Path(bundle_path)
    bundle = load_bundle(path)
    return analyze_request(
        policy=policy,
        bundle=bundle,
        service_code=service_code,
        request_id=path.stem,
    )


def write_batch_report(
    *,
    policy_path: str | Path,
    bundles_dir: str | Path,
    service_code: str,
    out_dir: str | Path,
    pattern: str = "*.json",
) -> dict[str, Path]:
    policy = load_policy(policy_path)
    source_dir = Path(bundles_dir)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    results: list[AnalysisResult] = []
    for bundle_path in sorted(source_dir.glob(pattern)):
        results.append(
            analyze_bundle_file(
                policy=policy,
                bundle_path=bundle_path,
                service_code=service_code,
            )
        )

    json_path = target / "batch_results.json"
    csv_path = target / "evidence_gap_report.csv"
    summary_path = target / "batch_summary.md"

    json_path.write_text(
        json.dumps([result.to_dict() for result in results], indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(csv_path, results)
    summary_path.write_text(_render_summary(results), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "summary": summary_path}


def _write_csv(path: Path, results: list[AnalysisResult]) -> None:
    fields = [
        "request_id",
        "patient_id",
        "service_code",
        "status",
        "risk_band",
        "score_percent",
        "best_pathway",
        "missing_criteria",
        "missing_actions",
        "warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "request_id": result.request_id,
                    "patient_id": result.patient.patient_id,
                    "service_code": result.service_code,
                    "status": result.status,
                    "risk_band": result.risk_band,
                    "score_percent": result.score_percent,
                    "best_pathway": result.best_pathway.label,
                    "missing_criteria": "|".join(result.best_pathway.missing_criteria),
                    "missing_actions": "|".join(result.missing_actions),
                    "warnings": "|".join(result.warnings),
                }
            )


def _render_summary(results: list[AnalysisResult]) -> str:
    total = len(results)
    ready = sum(1 for result in results if result.status == "ready_for_review")
    needs = sum(1 for result in results if result.status == "needs_evidence")
    not_ready = sum(1 for result in results if result.status == "not_ready")
    mismatch = sum(1 for result in results if result.status == "policy_mismatch")
    lines = [
        "# PriorPacket Batch Summary",
        "",
        f"- Total packets: {total}",
        f"- Ready for review: {ready}",
        f"- Needs evidence: {needs}",
        f"- Not ready: {not_ready}",
        f"- Policy mismatch: {mismatch}",
        "",
        "| Request | Status | Risk | Score | Missing actions |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for result in results:
        actions = "; ".join(result.missing_actions) or "None"
        lines.append(
            f"| {result.request_id} | {result.status} | {result.risk_band} | "
            f"{result.score_percent}% | {actions} |"
        )
    lines.append("")
    return "\n".join(lines)
