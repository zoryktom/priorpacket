"""Bundle indexing, de-duplication, patient attribution, and packet-level issues."""

from __future__ import annotations

import json
from typing import Any

from .fhir.helpers import parse_reference, subject_reference
from .models import Issue

# Resource types the engine reads as evidence or request context.
EVIDENCE_TYPES = frozenset(
    {
        "Patient",
        "ServiceRequest",
        "Condition",
        "Procedure",
        "Observation",
        "DocumentReference",
        "MedicationRequest",
        "DiagnosticReport",
    }
)
# Types that may legitimately appear in a packet but are not evidence inputs.
CONTEXT_TYPES = frozenset(
    {"Coverage", "Claim", "ClaimResponse", "Encounter", "Practitioner", "Organization", "Task"}
)
# Reference-bearing fields whose targets must resolve for evidence to be traceable.
INDIRECT_LINK_FIELDS = {
    "ServiceRequest": ("supportingInfo",),
    "DiagnosticReport": ("result",),
}


def resource_key(resource: dict[str, Any]) -> str:
    return f"{resource.get('resourceType', 'Resource')}/{resource.get('id', 'unknown')}"


def _canonical(resource: dict[str, Any]) -> str:
    return json.dumps(resource, sort_keys=True, separators=(",", ":"))


class BundleContext:
    """Deterministic, de-duplicated view of a structurally valid Bundle."""

    def __init__(self, bundle: dict[str, Any]):
        self.issues: list[Issue] = []
        self.id_conflicts: set[int] = set()
        self.resources: list[dict[str, Any]] = []
        self._full_urls: dict[str, dict[str, Any]] = {}
        self._build(bundle)
        self._index_references()

    def _build(self, bundle: dict[str, Any]) -> None:
        raw: list[dict[str, Any]] = []
        for entry in bundle.get("entry", []):
            resource = entry["resource"]
            raw.append(resource)
            full_url = entry.get("fullUrl")
            if isinstance(full_url, str):
                self._full_urls[full_url] = resource

        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for resource in raw:
            resource_type = resource["resourceType"]
            resource_id = resource.get("id")
            if not isinstance(resource_id, str) or not resource_id.strip():
                self.issues.append(
                    Issue(
                        "MISSING_RESOURCE_ID",
                        "warning",
                        f"A {resource_type} resource has no id and cannot be cited as evidence.",
                        resource=f"{resource_type}/(no id)",
                        path=f"{resource_type}.id",
                    )
                )
            groups.setdefault((resource_type, str(resource_id or "")), []).append(resource)

        for (resource_type, resource_id), members in sorted(groups.items()):
            distinct = {_canonical(member): member for member in members}
            ordered = [distinct[key] for key in sorted(distinct)]
            if resource_id and len(members) > 1:
                if len(ordered) == 1:
                    self.issues.append(
                        Issue(
                            "DUPLICATE_RESOURCE",
                            "warning",
                            f"{resource_type}/{resource_id} appears {len(members)} times with identical content; counted once.",
                            resource=f"{resource_type}/{resource_id}",
                        )
                    )
                else:
                    self.issues.append(
                        Issue(
                            "DUPLICATE_ID_CONFLICT",
                            "error" if resource_type in EVIDENCE_TYPES else "warning",
                            f"{resource_type}/{resource_id} appears with {len(ordered)} different contents; the conflict is preserved, not resolved.",
                            resource=f"{resource_type}/{resource_id}",
                        )
                    )
                    self.id_conflicts.update(id(member) for member in ordered)
            self.resources.extend(ordered)

        for resource in self.resources:
            resource_type = resource["resourceType"]
            if resource_type not in EVIDENCE_TYPES and resource_type not in CONTEXT_TYPES:
                self.issues.append(
                    Issue(
                        "UNSUPPORTED_RESOURCE_TYPE",
                        "warning",
                        f"Resource type {resource_type} is not read by this engine and was ignored.",
                        resource=resource_key(resource),
                    )
                )

    def _index_references(self) -> None:
        self._by_key = {
            (r["resourceType"], str(r.get("id"))): r for r in self.resources if r.get("id")
        }
        self.patients = [r for r in self.resources if r["resourceType"] == "Patient"]
        self.indirect_source: dict[int, str] = {}

    def by_type(self, resource_type: str) -> list[dict[str, Any]]:
        return [r for r in self.resources if r["resourceType"] == resource_type]

    def resolve(self, reference: Any) -> dict[str, Any] | None:
        if isinstance(reference, dict):
            reference = reference.get("reference")
        resource_type, resource_id = parse_reference(reference)
        if resource_type is None and isinstance(resource_id, str) and resource_id.startswith("urn:"):
            return self._full_urls.get(resource_id)
        if resource_type and resource_id:
            return self._by_key.get((resource_type, resource_id))
        return None

    def select_patient_id(self, service_request: dict[str, Any] | None) -> str | None:
        if service_request is not None:
            resource_type, resource_id = parse_reference(subject_reference(service_request))
            if resource_type == "Patient" and resource_id:
                return resource_id
        if self.patients:
            return str(self.patients[0].get("id")) if self.patients[0].get("id") else None
        return None

    def link_indirect_evidence(self, patient_id: str | None) -> None:
        """Attribute subject-less resources that a patient-attributed resource points to."""
        for source in self.resources:
            fields = INDIRECT_LINK_FIELDS.get(source["resourceType"], ())
            if not fields:
                continue
            source_type, source_id = parse_reference(subject_reference(source))
            source_ok = source_type == "Patient" and source_id == patient_id
            for field_name in fields:
                links = source.get(field_name, [])
                for link in links if isinstance(links, list) else []:
                    target = self.resolve(link)
                    reference = link.get("reference") if isinstance(link, dict) else None
                    if target is None:
                        self.issues.append(
                            Issue(
                                "UNRESOLVED_REFERENCE",
                                "error",
                                f"{resource_key(source)}.{field_name} points to {reference!r}, which is not in the packet.",
                                resource=resource_key(source),
                                path=f"{source['resourceType']}.{field_name}",
                            )
                        )
                    elif source_ok and subject_reference(target) is None:
                        self.indirect_source[id(target)] = resource_key(source)

    def check_subject_references(self) -> None:
        for resource in self.resources:
            if resource["resourceType"] in {"Patient"}:
                continue
            reference = subject_reference(resource)
            if reference is None:
                continue
            resource_type, _ = parse_reference(reference)
            if resource_type == "Patient" and self.resolve(reference) is None:
                self.issues.append(
                    Issue(
                        "UNRESOLVED_REFERENCE",
                        "error",
                        f"{resource_key(resource)} refers to {reference!r}, which is not in the packet.",
                        resource=resource_key(resource),
                        path=f"{resource['resourceType']}.subject",
                    )
                )

    def attribution(self, resource: dict[str, Any], patient_id: str | None) -> tuple[str, str | None]:
        """Return (state, note): state is verified, indirect, unattributed, or wrong_patient."""
        reference = subject_reference(resource)
        if reference is not None:
            resource_type, resource_id = parse_reference(reference)
            if resource_type == "Patient" and resource_id == patient_id:
                return "verified", None
            return "wrong_patient", f"subject is {reference!r}, expected Patient/{patient_id}"
        via = self.indirect_source.get(id(resource))
        if via:
            return "indirect", f"attributed through {via}"
        return "unattributed", "resource has no subject reference"


