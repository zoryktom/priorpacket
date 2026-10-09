from __future__ import annotations

from typing import Any
from uuid import uuid4

from priorpacket.evidence import EvidenceMapper
from priorpacket.fhir import resource_date, resources_by_type, summarize_patient
from priorpacket.models import AnalysisResult, CriterionResult, PathwayResult


def analyze_request(
    *,
    policy: dict[str, Any],
    bundle: dict[str, Any],
    service_code: str,
    request_id: str | None = None,
) -> AnalysisResult:
    service_request_date = _service_request_date(bundle, service_code)
    mapper = EvidenceMapper(bundle, service_request_date=service_request_date)
    criteria = tuple(mapper.evaluate(criterion) for criterion in policy["criteria"])
    best_pathway = _best_pathway(policy, criteria)
    max_score = best_pathway.max_score
    score = best_pathway.score
    warnings = _warnings(policy, service_code)
    risk_band = _risk_band(best_pathway)
    status = _status(best_pathway)
    missing_actions = tuple(
        result.missing_action
        for result in criteria
        if result.criterion_id in best_pathway.missing_criteria and result.missing_action
    )
    if warnings:
        status = "policy_mismatch"
        risk_band = "high"
        missing_actions = (
            f"Select a policy pack that explicitly includes service code {service_code}.",
            *missing_actions,
        )

    service = policy.get("service", {})
    return AnalysisResult(
        request_id=request_id or f"pp-{uuid4().hex[:10]}",
        policy_id=policy["policy_id"],
        payer=policy["payer"],
        service_code=service_code,
        service_name=service.get("name", "Requested service"),
        patient=summarize_patient(bundle),
        status=status,
        risk_band=risk_band,
        score=score,
        max_score=max_score,
        best_pathway=best_pathway,
        criteria=criteria,
        missing_actions=missing_actions,
        warnings=warnings,
    )


def _service_request_date(bundle: dict[str, Any], service_code: str) -> str | None:
    for service_request in resources_by_type(bundle, "ServiceRequest"):
        codes = service_request.get("code", {}).get("coding", [])
        if any(str(coding.get("code")) == str(service_code) for coding in codes):
            return resource_date(service_request)
    return None


def _best_pathway(
    policy: dict[str, Any],
    criteria: tuple[CriterionResult, ...],
) -> PathwayResult:
    by_id = {result.criterion_id: result for result in criteria}
    pathway_results: list[PathwayResult] = []
    for pathway in policy["pathways"]:
        required = tuple(pathway.get("requires", []))
        met = tuple(
            criterion_id
            for criterion_id in required
            if by_id[criterion_id].status == "met"
        )
        missing = tuple(
            criterion_id
            for criterion_id in required
            if by_id[criterion_id].status != "met"
        )
        max_score = sum(by_id[criterion_id].weight for criterion_id in required)
        score = sum(by_id[criterion_id].earned_weight for criterion_id in required)
        pathway_results.append(
            PathwayResult(
                pathway_id=pathway["id"],
                label=pathway.get("label", pathway["id"]),
                required_criteria=required,
                met_criteria=met,
                missing_criteria=missing,
                score=score,
                max_score=max_score,
            )
        )

    return max(
        pathway_results,
        key=lambda pathway: (pathway.completion_rate, pathway.score, -len(pathway.missing_criteria)),
    )


def _risk_band(pathway: PathwayResult) -> str:
    if not pathway.required_criteria:
        return "unknown"
    if pathway.completion_rate == 1:
        return "low"
    if pathway.completion_rate >= 0.67:
        return "moderate"
    return "high"


def _status(pathway: PathwayResult) -> str:
    if pathway.completion_rate == 1:
        return "ready_for_review"
    if pathway.completion_rate >= 0.67:
        return "needs_evidence"
    return "not_ready"


def _warnings(policy: dict[str, Any], service_code: str) -> tuple[str, ...]:
    configured_codes = {str(code) for code in policy.get("service", {}).get("codes", [])}
    if configured_codes and service_code not in configured_codes:
        return (
            f"Service code {service_code} is not listed in this policy pack.",
        )
    return tuple()
