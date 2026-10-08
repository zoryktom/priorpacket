from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CriterionStatus = Literal["met", "missing", "partial"]


@dataclass(frozen=True)
class EvidenceHit:
    resource_type: str
    resource_id: str
    label: str
    detail: str
    date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "label": self.label,
            "detail": self.detail,
            "date": self.date,
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

    @property
    def earned_weight(self) -> int:
        if self.status == "met":
            return self.weight
        if self.status == "partial":
            return self.weight // 2
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "label": self.label,
            "status": self.status,
            "weight": self.weight,
            "earned_weight": self.earned_weight,
            "rationale": self.rationale,
            "missing_action": self.missing_action,
            "evidence": [hit.to_dict() for hit in self.evidence],
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
            "met_criteria": list(self.met_criteria),
            "missing_criteria": list(self.missing_criteria),
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

    @property
    def score_percent(self) -> int:
        if self.max_score <= 0:
            return 0
        return round((self.score / self.max_score) * 100)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "payer": self.payer,
            "service_code": self.service_code,
            "service_name": self.service_name,
            "patient": self.patient.to_dict(),
            "status": self.status,
            "risk_band": self.risk_band,
            "score": self.score,
            "max_score": self.max_score,
            "score_percent": self.score_percent,
            "best_pathway": self.best_pathway.to_dict(),
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "missing_actions": list(self.missing_actions),
            "warnings": list(self.warnings),
        }
