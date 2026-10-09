from __future__ import annotations

from datetime import date, datetime
from typing import Any

from priorpacket.models import PatientSummary


def bundle_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry.get("resource", {}) for entry in bundle.get("entry", [])]


def resources_by_type(bundle: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    return [
        resource
        for resource in bundle_entries(bundle)
        if resource.get("resourceType") == resource_type
    ]


def summarize_patient(bundle: dict[str, Any]) -> PatientSummary:
    patients = resources_by_type(bundle, "Patient")
    if not patients:
        return PatientSummary(
            patient_id="unknown",
            display="Unknown synthetic patient",
            birth_date=None,
            sex=None,
        )

    patient = patients[0]
    names = patient.get("name", [])
    display = patient.get("id", "synthetic-patient")
    if names:
        first = names[0]
        given = " ".join(first.get("given", []))
        family = first.get("family", "")
        display = " ".join(part for part in [given, family] if part).strip() or display

    return PatientSummary(
        patient_id=patient.get("id", "unknown"),
        display=display,
        birth_date=patient.get("birthDate"),
        sex=patient.get("gender"),
    )


def coding_values(resource: dict[str, Any], *paths: str) -> set[str]:
    values: set[str] = set()
    for path in paths:
        node: Any = resource
        for part in path.split("."):
            if isinstance(node, dict):
                node = node.get(part)
            else:
                node = None
                break
        if isinstance(node, dict):
            for coding in node.get("coding", []):
                code = coding.get("code")
                if code:
                    values.add(str(code).upper())
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    for coding in item.get("coding", []):
                        code = coding.get("code")
                        if code:
                            values.add(str(code).upper())
    return values


def code_display(resource: dict[str, Any], path: str = "code") -> str:
    node: Any = resource
    for part in path.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return resource.get("id", "unknown")
    if not isinstance(node, dict):
        return resource.get("id", "unknown")
    if node.get("text"):
        return str(node["text"])
    coding = node.get("coding", [])
    if coding:
        return str(coding[0].get("display") or coding[0].get("code") or resource.get("id"))
    return resource.get("id", "unknown")


def resource_date(resource: dict[str, Any]) -> str | None:
    date_fields = [
        "effectiveDateTime",
        "authoredOn",
        "performedDateTime",
        "occurrenceDateTime",
        "date",
        "created",
        "recordedDate",
        "onsetDateTime",
    ]
    for field in date_fields:
        value = resource.get(field)
        if isinstance(value, str):
            return value[:10]
    period = resource.get("performedPeriod") or resource.get("effectivePeriod")
    if isinstance(period, dict) and isinstance(period.get("start"), str):
        return period["start"][:10]
    return None


def days_between(later: str | None, earlier: str | None) -> int | None:
    if not later or not earlier:
        return None
    try:
        later_date = date.fromisoformat(later[:10])
        earlier_date = date.fromisoformat(earlier[:10])
    except ValueError:
        return None
    return (later_date - earlier_date).days


def today_iso() -> str:
    return datetime.utcnow().date().isoformat()


def text_blob(resource: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ["description", "title", "status", "intent"]:
        value = resource.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ["type", "category", "code", "medicationCodeableConcept"]:
        node = resource.get(key)
        if isinstance(node, dict):
            if node.get("text"):
                parts.append(str(node["text"]))
            for coding in node.get("coding", []):
                parts.extend(
                    str(coding.get(field))
                    for field in ["code", "display"]
                    if coding.get(field)
                )
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    if item.get("text"):
                        parts.append(str(item["text"]))
                    for coding in item.get("coding", []):
                        parts.extend(
                            str(coding.get(field))
                            for field in ["code", "display"]
                            if coding.get(field)
                        )
    note = resource.get("note", [])
    if isinstance(note, list):
        for item in note:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
    return " ".join(parts).lower()
