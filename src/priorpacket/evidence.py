from __future__ import annotations

import operator
from typing import Any, Callable

from .fhir import (
    code_display,
    coding_values,
    days_between,
    resource_date,
    resources_by_type,
    text_blob,
)
from .models import CriterionResult, EvidenceHit


OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}


class EvidenceMapper:
    def __init__(self, bundle: dict[str, Any], service_request_date: str | None = None):
        self.bundle = bundle
        self.service_request_date = service_request_date

    def evaluate(self, criterion: dict[str, Any]) -> CriterionResult:
        kind = criterion.get("kind")
        if kind == "condition":
            return self._condition(criterion)
        if kind == "procedure":
            return self._procedure(criterion)
        if kind == "observation":
            return self._observation(criterion)
        if kind == "document":
            return self._document(criterion)
        if kind == "medication":
            return self._medication(criterion)
        return CriterionResult(
            criterion_id=criterion["id"],
            label=criterion.get("label", criterion["id"]),
            status="missing",
            weight=int(criterion.get("weight", 0)),
            rationale=f"Unsupported criterion kind: {kind}",
            missing_action=criterion.get("missing_action", "Review policy configuration."),
        )

    def _condition(self, criterion: dict[str, Any]) -> CriterionResult:
        resources = resources_by_type(self.bundle, "Condition")
        hits = self._match_code(
            resources,
            criterion,
            code_paths=("code",),
            label_path="code",
        )
        return self._result_from_hits(criterion, hits, "No matching diagnosis was found.")

    def _procedure(self, criterion: dict[str, Any]) -> CriterionResult:
        resources = resources_by_type(self.bundle, "Procedure")
        hits = self._match_code(
            resources,
            criterion,
            code_paths=("code",),
            label_path="code",
        )
        hits = self._filter_by_window(hits, criterion)
        return self._result_from_hits(criterion, hits, "No matching procedure was found.")

    def _medication(self, criterion: dict[str, Any]) -> CriterionResult:
        resources = resources_by_type(self.bundle, "MedicationRequest")
        hits = self._match_code(
            resources,
            criterion,
            code_paths=("medicationCodeableConcept",),
            label_path="medicationCodeableConcept",
        )
        if not hits and criterion.get("keywords"):
            hits = self._keyword_hits(resources, criterion)
        hits = self._filter_by_window(hits, criterion)
        return self._result_from_hits(criterion, hits, "No matching medication evidence was found.")

    def _document(self, criterion: dict[str, Any]) -> CriterionResult:
        resources = resources_by_type(self.bundle, "DocumentReference")
        hits = self._keyword_hits(resources, criterion)
        hits = self._filter_by_window(hits, criterion)
        return self._result_from_hits(criterion, hits, "No matching document evidence was found.")

    def _observation(self, criterion: dict[str, Any]) -> CriterionResult:
        resources = resources_by_type(self.bundle, "Observation")
        hits = self._match_code(
            resources,
            criterion,
            code_paths=("code",),
            label_path="code",
        )
        if criterion.get("operator") and criterion.get("value") is not None:
            hits = tuple(
                hit
                for hit in hits
                if self._observation_passes_value(hit.resource_id, criterion)
            )
        hits = self._filter_by_window(hits, criterion)
        return self._result_from_hits(criterion, hits, "No matching observation was found.")

    def _match_code(
        self,
        resources: list[dict[str, Any]],
        criterion: dict[str, Any],
        code_paths: tuple[str, ...],
        label_path: str,
    ) -> tuple[EvidenceHit, ...]:
        expected = {str(code).upper() for code in criterion.get("codes", [])}
        hits: list[EvidenceHit] = []
        for resource in resources:
            values = coding_values(resource, *code_paths)
            if expected and values.isdisjoint(expected):
                continue
            if not expected and not values:
                continue
            hits.append(
                EvidenceHit(
                    resource_type=resource.get("resourceType", "Resource"),
                    resource_id=resource.get("id", "unknown"),
                    label=code_display(resource, label_path),
                    detail=f"Matched code(s): {', '.join(sorted(values & expected or values))}",
                    date=resource_date(resource),
                )
            )
        return tuple(hits)

    def _keyword_hits(
        self,
        resources: list[dict[str, Any]],
        criterion: dict[str, Any],
    ) -> tuple[EvidenceHit, ...]:
        keywords = [str(keyword).lower() for keyword in criterion.get("keywords", [])]
        if not keywords:
            return tuple()

        require_all = bool(criterion.get("require_all_keywords", False))
        hits: list[EvidenceHit] = []
        for resource in resources:
            blob = text_blob(resource)
            matched = [keyword for keyword in keywords if keyword in blob]
            if require_all and len(matched) != len(keywords):
                continue
            if not require_all and not matched:
                continue
            hits.append(
                EvidenceHit(
                    resource_type=resource.get("resourceType", "Resource"),
                    resource_id=resource.get("id", "unknown"),
                    label=resource.get("description")
                    or resource.get("title")
                    or code_display(resource, "type"),
                    detail=f"Matched keyword(s): {', '.join(matched)}",
                    date=resource_date(resource),
                )
            )
        return tuple(hits)

    def _filter_by_window(
        self,
        hits: tuple[EvidenceHit, ...],
        criterion: dict[str, Any],
    ) -> tuple[EvidenceHit, ...]:
        within_days = criterion.get("within_days")
        if not within_days or not self.service_request_date:
            return hits
        filtered: list[EvidenceHit] = []
        for hit in hits:
            age = days_between(self.service_request_date, hit.date)
            if age is not None and 0 <= age <= int(within_days):
                filtered.append(hit)
        return tuple(filtered)

    def _observation_passes_value(self, resource_id: str, criterion: dict[str, Any]) -> bool:
        resources = resources_by_type(self.bundle, "Observation")
        resource = next((item for item in resources if item.get("id") == resource_id), None)
        if not resource:
            return False
        value = resource.get("valueQuantity", {}).get("value")
        if value is None:
            return False
        operation = OPERATORS.get(str(criterion.get("operator")))
        if not operation:
            return False
        return operation(float(value), float(criterion["value"]))

    def _result_from_hits(
        self,
        criterion: dict[str, Any],
        hits: tuple[EvidenceHit, ...],
        missing_rationale: str,
    ) -> CriterionResult:
        if hits:
            return CriterionResult(
                criterion_id=criterion["id"],
                label=criterion.get("label", criterion["id"]),
                status="met",
                weight=int(criterion.get("weight", 0)),
                rationale=criterion.get("met_rationale", "Required evidence found."),
                evidence=hits,
                missing_action=None,
            )
        return CriterionResult(
            criterion_id=criterion["id"],
            label=criterion.get("label", criterion["id"]),
            status="missing",
            weight=int(criterion.get("weight", 0)),
            rationale=criterion.get("missing_rationale", missing_rationale),
            evidence=tuple(),
            missing_action=criterion.get("missing_action", "Collect supporting documentation."),
        )
