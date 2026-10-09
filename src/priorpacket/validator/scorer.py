from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from priorpacket.engine.builder import (
    ClinicalCode,
    LabCriterion,
    NoteCriterion,
    PolicyRule,
    TreatmentCriterion,
    flatten_text,
    has_code,
    iter_resources,
    lab_in_range,
)


class AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AuditIssue(AuditModel):
    code: str
    severity: str
    message: str
    criterion: str | None = None
    resource: str | None = None
    path: str | None = None


class AuditResult(AuditModel):
    status: str
    score: int
    passed: bool
    issues: list[AuditIssue] = Field(default_factory=list)
    checked: int
    satisfied: int


class CompletenessScorer:
    """Verify criteria adherence for a synthesized authorization packet."""

    def audit(self, packet: dict[str, Any], payer_policy: dict[str, Any] | PolicyRule) -> AuditResult:
        policy = (
            payer_policy
            if isinstance(payer_policy, PolicyRule)
            else PolicyRule.model_validate(payer_policy)
        )
        resources = list(iter_resources(packet))
        issues: list[AuditIssue] = []
        checked = 0
        satisfied = 0

        for required_type in ("Patient", "Claim"):
            checked += 1
            if any(resource.get("resourceType") == required_type for resource in resources):
                satisfied += 1
            else:
                issues.append(
                    AuditIssue(
                        code=f"MISSING_{required_type.upper()}",
                        severity="error",
                        message=f"Packet does not contain a {required_type} resource.",
                    )
                )

        if any(resource.get("resourceType") == "Coverage" for resource in resources):
            checked += 1
            satisfied += 1
        else:
            checked += 1
            issues.append(
                AuditIssue(
                    code="MISSING_COVERAGE",
                    severity="error",
                    message="Packet does not contain active coverage evidence.",
                )
            )

        for diagnosis in policy.required_diagnoses:
            checked += 1
            if self._has_diagnosis(resources, diagnosis):
                satisfied += 1
            else:
                issues.append(
                    AuditIssue(
                        code="MISSING_DIAGNOSIS",
                        severity="error",
                        message=f"Missing required ICD-10-CM diagnosis code {diagnosis.code}.",
                        criterion=diagnosis.code,
                        path="Condition.code|Claim.diagnosis.diagnosisCodeableConcept",
                    )
                )

        for procedure in policy.required_procedures or [policy.requested_service]:
            checked += 1
            if self._has_claim_item(resources, procedure):
                satisfied += 1
            else:
                issues.append(
                    AuditIssue(
                        code="MISSING_PROCEDURE",
                        severity="error",
                        message=f"Missing requested CPT/HCPCS service code {procedure.code}.",
                        criterion=procedure.code,
                        path="Claim.item.productOrService",
                    )
                )

        for lab in policy.required_labs:
            checked += 1
            lab_issue = self._lab_issue(resources, lab)
            if lab_issue is None:
                satisfied += 1
            else:
                issues.append(lab_issue)

        for treatment in policy.prerequisite_treatments:
            checked += 1
            if self._has_treatment(resources, treatment):
                satisfied += 1
            else:
                issues.append(
                    AuditIssue(
                        code="MISSING_TREATMENT",
                        severity="error",
                        message=(
                            f"Missing prerequisite failed/intolerant treatment evidence "
                            f"for {treatment.code}."
                        ),
                        criterion=treatment.code,
                    )
                )

        for note in policy.required_notes:
            checked += 1
            if self._has_note(resources, note):
                satisfied += 1
            else:
                issues.append(
                    AuditIssue(
                        code="MISSING_NOTE",
                        severity="error",
                        message=f"Missing physician-note evidence containing '{note.contains}'.",
                        criterion=note.contains,
                    )
                )

        rejection_issue = self._rejection_issue(resources)
        if rejection_issue is not None:
            issues.append(rejection_issue)

        score = int(round((satisfied / checked) * 100)) if checked else 100
        has_errors = any(issue.severity == "error" for issue in issues)
        status = "pass"
        if rejection_issue is not None:
            status = "rejected"
        elif has_errors:
            status = "incomplete"
        return AuditResult(
            status=status,
            score=score,
            passed=status == "pass",
            issues=issues,
            checked=checked,
            satisfied=satisfied,
        )

    def _has_diagnosis(self, resources: list[dict[str, Any]], diagnosis: ClinicalCode) -> bool:
        for resource in resources:
            if resource.get("resourceType") == "Condition" and has_code(resource.get("code"), diagnosis):
                return True
            if resource.get("resourceType") == "Claim":
                for item in resource.get("diagnosis", []):
                    if has_code(item.get("diagnosisCodeableConcept"), diagnosis):
                        return True
        return False

    def _has_claim_item(self, resources: list[dict[str, Any]], procedure: ClinicalCode) -> bool:
        for claim in [resource for resource in resources if resource.get("resourceType") == "Claim"]:
            for item in claim.get("item", []):
                if has_code(item.get("productOrService"), procedure):
                    return True
        return False

    def _lab_issue(self, resources: list[dict[str, Any]], lab: LabCriterion) -> AuditIssue | None:
        clinical_code = ClinicalCode(code=lab.code, system=lab.system, display=lab.display)
        observations = [
            resource
            for resource in resources
            if resource.get("resourceType") == "Observation" and has_code(resource.get("code"), clinical_code)
        ]
        if not observations:
            return AuditIssue(
                code="MISSING_LAB",
                severity="error",
                message=f"Missing prerequisite lab observation {lab.code}.",
                criterion=lab.code,
                path="Observation.code",
            )
        if any(lab_in_range(resource, lab) for resource in observations):
            return None
        return AuditIssue(
            code="LAB_OUT_OF_RANGE",
            severity="error",
            message=f"Lab observation {lab.code} is present but outside the required range.",
            criterion=lab.code,
            resource=",".join(
                f"Observation/{resource.get('id')}" for resource in observations if resource.get("id")
            ),
            path="Observation.valueQuantity",
        )

    def _has_treatment(self, resources: list[dict[str, Any]], treatment: TreatmentCriterion) -> bool:
        clinical_code = ClinicalCode(code=treatment.code, system=treatment.system)
        status_words = {status.casefold() for status in treatment.statuses}
        for resource in resources:
            if not (
                has_code(resource.get("code"), clinical_code)
                or has_code(resource.get("medicationCodeableConcept"), clinical_code)
            ):
                continue
            text = flatten_text(resource).casefold()
            if any(status in text for status in status_words):
                return True
        return False

    def _has_note(self, resources: list[dict[str, Any]], note: NoteCriterion) -> bool:
        needle = note.contains.casefold()
        return any(needle in flatten_text(resource).casefold() for resource in resources)

    def _rejection_issue(self, resources: list[dict[str, Any]]) -> AuditIssue | None:
        for response in [resource for resource in resources if resource.get("resourceType") == "ClaimResponse"]:
            disposition = str(response.get("disposition", ""))
            outcome = str(response.get("outcome", ""))
            text = f"{outcome} {disposition}".casefold()
            if outcome == "error" or any(word in text for word in ("reject", "denied", "deny")):
                return AuditIssue(
                    code="AUTH_REJECTED",
                    severity="error",
                    message=disposition or "Authorization request was rejected by payer response.",
                    resource=f"ClaimResponse/{response.get('id')}",
                    path="ClaimResponse.outcome|ClaimResponse.disposition",
                )
        return None
