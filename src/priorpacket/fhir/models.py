from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PAS_CLAIM_PROFILE = "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim"
PAS_REQUEST_BUNDLE_PROFILE = (
    "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-request-bundle"
)


def _prune_empty(value: Any) -> Any:
    if isinstance(value, dict):
        pruned = {key: _prune_empty(child) for key, child in value.items()}
        return {
            key: child
            for key, child in pruned.items()
            if child is not None and child != [] and child != {}
        }
    if isinstance(value, list):
        return [
            child
            for child in (_prune_empty(child) for child in value)
            if child is not None and child != [] and child != {}
        ]
    return value


class FHIRModel(BaseModel):
    """Base model that accepts additional implementation-guide fields."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )

    def fhir_dump(self) -> dict[str, Any]:
        return _prune_empty(self.model_dump(by_alias=True, exclude_none=True))


class Meta(FHIRModel):
    profile: list[str] = Field(default_factory=list)
    tag: list["Coding"] = Field(default_factory=list)


class Identifier(FHIRModel):
    system: str | None = None
    value: str
    type: "CodeableConcept | None" = None


class Coding(FHIRModel):
    system: str | None = None
    code: str
    display: str | None = None


class CodeableConcept(FHIRModel):
    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None

    def codes(self) -> set[tuple[str | None, str]]:
        return {(coding.system, coding.code) for coding in self.coding}


class Reference(FHIRModel):
    reference: str
    display: str | None = None


class HumanName(FHIRModel):
    family: str | None = None
    given: list[str] = Field(default_factory=list)
    text: str | None = None


class Quantity(FHIRModel):
    value: float
    unit: str | None = None
    system: str | None = "http://unitsofmeasure.org"
    code: str | None = None


class Period(FHIRModel):
    start: str | None = None
    end: str | None = None


class Annotation(FHIRModel):
    authorString: str | None = None
    time: str | None = None
    text: str


class Extension(FHIRModel):
    url: str
    valueString: str | None = None
    valueCode: str | None = None
    valueBoolean: bool | None = None
    valueDecimal: float | None = None
    valueInteger: int | None = None
    valueDateTime: str | None = None
    valueReference: Reference | None = None
    valueCodeableConcept: CodeableConcept | None = None
    valueQuantity: Quantity | None = None


class Resource(FHIRModel):
    id: str
    meta: Meta | None = None
    extension: list[Extension] = Field(default_factory=list)


class Patient(Resource):
    resource_type: Literal["Patient"] = Field("Patient", alias="resourceType")
    identifier: list[Identifier] = Field(default_factory=list)
    name: list[HumanName] = Field(default_factory=list)
    gender: str | None = None
    birthDate: str | None = None


class Coverage(Resource):
    resource_type: Literal["Coverage"] = Field("Coverage", alias="resourceType")
    status: str = "active"
    beneficiary: Reference
    payor: list[Reference] = Field(default_factory=list)
    subscriberId: str | None = None
    relationship: CodeableConcept | None = None


class Condition(Resource):
    resource_type: Literal["Condition"] = Field("Condition", alias="resourceType")
    clinicalStatus: CodeableConcept | None = None
    verificationStatus: CodeableConcept | None = None
    category: list[CodeableConcept] = Field(default_factory=list)
    code: CodeableConcept
    subject: Reference
    encounter: Reference | None = None
    onsetDateTime: str | None = None
    recordedDate: str | None = None


class Observation(Resource):
    resource_type: Literal["Observation"] = Field("Observation", alias="resourceType")
    status: str = "final"
    category: list[CodeableConcept] = Field(default_factory=list)
    code: CodeableConcept
    subject: Reference
    encounter: Reference | None = None
    effectiveDateTime: str | None = None
    issued: str | None = None
    valueQuantity: Quantity | None = None
    valueString: str | None = None
    valueCodeableConcept: CodeableConcept | None = None
    interpretation: list[CodeableConcept] = Field(default_factory=list)
    note: list[Annotation] = Field(default_factory=list)


class Encounter(Resource):
    resource_type: Literal["Encounter"] = Field("Encounter", alias="resourceType")
    status: str = "finished"
    class_fhir: Coding | None = Field(default=None, alias="class")
    type: list[CodeableConcept] = Field(default_factory=list)
    subject: Reference
    period: Period | None = None
    reasonCode: list[CodeableConcept] = Field(default_factory=list)
    diagnosis: list[dict[str, Any]] = Field(default_factory=list)
    note: list[Annotation] = Field(default_factory=list)


class ClaimDiagnosis(FHIRModel):
    sequence: int
    diagnosisCodeableConcept: CodeableConcept
    type: list[CodeableConcept] = Field(default_factory=list)


class ClaimSupportingInfo(FHIRModel):
    sequence: int
    category: CodeableConcept
    code: CodeableConcept | None = None
    timingDate: str | None = None
    valueString: str | None = None
    valueQuantity: Quantity | None = None
    valueReference: Reference | None = None
    reason: CodeableConcept | None = None


class ClaimItem(FHIRModel):
    sequence: int
    productOrService: CodeableConcept
    modifier: list[CodeableConcept] = Field(default_factory=list)
    servicedDate: str | None = None
    quantity: Quantity | None = None
    encounter: list[Reference] = Field(default_factory=list)


class ClaimInsurance(FHIRModel):
    sequence: int
    focal: bool = True
    coverage: Reference
    preAuthRef: list[str] = Field(default_factory=list)


class Claim(Resource):
    resource_type: Literal["Claim"] = Field("Claim", alias="resourceType")
    meta: Meta = Field(default_factory=lambda: Meta(profile=[PAS_CLAIM_PROFILE]))
    status: str = "active"
    type: CodeableConcept = Field(
        default_factory=lambda: codeable_concept(
            "http://terminology.hl7.org/CodeSystem/claim-type", "professional"
        )
    )
    use: Literal["claim", "preauthorization", "predetermination"] = "preauthorization"
    patient: Reference
    created: str
    provider: Reference | None = None
    insurer: Reference | None = None
    priority: CodeableConcept = Field(
        default_factory=lambda: codeable_concept(
            "http://terminology.hl7.org/CodeSystem/processpriority", "normal"
        )
    )
    diagnosis: list[ClaimDiagnosis] = Field(default_factory=list)
    supportingInfo: list[ClaimSupportingInfo] = Field(default_factory=list)
    insurance: list[ClaimInsurance] = Field(default_factory=list)
    item: list[ClaimItem] = Field(default_factory=list)


class ClaimResponseError(FHIRModel):
    itemSequence: int | None = None
    detailSequence: int | None = None
    subDetailSequence: int | None = None
    code: CodeableConcept


class ClaimResponse(Resource):
    resource_type: Literal["ClaimResponse"] = Field("ClaimResponse", alias="resourceType")
    status: str = "active"
    type: CodeableConcept = Field(
        default_factory=lambda: codeable_concept(
            "http://terminology.hl7.org/CodeSystem/claim-type", "professional"
        )
    )
    use: Literal["claim", "preauthorization", "predetermination"] = "preauthorization"
    patient: Reference
    created: str
    insurer: Reference | None = None
    requestor: Reference | None = None
    request: Reference | None = None
    outcome: str = "complete"
    disposition: str | None = None
    preAuthRef: str | None = None
    error: list[ClaimResponseError] = Field(default_factory=list)


class BundleEntry(FHIRModel):
    fullUrl: str | None = None
    resource: dict[str, Any]


class Bundle(Resource):
    resource_type: Literal["Bundle"] = Field("Bundle", alias="resourceType")
    meta: Meta = Field(default_factory=lambda: Meta(profile=[PAS_REQUEST_BUNDLE_PROFILE]))
    type: Literal[
        "document",
        "message",
        "transaction",
        "transaction-response",
        "batch",
        "batch-response",
        "history",
        "searchset",
        "collection",
    ] = "collection"
    timestamp: str | None = None
    entry: list[BundleEntry] = Field(default_factory=list)


def codeable_concept(
    system: str | None,
    code: str,
    display: str | None = None,
    text: str | None = None,
) -> CodeableConcept:
    return CodeableConcept(coding=[Coding(system=system, code=code, display=display)], text=text)


def make_reference(resource: Resource | dict[str, Any], display: str | None = None) -> Reference:
    resource_type = (
        getattr(resource, "resource_type", None)
        if not isinstance(resource, dict)
        else resource.get("resourceType")
    )
    resource_id = getattr(resource, "id", None) if not isinstance(resource, dict) else resource.get("id")
    if not resource_type or not resource_id:
        raise ValueError("FHIR references require resourceType and id")
    return Reference(reference=f"{resource_type}/{resource_id}", display=display)
