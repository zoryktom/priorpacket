from __future__ import annotations

from dataclasses import replace
from typing import Any

from priorpacket.context import BundleContext, structural_issues
from priorpacket.evidence import EvidenceMapper
from priorpacket.fhir import resource_date_info, summarize_patient
from priorpacket.fhir.helpers import parse_day
from priorpacket.models import (
    LEGACY_STATUS,
    AnalysisResult,
    CriterionResult,
    Issue,
    PathwayResult,
    PatientSummary,
)
from priorpacket.policy import validate_policy

COMPLETION_THRESHOLD = 0.67


def analyze_request(
    *,
    policy: dict[str, Any],
    bundle: dict[str, Any],
    service_code: str,
    request_id: str | None = None,
) -> AnalysisResult:
    """Evaluate a bundle against a policy and return a deterministic, traceable result.

    Outcome precedence: INVALID_INPUT > POLICY_MISMATCH > INCOMPLETE > NEEDS_REVIEW > READY.
    Invalid input never raises; it is reported as an INVALID_INPUT result.
    """
    request_id = request_id or _request_id(policy, bundle, service_code)
    service_code = str(service_code)

    policy_errors = validate_policy(policy)
    if policy_errors:
        issues = tuple(_policy_issue(message) for message in policy_errors)
        return _invalid(policy, service_code, request_id, issues)
    bundle_issues = structural_issues(bundle)
    if bundle_issues:
        return _invalid(policy, service_code, request_id, tuple(bundle_issues))

    ctx = BundleContext(bundle)
    service_requests = ctx.by_type("ServiceRequest")
    matching = [sr for sr in service_requests if _has_code(sr, service_code)]
    service_request = matching[0] if matching else None
    patient_id = ctx.select_patient_id(service_request)
    ctx.link_indirect_evidence(patient_id)
    ctx.check_subject_references()

    date_source = service_request or (service_requests[0] if service_requests else None)
    request_date = resource_date_info(date_source) if date_source else None
    mapper = EvidenceMapper(
        bundle,
        request_date.value if request_date and request_date.status == "ok" else None,
        context=ctx,
        patient_id=patient_id,
        reference_date_status=request_date.status if request_date else "missing",
    )
    criteria = _apply_prerequisites(policy, tuple(mapper.evaluate(c) for c in policy["criteria"]))
    best = _best_pathway(policy, criteria)

    issues: list[Issue] = list(ctx.issues)
    warnings: list[str] = []
    mismatch = False
    review = False
    incomplete = False

    configured = {str(code) for code in policy["service"]["codes"]}
    if service_code not in configured:
        mismatch = True
        warnings.append(f"Service code {service_code} is not listed in this policy pack.")
        issues.append(
            Issue(
                "SERVICE_NOT_IN_POLICY",
                "error",
                f"Service code {service_code} is not covered by policy {policy['policy_id']}.",
            )
        )

    status_value = policy.get("status", "active")
    if status_value != "active":
        mismatch = True
        warnings.append(f"Policy status is '{status_value}', not 'active'.")
        issues.append(
            Issue("POLICY_NOT_ACTIVE", "error", f"Policy status is '{status_value}', not 'active'.")
        )

    if not mismatch:
        if service_request is None:
            incomplete = True
            if service_requests:
                issues.append(
                    Issue(
                        "SERVICE_CODE_MISMATCH",
                        "error",
                        f"No ServiceRequest in the packet requests service code {service_code}.",
                    )
                )
            else:
                issues.append(
                    Issue("MISSING_SERVICE_REQUEST", "error", "Packet contains no ServiceRequest.")
                )
        mismatch_issue, review_issue = _effective_window(policy, request_date)
        if mismatch_issue:
            mismatch = True
            issues.append(mismatch_issue)
        if review_issue:
            review = True
            issues.append(review_issue)

    blocking_bundle = any(
        issue.severity == "error" and issue.code in {"UNRESOLVED_REFERENCE", "DUPLICATE_ID_CONFLICT"}
        for issue in ctx.issues
    )
    if best.missing_criteria:
        incomplete = True
    if best.unresolved_criteria or blocking_bundle:
        review = True

    if mismatch:
        outcome = "POLICY_MISMATCH"
    elif incomplete:
        outcome = "INCOMPLETE"
    elif review:
        outcome = "NEEDS_REVIEW"
    else:
        outcome = "READY"

    missing_actions = _actions(criteria, best, outcome)
    if outcome == "POLICY_MISMATCH":
        missing_actions = (
            f"Select an active, in-effect policy pack that explicitly includes service code {service_code}.",
            *missing_actions,
        )
    elif service_request is None and incomplete:
        missing_actions = (f"Add a ServiceRequest for service code {service_code}.", *missing_actions)

    return AnalysisResult(
        request_id=request_id,
        policy_id=policy["policy_id"],
        payer=policy["payer"],
        service_code=service_code,
        service_name=policy["service"].get("name", "Requested service"),
        patient=summarize_patient(bundle),
        status=LEGACY_STATUS[outcome]
        if outcome != "INCOMPLETE"
        else ("needs_evidence" if best.completion_rate >= COMPLETION_THRESHOLD else "not_ready"),
        risk_band=_risk_band(outcome, best),
        score=best.score,
        max_score=best.max_score,
        best_pathway=best,
        criteria=criteria,
        missing_actions=missing_actions,
        warnings=tuple(warnings),
        outcome=outcome,
        policy_version=_policy_version(policy),
        issues=tuple(issues),
    )


def _request_id(policy: Any, bundle: Any, service_code: Any) -> str:
    import hashlib
    import json

    try:
        payload = json.dumps([policy, bundle, str(service_code)], sort_keys=True, default=str)
    except (TypeError, ValueError):
        payload = repr((policy, bundle, service_code))
    return "pp-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def _policy_version(policy: dict[str, Any]) -> str | None:
    version = policy.get("policy_version")
    return version if isinstance(version, str) else None


