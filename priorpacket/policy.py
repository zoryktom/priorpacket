from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PolicyError(ValueError):
    pass


def load_policy(path: str | Path) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError(f"Policy file is not valid JSON: {policy_path}") from exc

    required_keys = ["policy_id", "payer", "service", "criteria", "pathways"]
    missing = [key for key in required_keys if key not in policy]
    if missing:
        raise PolicyError(f"Policy is missing required keys: {', '.join(missing)}")

    criteria_ids = {criterion.get("id") for criterion in policy["criteria"]}
    if None in criteria_ids:
        raise PolicyError("Every criterion must include an id.")

    for pathway in policy["pathways"]:
        unknown = [
            criterion_id
            for criterion_id in pathway.get("requires", [])
            if criterion_id not in criteria_ids
        ]
        if unknown:
            raise PolicyError(
                f"Pathway {pathway.get('id', '<unknown>')} references unknown criteria: "
                + ", ".join(unknown)
            )

    return policy


def load_bundle(path: str | Path) -> dict[str, Any]:
    bundle_path = Path(path)
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError(f"FHIR bundle is not valid JSON: {bundle_path}") from exc

    if bundle.get("resourceType") != "Bundle":
        raise PolicyError("FHIR input must be a Bundle resource.")
    return bundle
