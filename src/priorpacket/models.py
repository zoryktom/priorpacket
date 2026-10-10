from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CriterionStatus = Literal["met", "missing", "partial", "needs_review"]

# Canonical research outcomes. ``AnalysisResult.status`` is a legacy, derived view
# of the outcome (see ``LEGACY_STATUS``) kept for backward compatibility.
OUTCOMES = ("READY", "INCOMPLETE", "NEEDS_REVIEW", "INVALID_INPUT", "POLICY_MISMATCH")


@dataclass(frozen=True)
class Issue:
    """A stable, machine-readable finding about a policy, packet, or criterion."""

    code: str
    severity: str  # "error" blocks READY, "warning" is reported, "info" is context
    message: str
    criterion_id: str | None = None
    resource: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "criterion_id": self.criterion_id,
            "resource": self.resource,
            "path": self.path,
        }


@dataclass(frozen=True)
class EvidenceHit:
    resource_type: str
    resource_id: str
    label: str
    detail: str
    date: str | None = None
    source_reference: str | None = None
    code: str | None = None
    system: str | None = None
    value: str | None = None
    unit: str | None = None
    selection_reason: str | None = None
    attribution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "label": self.label,
            "detail": self.detail,
            "date": self.date,
            "source_reference": self.source_reference or f"{self.resource_type}/{self.resource_id}",
            "code": self.code,
            "system": self.system,
            "value": self.value,
            "unit": self.unit,
            "selection_reason": self.selection_reason,
            "attribution": self.attribution,
        }


@dataclass(frozen=True)
class RejectedEvidence:
    """A candidate resource that looked relevant but failed a required constraint."""

    resource_type: str
    resource_id: str
    reason_code: str
    detail: str
    date: str | None = None
    code: str | None = None
    value: str | None = None
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "source_reference": f"{self.resource_type}/{self.resource_id}",
            "reason_code": self.reason_code,
            "detail": self.detail,
            "date": self.date,
            "code": self.code,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class CriterionResult:
    criterion_id: str
    label: str
    status: CriterionStatus
    weight: int
    rationale: str
    evidence: tuple[EvidenceHit, ...] = field(default_factory=tuple)
    missing_action: str | None = None
    required: bool = True
    kind: str | None = None
    description: str | None = None
    rejected: tuple[RejectedEvidence, ...] = field(default_factory=tuple)
    issues: tuple[Issue, ...] = field(default_factory=tuple)
    candidates_examined: int = 0

    @property
    def earned_weight(self) -> int:
        if self.status == "met":
            return self.weight
        if self.status == "partial":
            return self.weight // 2
        return 0

    @property
    def inference(self) -> str:
        if self.status == "met":
            return (
                f"Inferred met: {len(self.evidence)} observed resource(s) satisfy every "
                "constraint of this criterion."
            )
        if self.status == "needs_review":
            return (
                "Inferred unresolved: observed evidence is conflicting, ambiguous, or cannot be "
                "verified, so no safe determination is made."
            )
        return (
            "Inferred not met: no observed resource in this packet satisfies the criterion. "
            "Absence from the packet is not proof that the underlying event did not occur."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "label": self.label,
            "description": self.description or self.label,
            "kind": self.kind,
            "required": self.required,
            "status": self.status,
            "weight": self.weight,
            "earned_weight": self.earned_weight,
            "rationale": self.rationale,
            "missing_action": self.missing_action,
            "evidence": [hit.to_dict() for hit in self.evidence],
            "rejected_evidence": [item.to_dict() for item in self.rejected],
            "issues": [issue.to_dict() for issue in self.issues],
            "provenance": {
                "observed": [hit.source_reference or f"{hit.resource_type}/{hit.resource_id}" for hit in self.evidence],
                "inferred": self.inference,
                "candidates_examined": self.candidates_examined,
                "absence_of_evidence": not self.evidence,
            },
        }


@dataclass(frozen=True)
class PathwayResult:
    pathway_id: str
    label: str
    required_criteria: tuple[str, ...]
    met_criteria: tuple[str, ...]
    missing_criteria: tuple[str, ...]
    score: int
    max_score: int
    optional_criteria: tuple[str, ...] = field(default_factory=tuple)
    unresolved_criteria: tuple[str, ...] = field(default_factory=tuple)

    @property
    def completion_rate(self) -> float:
        if not self.required_criteria:
            return 0.0
        return len(self.met_criteria) / len(self.required_criteria)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pathway_id": self.pathway_id,
            "label": self.label,
            "required_criteria": list(self.required_criteria),
            "optional_criteria": list(self.optional_criteria),
            "met_criteria": list(self.met_criteria),
            "missing_criteria": list(self.missing_criteria),
            "unresolved_criteria": list(self.unresolved_criteria),
            "score": self.score,
            "max_score": self.max_score,
            "completion_rate": round(self.completion_rate, 3),
        }


@dataclass(frozen=True)
class PatientSummary:
    patient_id: str
    display: str
    birth_date: str | None
    sex: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "display": self.display,
            "birth_date": self.birth_date,
            "sex": self.sex,
        }


LEGACY_STATUS = {
    "READY": "ready_for_review",
    "INCOMPLETE": "needs_evidence",
    "NEEDS_REVIEW": "needs_review",
    "INVALID_INPUT": "invalid_input",
    "POLICY_MISMATCH": "policy_mismatch",
}


@dataclass(frozen=True)
class AnalysisResult:
    request_id: str
    policy_id: str
    payer: str
    service_code: str
    service_name: str
    patient: PatientSummary
    status: str
    risk_band: str
    score: int
    max_score: int
    best_pathway: PathwayResult
    criteria: tuple[CriterionResult, ...]
    missing_actions: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    outcome: str = "INCOMPLETE"
    policy_version: str | None = None
    issues: tuple[Issue, ...] = field(default_factory=tuple)

    @property
    def score_percent(self) -> int:
        if self.max_score <= 0:
            return 0
        return round((self.score / self.max_score) * 100)

    @property
    def issue_codes(self) -> tuple[str, ...]:
        """Sorted unique codes of error/warning issues for the packet and the criteria that
        decide the outcome (mandatory criteria of the best pathway)."""
        decisive = set(self.best_pathway.required_criteria)
        codes = {
            issue.code
            for issue in (
                *self.issues,
                *(i for c in self.criteria if c.criterion_id in decisive for i in c.issues),
            )
            if issue.severity in {"error", "warning"}
        }
        return tuple(sorted(codes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "payer": self.payer,
            "service_code": self.service_code,
            "service_name": self.service_name,
            "patient": self.patient.to_dict(),
            "outcome": self.outcome,
            "status": self.status,
            "risk_band": self.risk_band,
            "score": self.score,
            "max_score": self.max_score,
            "score_percent": self.score_percent,
            "best_pathway": self.best_pathway.to_dict(),
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "missing_actions": list(self.missing_actions),
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
            "issue_codes": list(self.issue_codes),
        }
