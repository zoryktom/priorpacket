from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PolicyError(ValueError):
    pass


SUPPORTED_CRITERION_KINDS = {"condition", "procedure", "observation", "document", "medication"}
SUPPORTED_OBSERVATION_OPERATORS = {">", ">=", "<", "<=", "=="}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_keys = ["policy_id", "payer", "service", "criteria", "pathways"]
    for key in required_keys:
        if key not in policy:
            errors.append(f"{key}: required field is missing")

    if errors:
        return errors

    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip():
        errors.append("policy_id: must be a non-empty string")
    if not isinstance(policy.get("payer"), str) or not policy["payer"].strip():
        errors.append("payer: must be a non-empty string")

    service = policy.get("service")
    if not isinstance(service, dict):
        errors.append("service: must be an object")
    else:
        if not isinstance(service.get("name"), str) or not service["name"].strip():
            errors.append("service.name: must be a non-empty string")
        codes = service.get("codes")
        if not isinstance(codes, list) or not codes or not all(isinstance(code, str) for code in codes):
            errors.append("service.codes: must be a non-empty list of strings")

    criteria = policy.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        errors.append("criteria: must be a non-empty list")
        criteria = []

    criteria_ids: set[str] = set()
    for index, criterion in enumerate(criteria):
        path = f"criteria[{index}]"
        if not isinstance(criterion, dict):
            errors.append(f"{path}: must be an object")
            continue

        criterion_id = criterion.get("id")
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            errors.append(f"{path}.id: must be a non-empty string")
        elif criterion_id in criteria_ids:
            errors.append(f"{path}.id: duplicate criterion id '{criterion_id}'")
        else:
            criteria_ids.add(criterion_id)

        kind = criterion.get("kind")
        if kind not in SUPPORTED_CRITERION_KINDS:
            errors.append(
                f"{path}.kind: must be one of {', '.join(sorted(SUPPORTED_CRITERION_KINDS))}"
            )

        weight = criterion.get("weight")
        if not isinstance(weight, int) or weight <= 0:
            errors.append(f"{path}.weight: must be a positive integer")

        codes = criterion.get("codes")
        keywords = criterion.get("keywords")
        if kind in {"condition", "procedure", "observation"}:
            if not isinstance(codes, list) or not codes or not all(isinstance(code, str) for code in codes):
                errors.append(f"{path}.codes: required for {kind} criteria")
        if kind == "medication" and not codes and not keywords:
            errors.append(f"{path}: medication criteria require codes or keywords")
        if kind == "document":
            if not isinstance(keywords, list) or not keywords or not all(
                isinstance(keyword, str) for keyword in keywords
            ):
                errors.append(f"{path}.keywords: required for document criteria")

        if "within_days" in criterion:
            within_days = criterion["within_days"]
            if not isinstance(within_days, int) or within_days <= 0:
                errors.append(f"{path}.within_days: must be a positive integer")

        if kind == "observation":
            operator = criterion.get("operator")
            if operator is not None and operator not in SUPPORTED_OBSERVATION_OPERATORS:
                errors.append(
                    f"{path}.operator: must be one of {', '.join(sorted(SUPPORTED_OBSERVATION_OPERATORS))}"
                )
            if operator is not None and "value" not in criterion:
                errors.append(f"{path}.value: required when operator is set")

    pathways = policy.get("pathways")
    if not isinstance(pathways, list) or not pathways:
        errors.append("pathways: must be a non-empty list")
        pathways = []

    pathway_ids: set[str] = set()
    for index, pathway in enumerate(pathways):
        path = f"pathways[{index}]"
        if not isinstance(pathway, dict):
            errors.append(f"{path}: must be an object")
            continue

        pathway_id = pathway.get("id")
        if not isinstance(pathway_id, str) or not pathway_id.strip():
            errors.append(f"{path}.id: must be a non-empty string")
        elif pathway_id in pathway_ids:
            errors.append(f"{path}.id: duplicate pathway id '{pathway_id}'")
        else:
            pathway_ids.add(pathway_id)

        requires = pathway.get("requires")
        if not isinstance(requires, list) or not requires:
            errors.append(f"{path}.requires: must be a non-empty list")
            continue
        for criterion_id in requires:
            if criterion_id not in criteria_ids:
                errors.append(f"{path}.requires: unknown criterion id '{criterion_id}'")

    return errors


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if bundle.get("resourceType") != "Bundle":
        errors.append("resourceType: FHIR input must be a Bundle")
    entries = bundle.get("entry")
    if not isinstance(entries, list):
        errors.append("entry: must be a list")
        return errors
    for index, entry in enumerate(entries):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            errors.append(f"entry[{index}].resource: must be an object")
            continue
        if not isinstance(resource.get("resourceType"), str):
            errors.append(f"entry[{index}].resource.resourceType: must be a string")
    return errors


def load_policy(path: str | Path) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError(f"Policy file is not valid JSON: {policy_path}") from exc

    errors = validate_policy(policy)
    if errors:
        raise PolicyError("Policy validation failed:\n- " + "\n- ".join(errors))

    return policy


def load_bundle(path: str | Path) -> dict[str, Any]:
    bundle_path = Path(path)
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError(f"FHIR bundle is not valid JSON: {bundle_path}") from exc

    errors = validate_bundle(bundle)
    if errors:
        raise PolicyError("FHIR bundle validation failed:\n- " + "\n- ".join(errors))
    return bundle
