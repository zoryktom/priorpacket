from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any


class PolicyError(ValueError):
    pass


SUPPORTED_CRITERION_KINDS = {"condition", "procedure", "observation", "document", "medication"}
SUPPORTED_OBSERVATION_OPERATORS = {">", ">=", "<", "<=", "=="}
SUPPORTED_SCHEMA_VERSIONS = {1}
POLICY_STATUSES = {"active", "inactive", "draft", "retired"}

_ICD10 = re.compile(r"^[A-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$")
_CPT = re.compile(r"^(\d{4}[0-9FTU])$")
_HCPCS = re.compile(r"^[A-Z]\d{4}$")
_LOINC = re.compile(r"^\d{1,7}-\d$")
_DIGITS = re.compile(r"^\d{1,18}$")

# Code systems this engine can validate code formats for. Format checks are syntactic
# only; they do not prove a code exists in the current release of the terminology.
KNOWN_CODE_SYSTEMS: dict[str, re.Pattern[str]] = {
    "http://hl7.org/fhir/sid/icd-10-cm": _ICD10,
    "http://www.ama-assn.org/go/cpt": _CPT,
    "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets": _HCPCS,
    "http://loinc.org": _LOINC,
    "http://www.nlm.nih.gov/research/umls/rxnorm": _DIGITS,
    "http://snomed.info/sct": _DIGITS,
}

TOP_LEVEL_KEYS = {
    "$schema",
    "policy_id",
    "payer",
    "service",
    "criteria",
    "pathways",
    "description",
    "schema_version",
    "policy_version",
    "status",
    "effective_start",
    "effective_end",
}
CRITERION_KEYS = {
    "id",
    "kind",
    "label",
    "description",
    "weight",
    "required",
    "codes",
    "code_systems",
    "keywords",
    "require_all_keywords",
    "conflict_keywords",
    "within_days",
    "operator",
    "value",
    "min_value",
    "max_value",
    "unit",
    "unit_aliases",
    "prerequisite",
    "met_rationale",
    "missing_rationale",
    "missing_action",
    "review_action",
}
PATHWAY_KEYS = {"id", "label", "requires", "description"}
SERVICE_KEYS = {"name", "codes", "description"}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_str_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_policy(policy: Any) -> list[str]:
    """Return actionable errors; an empty list means the policy can be evaluated reliably."""
    if not isinstance(policy, dict):
        return ["policy: must be a JSON object"]
    errors: list[str] = []
    required = ["policy_id", "payer", "service", "criteria", "pathways"]
    for key in required:
        if key not in policy:
            errors.append(f"{key}: required field is missing")
    for key in sorted(set(policy) - TOP_LEVEL_KEYS):
        errors.append(f"{key}: unknown policy field; unknown rules are never treated as satisfied")
    if any(key not in policy for key in required):
        return errors

    if not isinstance(policy["policy_id"], str) or not policy["policy_id"].strip():
        errors.append("policy_id: must be a non-empty string")
    if not isinstance(policy["payer"], str) or not policy["payer"].strip():
        errors.append("payer: must be a non-empty string")
    _validate_governance(policy, errors)
    _validate_service(policy["service"], errors)

    criteria = policy["criteria"]
    if not isinstance(criteria, list) or not criteria:
        errors.append("criteria: must be a non-empty list")
        criteria = []
    criteria_ids = _validate_criteria(criteria, errors)
    _validate_prerequisites(criteria, criteria_ids, errors)
    _validate_pathways(policy["pathways"], criteria, criteria_ids, errors)
    return errors


def policy_warnings(policy: dict[str, Any]) -> list[str]:
    """Non-fatal findings, such as criteria no pathway can reach."""
    warnings: list[str] = []
    criteria = policy.get("criteria")
    pathways = policy.get("pathways")
    if not isinstance(criteria, list) or not isinstance(pathways, list):
        return warnings
    used = {
        criterion_id
        for pathway in pathways
        if isinstance(pathway, dict) and isinstance(pathway.get("requires"), list)
        for criterion_id in pathway["requires"]
    }
    for index, criterion in enumerate(criteria):
        if isinstance(criterion, dict) and criterion.get("id") not in used:
            warnings.append(
                f"criteria[{index}].id: criterion '{criterion.get('id')}' is not required by any "
                "pathway and cannot affect the outcome"
            )
    seen: dict[tuple[str, ...], str] = {}
    for index, pathway in enumerate(pathways):
        if isinstance(pathway, dict) and isinstance(pathway.get("requires"), list):
            key = tuple(sorted(str(item) for item in pathway["requires"]))
            if key in seen:
                warnings.append(f"pathways[{index}]: duplicates the requirements of pathway '{seen[key]}'")
            else:
                seen[key] = str(pathway.get("id"))
    return warnings


