from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from priorpacket.fhir import (
    Bundle,
    BundleEntry,
    Claim,
    ClaimDiagnosis,
    ClaimInsurance,
    ClaimItem,
    ClaimSupportingInfo,
    CodeableConcept,
    Reference,
    codeable_concept,
)

ICD10_CM = "http://hl7.org/fhir/sid/icd-10-cm"
LOINC = "http://loinc.org"
HCPCS = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"
SNOMED = "http://snomed.info/sct"
PRIORPACKET_SYSTEM = "https://priorpacket.dev/fhir/CodeSystem/evidence"


class EngineModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ClinicalCode(EngineModel):
    code: str
    system: str | None = None
    display: str | None = None
    text: str | None = None

    def to_codeable_concept(self) -> CodeableConcept:
        return codeable_concept(self.system, self.code, self.display, self.text)

    @property
    def key(self) -> tuple[str | None, str]:
        return (self.system, self.code)


class LabCriterion(EngineModel):
    code: str = Field(alias="loinc")
    system: str = LOINC
    display: str | None = Field(default=None, alias="name")
    min_value: float | None = Field(default=None, alias="min")
    max_value: float | None = Field(default=None, alias="max")
    unit: str | None = None
    lookback_days: int | None = 365

    @model_validator(mode="before")
    @classmethod
    def _accept_code_or_loinc(cls, data: Any) -> Any:
        if isinstance(data, dict) and "code" in data and "loinc" not in data:
            data = {**data, "loinc": data["code"]}
        return data

    def codeable(self) -> CodeableConcept:
        return codeable_concept(self.system, self.code, self.display)


class TreatmentCriterion(EngineModel):
    code: str
    system: str | None = None
    display: str | None = None
    statuses: list[str] = Field(default_factory=lambda: ["failed", "intolerant"])
    lookback_days: int | None = 730

    def codeable(self) -> CodeableConcept:
        return codeable_concept(self.system, self.code, self.display)


class NoteCriterion(EngineModel):
    contains: str
    lookback_days: int | None = 365