def _policy_issue(message: str) -> Issue:
    code = "POLICY_UNSUPPORTED_SCHEMA_VERSION" if message.startswith("schema_version") else "POLICY_INVALID"
    return Issue(code, "error", message, path=message.split(":", 1)[0])


def _has_code(resource: dict[str, Any], code: str) -> bool:
    codings = resource.get("code", {}).get("coding", []) if isinstance(resource.get("code"), dict) else []
    return any(isinstance(c, dict) and str(c.get("code")) == code for c in codings)


def _effective_window(policy: dict[str, Any], request_date: Any) -> tuple[Issue | None, Issue | None]:
    start, end = policy.get("effective_start"), policy.get("effective_end")
    if not start and not end:
        return None, None
    day = parse_day(request_date.value) if request_date and request_date.status == "ok" else None
    if day is None:
        return None, Issue(
            "POLICY_EFFECTIVE_DATE_UNVERIFIABLE",
            "error",
            "Policy has an effective period but the request date is missing or ambiguous.",
        )
    if (start and day.isoformat() < start) or (end and day.isoformat() > end):
        return (
            Issue(
                "POLICY_NOT_EFFECTIVE",
                "error",
                f"Request date {day.isoformat()} is outside the policy effective period "
                f"{start or '...'} to {end or '...'}.",
            ),
            None,
        )
    return None, None


def _apply_prerequisites(
    policy: dict[str, Any], criteria: tuple[CriterionResult, ...]
) -> tuple[CriterionResult, ...]:
    by_id = {c.criterion_id: c for c in criteria}
    prerequisites = {c["id"]: c["prerequisite"] for c in policy["criteria"] if "prerequisite" in c}
    out = []
    for result in criteria:
        target = prerequisites.get(result.criterion_id)
        if target and result.status == "met" and by_id[target].status != "met":
            issue = Issue(
                "PREREQUISITE_UNMET",
                "error",
                f"Criterion '{result.criterion_id}' requires '{target}' to be met first.",
                criterion_id=result.criterion_id,
            )
            result = replace(
                result,
                status="missing",
                rationale=f"Prerequisite criterion '{target}' is not met.",
                issues=(*result.issues, issue),
            )
        out.append(result)
    return tuple(out)


def _best_pathway(policy: dict[str, Any], criteria: tuple[CriterionResult, ...]) -> PathwayResult:
    by_id = {result.criterion_id: result for result in criteria}
    results: list[PathwayResult] = []
    for pathway in policy["pathways"]:
        requires = tuple(pathway["requires"])
        mandatory = tuple(c for c in requires if by_id[c].required)
        optional = tuple(c for c in requires if not by_id[c].required)
        met = tuple(c for c in mandatory if by_id[c].status == "met")
        unmet = tuple(c for c in mandatory if by_id[c].status != "met")
        missing = tuple(c for c in unmet if by_id[c].status in {"missing", "partial"})
        unresolved = tuple(c for c in unmet if by_id[c].status == "needs_review")
        results.append(
            PathwayResult(
                pathway_id=pathway["id"],
                label=pathway.get("label", pathway["id"]),
                required_criteria=mandatory,
                met_criteria=met,
                missing_criteria=missing,
                score=sum(by_id[c].earned_weight for c in mandatory),
                max_score=sum(by_id[c].weight for c in mandatory),
                optional_criteria=optional,
                unresolved_criteria=unresolved,
            )
        )
    return max(
        results,
        key=lambda p: (
            len(p.missing_criteria) == 0 and len(p.unresolved_criteria) == 0,
            p.completion_rate,
            p.score,
            -len(p.missing_criteria),
        ),
    )


def _actions(criteria: tuple[CriterionResult, ...], best: PathwayResult, outcome: str) -> tuple[str, ...]:
    gaps = set(best.missing_criteria) | set(best.unresolved_criteria)
    actions = []
    for result in criteria:
        if result.criterion_id in gaps and result.missing_action:
            actions.append(result.missing_action)
    return tuple(actions)


def _risk_band(outcome: str, pathway: PathwayResult) -> str:
    if outcome == "READY":
        return "low"
    if outcome in {"INVALID_INPUT", "POLICY_MISMATCH"}:
        return "high"
    if not pathway.required_criteria:
        return "high"
    return "moderate" if pathway.completion_rate >= COMPLETION_THRESHOLD else "high"


def _invalid(
    policy: Any, service_code: str, request_id: str, issues: tuple[Issue, ...]
) -> AnalysisResult:
    policy = policy if isinstance(policy, dict) else {}
    service = policy.get("service") if isinstance(policy.get("service"), dict) else {}
    pathway = PathwayResult("none", "No evaluable pathway", (), (), (), 0, 0)
    policy_id = policy.get("policy_id")
    payer = policy.get("payer")
    return AnalysisResult(
        request_id=request_id,
        policy_id=policy_id if isinstance(policy_id, str) else "unknown",
        payer=payer if isinstance(payer, str) else "unknown",
        service_code=service_code,
        service_name=service.get("name", "Requested service") if isinstance(service.get("name"), str) else "Requested service",
        patient=PatientSummary("unknown", "Unknown synthetic patient", None, None),
        status=LEGACY_STATUS["INVALID_INPUT"],
        risk_band="high",
        score=0,
        max_score=0,
        best_pathway=pathway,
        criteria=(),
        missing_actions=("Correct the invalid input and re-run; no readiness determination was made.",),
        warnings=tuple(issue.message for issue in issues),
        outcome="INVALID_INPUT",
        policy_version=_policy_version(policy),
        issues=issues,
    )