def structural_issues(bundle: Any) -> list[Issue]:
    """Fatal structure problems; any result means the input cannot be evaluated reliably."""
    if not isinstance(bundle, dict):
        return [Issue("NOT_A_BUNDLE", "error", "Input must be a JSON object containing a FHIR Bundle.")]
    issues: list[Issue] = []
    if bundle.get("resourceType") != "Bundle":
        issues.append(
            Issue("NOT_A_BUNDLE", "error", "resourceType must be 'Bundle'.", path="Bundle.resourceType")
        )
        return issues
    entries = bundle.get("entry")
    if not isinstance(entries, list):
        return [Issue("MALFORMED_BUNDLE", "error", "Bundle.entry must be a list.", path="Bundle.entry")]
    if not entries:
        return [Issue("EMPTY_BUNDLE", "error", "Bundle contains no entries.", path="Bundle.entry")]
    for index, entry in enumerate(entries):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        path = f"Bundle.entry[{index}].resource"
        if not isinstance(resource, dict):
            issues.append(Issue("MALFORMED_RESOURCE", "error", f"{path} must be an object.", path=path))
        elif not isinstance(resource.get("resourceType"), str) or not resource["resourceType"]:
            issues.append(
                Issue("MALFORMED_RESOURCE", "error", f"{path}.resourceType must be a string.", path=path)
            )
        elif "id" in resource and not isinstance(resource["id"], str):
            issues.append(
                Issue("MALFORMED_RESOURCE", "error", f"{path}.id must be a string.", path=f"{path}.id")
            )
    if not issues and not any(e["resource"]["resourceType"] == "Patient" for e in entries):
        issues.append(
            Issue(
                "MISSING_PATIENT",
                "error",
                "Bundle has no Patient resource; evidence cannot be attributed to a patient.",
                path="Bundle.entry",
            )
        )
    return issues