class PolicyRule(EngineModel):
    id: str
    title: str
    requested_service: ClinicalCode = Field(alias="service")
    required_diagnoses: list[ClinicalCode] = Field(default_factory=list)
    required_procedures: list[ClinicalCode] = Field(default_factory=list)
    required_labs: list[LabCriterion] = Field(default_factory=list)
    prerequisite_treatments: list[TreatmentCriterion] = Field(default_factory=list)
    required_notes: list[NoteCriterion] = Field(default_factory=list)
    request_date: str = "2026-01-01T00:00:00Z"
    payer: str = "Organization/payer"
    provider: str = "Organization/requesting-provider"

    @model_validator(mode="before")
    @classmethod
    def _accept_nested_criteria(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "requested_service" in normalized and "service" not in normalized:
            normalized["service"] = normalized["requested_service"]
        criteria = normalized.get("criteria")
        if isinstance(criteria, dict):
            mapping = {
                "diagnoses": "required_diagnoses",
                "procedures": "required_procedures",
                "labs": "required_labs",
                "treatments": "prerequisite_treatments",
                "notes": "required_notes",
            }
            for source, target in mapping.items():
                if source in criteria and target not in normalized:
                    normalized[target] = criteria[source]
        return normalized


@dataclass(frozen=True)
class EvidenceSelection:
    diagnoses: list[dict[str, Any]]
    labs: list[dict[str, Any]]
    treatments: list[dict[str, Any]]
    notes: list[dict[str, Any]]

    @property
    def resources(self) -> list[dict[str, Any]]:
        selected: dict[tuple[str, str], dict[str, Any]] = {}
        for resource in [*self.diagnoses, *self.labs, *self.treatments, *self.notes]:
            resource_type = resource.get("resourceType")
            resource_id = resource.get("id")
            if resource_type and resource_id:
                selected[(resource_type, resource_id)] = resource
        return [selected[key] for key in sorted(selected)]


class PacketBuilder:
    """Build deterministic prior authorization evidence packets."""

    def build(self, patient_record: dict[str, Any], policy_rule: dict[str, Any] | PolicyRule) -> Bundle:
        policy = (
            policy_rule
            if isinstance(policy_rule, PolicyRule)
            else PolicyRule.model_validate(policy_rule)
        )
        resources = list(iter_resources(patient_record))
        patient = require_one(resources, "Patient")
        coverage = first_resource(resources, "Coverage")
        selected = self.select_evidence(resources, policy)
        claim = self._build_claim(patient, coverage, selected, policy)
        bundle_resources = self._bundle_resources(patient, coverage, selected.resources, claim.fhir_dump())
        bundle_id = deterministic_id("bundle", patient.get("id"), policy.id)
        return Bundle(
            id=bundle_id,
            timestamp=policy.request_date,
            entry=[
                BundleEntry(fullUrl=f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, resource['resourceType'] + '/' + str(resource['id']))}", resource=resource)
                for resource in bundle_resources
            ],
        )

    def select_evidence(
        self, resources: Iterable[dict[str, Any]], policy: PolicyRule
    ) -> EvidenceSelection:
        resource_list = list(resources)
        diagnoses = [
            find_first_by_code(resource_list, "Condition", code)
            for code in policy.required_diagnoses
        ]
        labs = [
            find_best_lab(resource_list, lab)
            for lab in policy.required_labs
        ]
        treatments = [
            find_treatment(resource_list, treatment)
            for treatment in policy.prerequisite_treatments
        ]
        notes = [
            find_note(resource_list, note)
            for note in policy.required_notes
        ]
        return EvidenceSelection(
            diagnoses=[resource for resource in diagnoses if resource],
            labs=[resource for resource in labs if resource],
            treatments=[resource for resource in treatments if resource],
            notes=[resource for resource in notes if resource],
        )

    def _build_claim(
        self,
        patient: dict[str, Any],
        coverage: dict[str, Any] | None,
        selected: EvidenceSelection,
        policy: PolicyRule,
    ) -> Claim:
        claim_id = deterministic_id("claim", patient.get("id"), policy.id)
        diagnosis_items = [
            ClaimDiagnosis(
                sequence=index,
                diagnosisCodeableConcept=CodeableConcept.model_validate(resource["code"]),
                type=[codeable_concept(PRIORPACKET_SYSTEM, "principal-diagnosis")],
            )
            for index, resource in enumerate(selected.diagnoses, start=1)
        ]
        item_codes = policy.required_procedures or [policy.requested_service]
        claim_items = [
            ClaimItem(sequence=index, productOrService=code.to_codeable_concept())
            for index, code in enumerate(item_codes, start=1)
        ]
        supporting_info = make_supporting_info(selected)
        insurance = []
        if coverage:
            insurance.append(
                ClaimInsurance(
                    sequence=1,
                    focal=True,
                    coverage=Reference(reference=f"Coverage/{coverage['id']}"),
                )
            )
        return Claim(
            id=claim_id,
            patient=Reference(reference=f"Patient/{patient['id']}"),
            created=policy.request_date,
            provider=Reference(reference=policy.provider),
            insurer=Reference(reference=policy.payer),
            diagnosis=diagnosis_items,
            supportingInfo=supporting_info,
            insurance=insurance,
            item=claim_items,
        )

    def _bundle_resources(
        self,
        patient: dict[str, Any],
        coverage: dict[str, Any] | None,
        evidence: list[dict[str, Any]],
        claim: dict[str, Any],
    ) -> list[dict[str, Any]]:
        keyed: dict[tuple[str, str], dict[str, Any]] = {
            (patient["resourceType"], patient["id"]): patient,
            (claim["resourceType"], claim["id"]): claim,
        }
        if coverage:
            keyed[(coverage["resourceType"], coverage["id"])] = coverage
        for resource in evidence:
            keyed[(resource["resourceType"], resource["id"])] = resource
        return [keyed[key] for key in sorted(keyed)]


