"""Layered FHIR/PAS validation.

This is a lightweight, dependency-free check. It is NOT a substitute for the official HL7
FHIR validator with the Da Vinci PAS implementation guide loaded; it covers only the layers
named below and reports which layers were not checked.
"""
from __future__ import annotations

import re
from typing import Any

from .context import structural_issues
from .fhir.helpers import parse_reference
from .fhir.models import PAS_CLAIM_PROFILE, PAS_REQUEST_BUNDLE_PROFILE
from .policy import KNOWN_CODE_SYSTEMS

_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
_UUID_URN = re.compile(r"^urn:uuid:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

NOT_CHECKED = [
    "full FHIR R4 schema/cardinality validation",
    "binding validation against complete terminology releases",
    "PAS profile invariants and slicing",
    "digital signatures and security labels",
]


def _finding(layer: str, severity: str, code: str, message: str, path: str | None = None) -> dict[str, Any]:
    return {"layer": layer, "severity": severity, "code": code, "message": message, "path": path}


def validate_fhir_bundle(bundle: Any, *, expect_pas: bool = False) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for issue in structural_issues(bundle):
        findings.append(_finding("structural", "error", issue.code, issue.message, issue.path))
    if findings:
        return _report(findings)

    entries = bundle["entry"]
    ids: dict[tuple[str, str], int] = {}
    full_urls: set[str] = set()
    for index, entry in enumerate(entries):
        resource = entry["resource"]
        path = f"Bundle.entry[{index}].resource"
        resource_type = resource["resourceType"]
        resource_id = resource.get("id")
        if resource_id is None:
            findings.append(_finding("structural", "warning", "MISSING_ID", f"{resource_type} has no id.", path))
        elif not _ID.match(resource_id):
            findings.append(_finding("structural", "error", "INVALID_ID", f"id {resource_id!r} violates the FHIR id format.", path))
        else:
            key = (resource_type, resource_id)
            if key in ids:
                findings.append(_finding("structural", "error", "DUPLICATE_ID", f"{resource_type}/{resource_id} appears more than once.", path))
            ids[key] = index
        full_url = entry.get("fullUrl")
        if isinstance(full_url, str):
            full_urls.add(full_url)
            if full_url.startswith("urn:uuid:") and not _UUID_URN.match(full_url):
                findings.append(_finding("structural", "error", "INVALID_UUID_URN", f"fullUrl {full_url!r} is not a valid urn:uuid.", f"Bundle.entry[{index}].fullUrl"))

    for index, entry in enumerate(entries):
        resource = entry["resource"]
        for field_path, reference in _references(resource):
            resource_type, resource_id = parse_reference(reference)
            if resource_type is None and isinstance(reference, str) and reference.startswith("urn:"):
                ok = reference in full_urls
            else:
                ok = (resource_type, resource_id) in ids
            if not ok:
                findings.append(_finding("structural", "error", "UNRESOLVED_REFERENCE", f"{reference!r} is not in the bundle.", f"Bundle.entry[{index}].resource.{field_path}"))

    if expect_pas:
        profiles = bundle.get("meta", {}).get("profile", []) if isinstance(bundle.get("meta"), dict) else []
        if PAS_REQUEST_BUNDLE_PROFILE not in profiles:
            findings.append(_finding("profile", "error", "MISSING_BUNDLE_PROFILE", "Bundle.meta.profile lacks the PAS request bundle profile.", "Bundle.meta.profile"))
        if bundle.get("type") != "collection":
            findings.append(_finding("profile", "warning", "UNEXPECTED_BUNDLE_TYPE", "PAS request bundles are expected to be type 'collection'.", "Bundle.type"))
        first = entries[0]["resource"]
        if first.get("resourceType") != "Claim":
            findings.append(_finding("profile", "error", "FIRST_ENTRY_NOT_CLAIM", "The first PAS entry must be the Claim.", "Bundle.entry[0]"))
        else:
            claim_profiles = first.get("meta", {}).get("profile", []) if isinstance(first.get("meta"), dict) else []
            if PAS_CLAIM_PROFILE not in claim_profiles:
                findings.append(_finding("profile", "error", "MISSING_CLAIM_PROFILE", "Claim.meta.profile lacks the PAS claim profile.", "Bundle.entry[0].resource.meta.profile"))
            if first.get("use") != "preauthorization":
                findings.append(_finding("semantics", "error", "CLAIM_USE", "Claim.use must be 'preauthorization'.", "Bundle.entry[0].resource.use"))

    for index, entry in enumerate(entries):
        for path, coding in _codings(entry["resource"], f"Bundle.entry[{index}].resource"):
            system, code = coding.get("system"), coding.get("code")
            pattern = KNOWN_CODE_SYSTEMS.get(system) if isinstance(system, str) else None
            if pattern is not None and isinstance(code, str) and not pattern.match(code.upper()):
                findings.append(_finding("terminology", "warning", "CODE_FORMAT", f"{code!r} does not look like a valid code for {system} (format check only).", path))
    return _report(findings)


def _report(findings: list[dict[str, Any]]) -> dict[str, Any]:
    findings = sorted(findings, key=lambda f: (f["layer"], f["code"], f["path"] or "", f["message"]))
    errors = [f for f in findings if f["severity"] == "error"]
    return {
        "valid": not errors,
        "errors": len(errors),
        "warnings": len(findings) - len(errors),
        "findings": findings,
        "not_checked": NOT_CHECKED,
    }


def _references(node: Any, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            if key == "reference" and isinstance(value, str) and not value.startswith("#"):
                found.append((child, value))
            else:
                found.extend(_references(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_references(value, f"{path}[{index}]"))
    return found


def _codings(node: Any, path: str) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        coding = node.get("coding")
        if isinstance(coding, list):
            for index, item in enumerate(coding):
                if isinstance(item, dict):
                    found.append((f"{path}.coding[{index}]", item))
        for key, value in node.items():
            if key != "coding":
                found.extend(_codings(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_codings(value, f"{path}[{index}]"))
    return found
