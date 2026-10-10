from __future__ import annotations

import operator
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from .context import BundleContext, resource_key
from .fhir import code_display, days_between, resource_date_info, text_blob
from .models import CriterionResult, EvidenceHit, Issue, RejectedEvidence

OPERATORS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}

KIND_SPEC: dict[str, tuple[str, tuple[str, ...]]] = {
    "condition": ("Condition", ("code",)),
    "procedure": ("Procedure", ("code",)),
    "observation": ("Observation", ("code",)),
    "medication": ("MedicationRequest", ("medicationCodeableConcept",)),
    "document": ("DocumentReference", ()),
}

# Resource statuses that mean the record must not be used as supporting evidence.
INVALID_STATUSES = frozenset({"entered-in-error", "not-done", "cancelled", "refuted"})

# Rejection reasons that leave a criterion unresolved (needs human review) when no
# other resource qualifies. Every other reason leaves the criterion plainly unmet.
ESCALATING_REASONS = frozenset(
    {
        "WRONG_PATIENT",
        "MISSING_RESOURCE_ID",
        "CODE_SYSTEM_MISMATCH",
        "CODE_SYSTEM_MISSING",
        "UNIT_MISMATCH",
        "UNIT_MISSING",
        "MALFORMED_VALUE",
        "MISSING_DATE",
        "AMBIGUOUS_DATE",
        "CONFLICTING_DATES",
        "NO_REFERENCE_DATE",
        "DATE_AFTER_REQUEST",
        "DUPLICATE_ID_CONFLICT",
        "CONTRADICTED_BY_RECORD",
    }
)


@dataclass(frozen=True)
class _Rejection:
    reason: str
    detail: str


