from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from priorpacket.models import PatientSummary


def bundle_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return []
    return [
        entry["resource"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
    ]


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
    return datetime.now(timezone.utc).date().isoformat()


@dataclass(frozen=True)
class DateInfo:
    """Outcome of reading a resource's clinical date.

    ``status`` is one of ``ok``, ``missing``, ``ambiguous`` (present but not a full
    calendar date) or ``conflicting`` (two fields for the same event disagree).
    """

    value: str | None
    status: str
    detail: str = ""


_DATE_FIELDS = (
    "effectiveDateTime",
    "authoredOn",
    "performedDateTime",
    "occurrenceDateTime",
    "date",
    "created",
    "recordedDate",
    "onsetDateTime",
)
_PERIOD_FIELDS = ("performedPeriod", "effectivePeriod")
_SAME_EVENT_FIELDS = (
    ("effectiveDateTime", "effectivePeriod.start"),
    ("performedDateTime", "performedPeriod.start"),
)


def parse_day(value: Any) -> date | None:
    """Parse a full FHIR date or dateTime to a calendar day; partial dates return None."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    if len(value) > 10 and value[10] != "T":
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def resource_date_info(resource: dict[str, Any]) -> DateInfo:
    found: list[tuple[str, Any]] = []
    for field_name in _DATE_FIELDS:
        if resource.get(field_name) is not None:
            found.append((field_name, resource[field_name]))
    for period_name in _PERIOD_FIELDS:
        period = resource.get(period_name)
        if isinstance(period, dict) and period.get("start") is not None:
            found.append((f"{period_name}.start", period["start"]))
    if not found:
        return DateInfo(None, "missing", "no date or timestamp present")

    by_name = dict(found)
    for first, second in _SAME_EVENT_FIELDS:
        if first in by_name and second in by_name:
            left, right = parse_day(by_name[first]), parse_day(by_name[second])
            if left and right and left != right:
                return DateInfo(
                    None,
                    "conflicting",
                    f"{first}={left.isoformat()} disagrees with {second}={right.isoformat()}",
                )

    name, raw = found[0]
    parsed = parse_day(raw)
    if parsed is None:
        return DateInfo(None, "ambiguous", f"{name}={raw!r} is not a complete calendar date")
    return DateInfo(parsed.isoformat(), "ok", name)


def parse_reference(reference: Any) -> tuple[str | None, str | None]:
    """Split a FHIR reference into (resource type, id); urn references return (None, urn)."""
    if not isinstance(reference, str) or not reference.strip() or reference.startswith("#"):
        return None, None
    if reference.startswith("urn:"):
        return None, reference
    parts = reference.split("?")[0].split("/")
    if "_history" in parts:
        parts = parts[: parts.index("_history")]
    if len(parts) >= 2 and parts[-1]:
        return parts[-2], parts[-1]
    return None, reference


def subject_reference(resource: dict[str, Any]) -> str | None:
    for key in ("subject", "patient", "beneficiary"):
        node = resource.get(key)
        if isinstance(node, dict) and isinstance(node.get("reference"), str):
            return node["reference"]
    return None


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