def iter_resources(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    if payload.get("resourceType") == "Bundle":
        for entry in payload.get("entry", []):
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if isinstance(resource, dict):
                yield resource
        return
    if "resources" in payload and isinstance(payload["resources"], list):
        for resource in payload["resources"]:
            if isinstance(resource, dict):
                yield resource
        return
    if "resourceType" in payload:
        yield payload


def require_one(resources: list[dict[str, Any]], resource_type: str) -> dict[str, Any]:
    resource = first_resource(resources, resource_type)
    if resource is None:
        raise ValueError(f"patient record is missing required FHIR resource: {resource_type}")
    return resource


def first_resource(resources: list[dict[str, Any]], resource_type: str) -> dict[str, Any] | None:
    matches = [resource for resource in resources if resource.get("resourceType") == resource_type]
    return sorted(matches, key=resource_sort_key)[0] if matches else None


def find_first_by_code(
    resources: list[dict[str, Any]],
    resource_type: str,
    criterion: ClinicalCode,
) -> dict[str, Any] | None:
    matches = [
        resource
        for resource in resources
        if resource.get("resourceType") == resource_type and has_code(resource.get("code"), criterion)
    ]
    return sorted(matches, key=resource_sort_key)[0] if matches else None


def find_best_lab(resources: list[dict[str, Any]], criterion: LabCriterion) -> dict[str, Any] | None:
    observations = [
        resource
        for resource in resources
        if resource.get("resourceType") == "Observation"
        and has_code(resource.get("code"), ClinicalCode(code=criterion.code, system=criterion.system))
    ]
    passing = [resource for resource in observations if lab_in_range(resource, criterion)]
    candidates = passing or observations
    return sorted(candidates, key=resource_sort_key)[-1] if candidates else None


def find_treatment(resources: list[dict[str, Any]], criterion: TreatmentCriterion) -> dict[str, Any] | None:
    clinical_code = ClinicalCode(code=criterion.code, system=criterion.system, display=criterion.display)
    candidates = [
        resource
        for resource in resources
        if (
            has_code(resource.get("code"), clinical_code)
            or has_code(resource.get("medicationCodeableConcept"), clinical_code)
            or has_code(resource.get("procedureCodeableConcept"), clinical_code)
        )
    ]
    status_words = {status.casefold() for status in criterion.statuses}
    matching = [
        resource
        for resource in candidates
        if any(status in flatten_text(resource).casefold() for status in status_words)
    ]
    return sorted(matching, key=resource_sort_key)[-1] if matching else None


def find_note(resources: list[dict[str, Any]], criterion: NoteCriterion) -> dict[str, Any] | None:
    needle = criterion.contains.casefold()
    matches = [
        resource
        for resource in resources
        if resource.get("resourceType") in {"Encounter", "Observation", "DocumentReference", "DiagnosticReport"}
        and needle in flatten_text(resource).casefold()
    ]
    return sorted(matches, key=resource_sort_key)[-1] if matches else None


def make_supporting_info(selection: EvidenceSelection) -> list[ClaimSupportingInfo]:
    items: list[tuple[str, dict[str, Any]]] = []
    items.extend(("diagnosis", resource) for resource in selection.diagnoses)
    items.extend(("lab", resource) for resource in selection.labs)
    items.extend(("prior-treatment", resource) for resource in selection.treatments)
    items.extend(("physician-note", resource) for resource in selection.notes)
    supporting_info = []
    for sequence, (category, resource) in enumerate(items, start=1):
        code = resource.get("code")
        supporting_info.append(
            ClaimSupportingInfo(
                sequence=sequence,
                category=codeable_concept(PRIORPACKET_SYSTEM, category),
                code=CodeableConcept.model_validate(code) if isinstance(code, dict) else None,
                timingDate=resource.get("effectiveDateTime") or resource.get("recordedDate"),
                valueReference=Reference(reference=f"{resource['resourceType']}/{resource['id']}"),
            )
        )
    return supporting_info


def has_code(codeable: Any, criterion: ClinicalCode) -> bool:
    if not isinstance(codeable, dict):
        return False
    codings = codeable.get("coding") or []
    for coding in codings:
        if not isinstance(coding, dict):
            continue
        code_matches = coding.get("code") == criterion.code
        system_matches = criterion.system is None or coding.get("system") == criterion.system
        if code_matches and system_matches:
            return True
    return False


def lab_in_range(resource: dict[str, Any], criterion: LabCriterion) -> bool:
    value = resource.get("valueQuantity", {}).get("value")
    if value is None:
        return False
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False
    if criterion.unit:
        unit = resource.get("valueQuantity", {}).get("unit") or resource.get("valueQuantity", {}).get("code")
        if unit != criterion.unit:
            return False
    if criterion.min_value is not None and numeric_value < criterion.min_value:
        return False
    if criterion.max_value is not None and numeric_value > criterion.max_value:
        return False
    return True


def flatten_text(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            parts.append(flatten_text(child))
    elif isinstance(value, list):
        for child in value:
            parts.append(flatten_text(child))
    elif value is not None:
        parts.append(str(value))
    return " ".join(part for part in parts if part)


def resource_sort_key(resource: dict[str, Any]) -> tuple[str, str, str]:
    date = (
        resource.get("effectiveDateTime")
        or resource.get("recordedDate")
        or resource.get("issued")
        or resource.get("period", {}).get("start")
        or ""
    )
    return (date, resource.get("resourceType", ""), resource.get("id", ""))


def deterministic_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:12]}"