class EvidenceMapper:
    """Evaluate policy criteria against a bundle with explicit, deterministic semantics."""

    def __init__(
        self,
        bundle: dict[str, Any],
        service_request_date: str | None = None,
        *,
        context: BundleContext | None = None,
        patient_id: str | None = None,
        reference_date_status: str | None = None,
    ):
        self.bundle = bundle
        self.ctx = context or BundleContext(bundle)
        self.patient_id = patient_id if patient_id is not None else self.ctx.select_patient_id(None)
        self.service_request_date = service_request_date
        self.reference_date_status = reference_date_status or ("ok" if service_request_date else "missing")

    def evaluate(self, criterion: dict[str, Any]) -> CriterionResult:
        kind = criterion.get("kind")
        base = {
            "criterion_id": criterion["id"],
            "label": criterion.get("label", criterion["id"]),
            "weight": int(criterion.get("weight", 0)),
            "required": bool(criterion.get("required", True)),
            "kind": kind if isinstance(kind, str) else None,
            "description": criterion.get("description", criterion.get("label", criterion["id"])),
        }
        if kind not in KIND_SPEC:
            issue = Issue(
                "UNSUPPORTED_CRITERION_KIND",
                "error",
                f"Criterion kind {kind!r} is not supported and cannot be treated as satisfied.",
                criterion_id=criterion["id"],
            )
            return CriterionResult(
                status="needs_review",
                rationale=f"Unsupported criterion kind: {kind}",
                missing_action=criterion.get("missing_action", "Review policy configuration."),
                issues=(issue,),
                **base,
            )

        resource_type, code_paths = KIND_SPEC[kind]
        candidates = self.ctx.by_type(resource_type)
        hits: list[EvidenceHit] = []
        rejected: list[RejectedEvidence] = []

        for resource in candidates:
            matched = self._match(resource, criterion, kind, code_paths)
            if matched is None:
                continue
            if isinstance(matched, _Rejection):
                rejected.append(self._reject(resource, matched))
                continue
            outcome = self._check_constraints(resource, criterion, kind, matched)
            if isinstance(outcome, _Rejection):
                rejected.append(self._reject(resource, outcome, matched))
                continue
            hits.append(outcome)

        hits = self._order_hits(hits)
        value_failures = [item for item in rejected if item.reason_code == "VALUE_OUT_OF_RANGE"]
        conflict_issues, contradicting = self._conflicts(criterion, resource_type, hits, value_failures)
        rejected.extend(contradicting)
        rejected = self._order_rejected(rejected)

        if conflict_issues:
            status = "needs_review"
        elif hits:
            status = "met"
        elif any(item.reason_code in ESCALATING_REASONS for item in rejected):
            status = "needs_review"
        else:
            status = "missing"

        issues = self._issues(criterion, status, hits, rejected, conflict_issues)
        if status == "met":
            rationale = criterion.get("met_rationale", "Required evidence found.")
            action = None
        elif status == "needs_review":
            rationale = (
                "Evidence for this criterion is conflicting, ambiguous, or unverifiable; "
                "it was neither accepted nor treated as absent."
            )
            action = criterion.get(
                "review_action", "Resolve the flagged evidence problem and re-run the analysis."
            )
        else:
            rationale = criterion.get("missing_rationale", self._default_missing_rationale(kind))
            action = criterion.get("missing_action", "Collect supporting documentation.")
        return CriterionResult(
            status=status,
            rationale=rationale,
            evidence=tuple(hits),
            missing_action=action,
            rejected=tuple(rejected),
            issues=issues,
            candidates_examined=len(candidates),
            **base,
        )

    @staticmethod
    def _default_missing_rationale(kind: str) -> str:
        return {
            "condition": "No matching diagnosis was found in the packet.",
            "procedure": "No matching procedure was found in the packet.",
            "observation": "No matching observation was found in the packet.",
            "medication": (
                "No matching medication evidence was found in the packet; this does not "
                "establish that the treatment was not attempted."
            ),
            "document": (
                "No matching document evidence was found in the packet; this does not "
                "establish that the treatment or finding is absent from the record."
            ),
        }[kind]

    # -- matching ---------------------------------------------------------------------

    @staticmethod
    def _codings(resource: dict[str, Any], paths: tuple[str, ...]) -> list[dict[str, Any]]:
        codings: list[dict[str, Any]] = []
        for path in paths:
            node = resource.get(path)
            for item in node if isinstance(node, list) else [node]:
                if isinstance(item, dict) and isinstance(item.get("coding"), list):
                    codings.extend(c for c in item["coding"] if isinstance(c, dict))
        return codings

    def _match(
        self,
        resource: dict[str, Any],
        criterion: dict[str, Any],
        kind: str,
        code_paths: tuple[str, ...],
    ) -> dict[str, Any] | _Rejection | None:
        expected = {str(code).upper() for code in criterion.get("codes", [])}
        keywords = [str(k).lower() for k in criterion.get("keywords", [])]
        if kind == "document":
            return self._keyword_match(resource, criterion, keywords)

        codings = self._codings(resource, code_paths)
        matching = [c for c in codings if str(c.get("code", "")).upper() in expected]
        if not matching:
            if kind == "medication" and keywords:
                return self._keyword_match(resource, criterion, keywords)
            return None

        systems = criterion.get("code_systems")
        if systems:
            allowed = [c for c in matching if c.get("system") in systems]
            if not allowed:
                seen = sorted({str(c.get("system")) for c in matching if c.get("system")})
                if not seen:
                    return _Rejection("CODE_SYSTEM_MISSING", "matching code has no coding system")
                return _Rejection(
                    "CODE_SYSTEM_MISMATCH",
                    f"code matches but system {', '.join(seen)} is not one of {', '.join(systems)}",
                )
            matching = allowed
        chosen = sorted(matching, key=lambda c: (str(c.get("system")), str(c.get("code"))))[0]
        codes = sorted({str(c.get("code")).upper() for c in matching})
        return {
            "code": str(chosen.get("code")),
            "system": chosen.get("system"),
            "detail": f"Matched code(s): {', '.join(codes)}",
        }

    @staticmethod
    def _keyword_match(
        resource: dict[str, Any],
        criterion: dict[str, Any],
        keywords: list[str],
    ) -> dict[str, Any] | None:
        if not keywords:
            return None
        blob = text_blob(resource)
        found = [k for k in keywords if k in blob]
        if criterion.get("require_all_keywords", False):
            if len(found) != len(keywords):
                return None
        elif not found:
            return None
        return {"code": None, "system": None, "detail": f"Matched keyword(s): {', '.join(found)}"}

    # -- constraints ------------------------------------------------------------------

    def _check_constraints(
        self,
        resource: dict[str, Any],
        criterion: dict[str, Any],
        kind: str,
        matched: dict[str, Any],
    ) -> EvidenceHit | _Rejection:
        if not resource.get("id"):
            return _Rejection("MISSING_RESOURCE_ID", "resource has no id so it cannot be cited")
        if id(resource) in self.ctx.id_conflicts:
            return _Rejection(
                "DUPLICATE_ID_CONFLICT", "another resource with the same id has different content"
            )

        state, note = self.ctx.attribution(resource, self.patient_id)
        if state == "wrong_patient":
            return _Rejection("WRONG_PATIENT", note or "resource belongs to a different patient")

        for state_value in (resource.get("status"), _verification_code(resource)):
            if isinstance(state_value, str) and state_value in INVALID_STATUSES:
                return _Rejection(
                    "RESOURCE_STATUS_INVALID", f"status {state_value!r} cannot support a criterion"
                )

        date_info = resource_date_info(resource)
        within_days = criterion.get("within_days")
        if date_info.status == "conflicting":
            return _Rejection("CONFLICTING_DATES", date_info.detail)
        if within_days:
            window = self._window_rejection(date_info, int(within_days))
            if window:
                return window

        value_text: str | None = None
        unit_text: str | None = None
        if kind == "observation":
            checked = self._check_observation(resource, criterion)
            if isinstance(checked, _Rejection):
                return checked
            value_text, unit_text = checked

        if kind == "document":
            label = resource.get("description") or resource.get("title") or code_display(resource, "type")
        elif kind == "medication":
            label = code_display(resource, "medicationCodeableConcept")
        else:
            label = code_display(resource, "code")
        return EvidenceHit(
            resource_type=resource["resourceType"],
            resource_id=str(resource["id"]),
            label=str(label),
            detail=matched["detail"],
            date=date_info.value,
            source_reference=resource_key(resource),
            code=matched.get("code"),
            system=matched.get("system"),
            value=value_text,
            unit=unit_text,
            attribution=state if note is None else f"{state}: {note}",
        )

    def _window_rejection(self, date_info: Any, within_days: int) -> _Rejection | None:
        if date_info.status == "ambiguous":
            return _Rejection("AMBIGUOUS_DATE", date_info.detail)
        if date_info.status == "missing":
            return _Rejection("MISSING_DATE", f"{date_info.detail}; the lookback window cannot be checked")
        if self.reference_date_status != "ok" or not self.service_request_date:
            return _Rejection(
                "NO_REFERENCE_DATE",
                "the request date is missing or ambiguous, so the lookback window cannot be checked",
            )
        age = days_between(self.service_request_date, date_info.value)
        if age is None:
            return _Rejection("AMBIGUOUS_DATE", "dates could not be compared")
        if age < 0:
            return _Rejection(
                "DATE_AFTER_REQUEST",
                f"evidence dated {date_info.value} is after the request date {self.service_request_date}",
            )
        if age > within_days:
            return _Rejection(
                "EVIDENCE_OUTSIDE_WINDOW",
                f"evidence is {age} days old; policy window is {within_days} days (inclusive)",
            )
        return None

    def _check_observation(
        self,
        resource: dict[str, Any],
        criterion: dict[str, Any],
    ) -> tuple[str | None, str | None] | _Rejection:
        needs_value = any(criterion.get(name) is not None for name in ("operator", "min_value", "max_value"))
        quantity = resource.get("valueQuantity")
        if not needs_value and not isinstance(quantity, dict):
            return None, None
        if not isinstance(quantity, dict) or quantity.get("value") is None:
            if needs_value:
                return _Rejection("MALFORMED_VALUE", "observation has no numeric valueQuantity.value")
            return None, None
        raw = quantity["value"]
        try:
            if isinstance(raw, bool):
                raise InvalidOperation
            value = Decimal(str(raw))
            if not value.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            return _Rejection("MALFORMED_VALUE", f"valueQuantity.value {raw!r} is not numeric")

        unit = quantity.get("code") or quantity.get("unit")
        expected_unit = criterion.get("unit")
        if expected_unit:
            if not unit:
                return _Rejection(
                    "UNIT_MISSING", f"policy requires unit {expected_unit!r}; observation has no unit"
                )
            accepted = {str(expected_unit).casefold()}
            accepted.update(str(u).casefold() for u in criterion.get("unit_aliases", []))
            reported = {
                str(quantity.get("code", "")).casefold(),
                str(quantity.get("unit", "")).casefold(),
            } - {""}
            if reported.isdisjoint(accepted):
                return _Rejection(
                    "UNIT_MISMATCH",
                    f"observation unit {unit!r} is not comparable with policy unit {expected_unit!r}",
                )

        failure = self._value_failure(value, criterion)
        if failure:
            return _Rejection("VALUE_OUT_OF_RANGE", failure)
        return str(raw), (str(unit) if unit else None)

    @staticmethod
    def _value_failure(value: Decimal, criterion: dict[str, Any]) -> str | None:
        op = criterion.get("operator")
        if op and not OPERATORS[op](value, Decimal(str(criterion["value"]))):
            return f"value {value} does not satisfy {op} {criterion['value']}"
        minimum, maximum = criterion.get("min_value"), criterion.get("max_value")
        if minimum is not None and value < Decimal(str(minimum)):
            return f"value {value} is below the minimum {minimum}"
        if maximum is not None and value > Decimal(str(maximum)):
            return f"value {value} is above the maximum {maximum}"
        return None

    # -- conflicts --------------------------------------------------------------------

    def _conflicts(
        self,
        criterion: dict[str, Any],
        resource_type: str,
        hits: list[EvidenceHit],
        value_failures: list[RejectedEvidence],
    ) -> tuple[list[Issue], list[RejectedEvidence]]:
        issues: list[Issue] = []
        contradicting: list[RejectedEvidence] = []
        phrases = [str(p).lower() for p in criterion.get("conflict_keywords", [])]
        if phrases and hits:
            scope = {resource_type, "DocumentReference"}
            for resource in self.ctx.resources:
                if resource["resourceType"] not in scope:
                    continue
                if self.ctx.attribution(resource, self.patient_id)[0] == "wrong_patient":
                    continue
                found = [p for p in phrases if p in text_blob(resource)]
                if found:
                    contradicting.append(
                        RejectedEvidence(
                            resource_type=resource["resourceType"],
                            resource_id=str(resource.get("id", "unknown")),
                            reason_code="CONTRADICTED_BY_RECORD",
                            detail=f"record states {', '.join(found)!r}, contradicting qualifying evidence",
                            date=resource_date_info(resource).value,
                        )
                    )
        if contradicting or (hits and value_failures):
            message = (
                "Qualifying evidence is contradicted by another record; both are preserved for review."
                if contradicting
                else "Observations for the same code disagree about the policy threshold; neither is preferred."
            )
            issues.append(Issue("CONFLICTING_EVIDENCE", "error", message, criterion_id=criterion["id"]))
        return issues, contradicting

    # -- bookkeeping ------------------------------------------------------------------

    @staticmethod
    def _reject(
        resource: dict[str, Any],
        rejection: _Rejection,
        matched: dict[str, Any] | None = None,
    ) -> RejectedEvidence:
        quantity = resource.get("valueQuantity")
        quantity = quantity if isinstance(quantity, dict) else {}
        value = quantity.get("value")
        return RejectedEvidence(
            resource_type=resource["resourceType"],
            resource_id=str(resource.get("id", "unknown")),
            reason_code=rejection.reason,
            detail=rejection.detail,
            date=resource_date_info(resource).value,
            code=(matched or {}).get("code"),
            value=str(value) if value is not None else None,
            unit=quantity.get("code") or quantity.get("unit"),
        )

    @staticmethod
    def _order_hits(hits: list[EvidenceHit]) -> list[EvidenceHit]:
        newest_first = sorted(hits, key=lambda h: (h.resource_type, h.resource_id))
        newest_first.sort(key=lambda h: h.date or "", reverse=True)
        newest_first.sort(key=lambda h: h.date is None)
        return [
            replace(
                hit,
                selection_reason=(
                    "primary: most recent qualifying resource"
                    if index == 0
                    else "additional qualifying resource (not needed to satisfy the criterion)"
                ),
            )
            for index, hit in enumerate(newest_first)
        ]

    @staticmethod
    def _order_rejected(items: list[RejectedEvidence]) -> list[RejectedEvidence]:
        unique = {(i.resource_type, i.resource_id, i.reason_code): i for i in items}
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _issues(
        criterion: dict[str, Any],
        status: str,
        hits: list[EvidenceHit],
        rejected: list[RejectedEvidence],
        conflict_issues: list[Issue],
    ) -> tuple[Issue, ...]:
        issues: list[Issue] = list(conflict_issues)
        for item in rejected:
            if status == "met":
                severity = "warning" if item.reason_code in ESCALATING_REASONS else "info"
            else:
                severity = "error"
            issues.append(
                Issue(
                    item.reason_code,
                    severity,
                    f"{item.resource_type}/{item.resource_id}: {item.detail}",
                    criterion_id=criterion["id"],
                    resource=f"{item.resource_type}/{item.resource_id}",
                )
            )
        if status == "missing" and not rejected:
            issues.append(
                Issue(
                    "MISSING_EVIDENCE",
                    "error",
                    "No qualifying evidence exists in the packet for this criterion.",
                    criterion_id=criterion["id"],
                )
            )
        for hit in hits:
            if hit.attribution and hit.attribution.startswith("unattributed"):
                issues.append(
                    Issue(
                        "UNATTRIBUTED_EVIDENCE",
                        "warning",
                        f"{hit.source_reference} has no subject reference; patient attribution is unverified.",
                        criterion_id=criterion["id"],
                        resource=hit.source_reference,
                    )
                )
        unique = {(i.code, i.criterion_id or "", i.resource or ""): i for i in issues}
        return tuple(unique[key] for key in sorted(unique))


def _verification_code(resource: dict[str, Any]) -> str | None:
    verification = resource.get("verificationStatus")
    if isinstance(verification, dict):
        codings = verification.get("coding", [])
        if codings and isinstance(codings[0], dict):
            return codings[0].get("code")
    return None