def _validate_governance(policy: dict[str, Any], errors: list[str]) -> None:
    if "schema_version" in policy:
        version = policy["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            errors.append("schema_version: must be an integer")
        elif version not in SUPPORTED_SCHEMA_VERSIONS:
            errors.append(
                f"schema_version: {version} is not supported; supported versions: "
                f"{', '.join(str(v) for v in sorted(SUPPORTED_SCHEMA_VERSIONS))}"
            )
    if "policy_version" in policy and (
        not isinstance(policy["policy_version"], str) or not policy["policy_version"].strip()
    ):
        errors.append("policy_version: must be a non-empty string")
    if "status" in policy and policy["status"] not in POLICY_STATUSES:
        errors.append(f"status: must be one of {', '.join(sorted(POLICY_STATUSES))}")
    start = end = None
    for key in ("effective_start", "effective_end"):
        if key in policy:
            parsed = _parse_iso_date(policy[key])
            if parsed is None:
                errors.append(f"{key}: must be an ISO date (YYYY-MM-DD)")
            elif key == "effective_start":
                start = parsed
            else:
                end = parsed
    if start and end and start > end:
        errors.append("effective_start: must not be after effective_end")


def _validate_service(service: Any, errors: list[str]) -> None:
    if not isinstance(service, dict):
        errors.append("service: must be an object")
        return
    for key in sorted(set(service) - SERVICE_KEYS):
        errors.append(f"service.{key}: unknown field")
    if not isinstance(service.get("name"), str) or not service["name"].strip():
        errors.append("service.name: must be a non-empty string")
    codes = service.get("codes")
    if not _is_str_list(codes):
        errors.append("service.codes: must be a non-empty list of strings")
    elif len(set(codes)) != len(codes):
        errors.append("service.codes: contains duplicate codes")


def _validate_criteria(criteria: list[Any], errors: list[str]) -> set[str]:
    criteria_ids: set[str] = set()
    for index, criterion in enumerate(criteria):
        path = f"criteria[{index}]"
        if not isinstance(criterion, dict):
            errors.append(f"{path}: must be an object")
            continue
        for key in sorted(set(criterion) - CRITERION_KEYS):
            errors.append(f"{path}.{key}: unknown criterion field; it would be silently ignored")

        criterion_id = criterion.get("id")
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            errors.append(f"{path}.id: must be a non-empty string")
        elif criterion_id in criteria_ids:
            errors.append(f"{path}.id: duplicate criterion id '{criterion_id}'")
        else:
            criteria_ids.add(criterion_id)

        kind = criterion.get("kind")
        if kind not in SUPPORTED_CRITERION_KINDS:
            errors.append(f"{path}.kind: must be one of {', '.join(sorted(SUPPORTED_CRITERION_KINDS))}")
        weight = criterion.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
            errors.append(f"{path}.weight: must be a positive integer")
        for flag in ("required", "require_all_keywords"):
            if flag in criterion and not isinstance(criterion[flag], bool):
                errors.append(f"{path}.{flag}: must be true or false")

        codes = criterion.get("codes")
        keywords = criterion.get("keywords")
        if kind in {"condition", "procedure", "observation"} and not _is_str_list(codes):
            errors.append(f"{path}.codes: required for {kind} criteria")
        if kind == "medication" and not codes and not keywords:
            errors.append(f"{path}: medication criteria require codes or keywords")
        if kind == "document" and not _is_str_list(keywords):
            errors.append(f"{path}.keywords: required for document criteria")
        if codes is not None and not _is_str_list(codes):
            errors.append(f"{path}.codes: must be a non-empty list of strings")
        if keywords is not None and not _is_str_list(keywords):
            errors.append(f"{path}.keywords: must be a non-empty list of strings")
        if "conflict_keywords" in criterion and not _is_str_list(criterion["conflict_keywords"]):
            errors.append(f"{path}.conflict_keywords: must be a non-empty list of strings")

        _validate_code_systems(criterion, path, kind, codes, errors)

        if "within_days" in criterion:
            within_days = criterion["within_days"]
            if isinstance(within_days, bool) or not isinstance(within_days, int) or within_days <= 0:
                errors.append(f"{path}.within_days: must be a positive integer")

        _validate_value_rules(criterion, path, kind, errors)
    return criteria_ids


def _validate_code_systems(
    criterion: dict[str, Any], path: str, kind: Any, codes: Any, errors: list[str]
) -> None:
    if "code_systems" not in criterion:
        return
    systems = criterion["code_systems"]
    if not _is_str_list(systems):
        errors.append(f"{path}.code_systems: must be a non-empty list of code system URIs")
        return
    if kind == "document":
        errors.append(f"{path}.code_systems: not applicable to document criteria")
        return
    unknown = [system for system in systems if system not in KNOWN_CODE_SYSTEMS]
    for system in unknown:
        errors.append(
            f"{path}.code_systems: unsupported code system '{system}'; supported: "
            f"{', '.join(sorted(KNOWN_CODE_SYSTEMS))}"
        )
    if len(systems) == 1 and not unknown and _is_str_list(codes):
        pattern = KNOWN_CODE_SYSTEMS[systems[0]]
        for code in codes:
            if not pattern.match(code.upper()):
                errors.append(f"{path}.codes: '{code}' is not a valid code format for {systems[0]}")


def _validate_value_rules(criterion: dict[str, Any], path: str, kind: Any, errors: list[str]) -> None:
    value_fields = ("operator", "value", "min_value", "max_value", "unit", "unit_aliases")
    if kind != "observation":
        for field in value_fields:
            if field in criterion:
                errors.append(f"{path}.{field}: only supported on observation criteria")
        return

    operator = criterion.get("operator")
    if operator is not None and operator not in SUPPORTED_OBSERVATION_OPERATORS:
        errors.append(
            f"{path}.operator: must be one of {', '.join(sorted(SUPPORTED_OBSERVATION_OPERATORS))}"
        )
    if operator is not None and "value" not in criterion:
        errors.append(f"{path}.value: required when operator is set")
    if "value" in criterion and operator is None:
        errors.append(f"{path}.operator: required when value is set")
    for field in ("value", "min_value", "max_value"):
        if field in criterion and not _is_number(criterion[field]):
            errors.append(f"{path}.{field}: must be a finite number")
    if "unit" in criterion and (not isinstance(criterion["unit"], str) or not criterion["unit"].strip()):
        errors.append(f"{path}.unit: must be a non-empty string")
    if "unit_aliases" in criterion and "unit" not in criterion:
        errors.append(f"{path}.unit_aliases: requires unit")
    if "unit_aliases" in criterion and not _is_str_list(criterion["unit_aliases"]):
        errors.append(f"{path}.unit_aliases: must be a non-empty list of strings")

    numbers_ok = all(
        _is_number(criterion[field]) for field in ("value", "min_value", "max_value") if field in criterion
    )
    if numbers_ok and operator in {None, *SUPPORTED_OBSERVATION_OPERATORS} and _is_unsatisfiable(criterion):
        errors.append(f"{path}: value constraints can never be satisfied (contradictory range)")


def _is_unsatisfiable(criterion: dict[str, Any]) -> bool:
    low, low_strict = -math.inf, False
    high, high_strict = math.inf, False

    def tighten_low(bound: float, strict: bool) -> None:
        nonlocal low, low_strict
        if bound > low or (bound == low and strict):
            low, low_strict = bound, strict

    def tighten_high(bound: float, strict: bool) -> None:
        nonlocal high, high_strict
        if bound < high or (bound == high and strict):
            high, high_strict = bound, strict

    operator = criterion.get("operator")
    value = criterion.get("value")
    if value is None:
        operator = None
    if operator in {">", ">="}:
        tighten_low(value, operator == ">")
    elif operator in {"<", "<="}:
        tighten_high(value, operator == "<")
    elif operator == "==":
        tighten_low(value, False)
        tighten_high(value, False)
    if "min_value" in criterion:
        tighten_low(criterion["min_value"], False)
    if "max_value" in criterion:
        tighten_high(criterion["max_value"], False)
    return low > high or (low == high and (low_strict or high_strict))


def _validate_prerequisites(criteria: list[Any], criteria_ids: set[str], errors: list[str]) -> None:
    edges: dict[str, str] = {}
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict) or "prerequisite" not in criterion:
            continue
        path = f"criteria[{index}].prerequisite"
        target = criterion["prerequisite"]
        if not isinstance(target, str) or target not in criteria_ids:
            errors.append(f"{path}: unknown criterion id {target!r}")
        elif target == criterion.get("id"):
            errors.append(f"{path}: a criterion cannot be its own prerequisite")
        else:
            edges[str(criterion.get("id"))] = target
    for start in sorted(edges):
        seen = {start}
        node = edges.get(start)
        while node is not None:
            if node in seen:
                errors.append(f"criteria[{start}].prerequisite: circular prerequisite chain")
                break
            seen.add(node)
            node = edges.get(node)


def _validate_pathways(
    pathways: Any, criteria: list[Any], criteria_ids: set[str], errors: list[str]
) -> None:
    if not isinstance(pathways, list) or not pathways:
        errors.append("pathways: must be a non-empty list")
        return
    optional_ids = {
        c.get("id") for c in criteria if isinstance(c, dict) and c.get("required") is False
    }
    pathway_ids: set[str] = set()
    for index, pathway in enumerate(pathways):
        path = f"pathways[{index}]"
        if not isinstance(pathway, dict):
            errors.append(f"{path}: must be an object")
            continue
        for key in sorted(set(pathway) - PATHWAY_KEYS):
            errors.append(f"{path}.{key}: unknown pathway field")
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
        if len(set(map(str, requires))) != len(requires):
            errors.append(f"{path}.requires: contains duplicate criterion ids")
        for criterion_id in requires:
            if criterion_id not in criteria_ids:
                errors.append(f"{path}.requires: unknown criterion id '{criterion_id}'")
        if all(criterion_id in optional_ids for criterion_id in requires):
            errors.append(
                f"{path}.requires: pathway has no mandatory criterion and would always be satisfied"
            )


def validate_bundle(bundle: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        errors.append("resourceType: FHIR input must be a Bundle")
        return errors
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
