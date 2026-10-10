from __future__ import annotations

from typing import Any

from .models import AnalysisResult


def build_gap_task(result: AnalysisResult) -> dict[str, Any]:
    """Build a FHIR Task-like work item for evidence completion.

    This is an operational export for provider workflows. It is intentionally
    cautious and does not claim conformance to a full Da Vinci profile.
    """

    task_status = "ready" if result.outcome == "READY" else "requested"
    missing = "\n".join(f"- {action}" for action in result.missing_actions)
    if not missing:
        missing = "No missing evidence for the best pathway."

    return {
        "resourceType": "Task",
        "id": result.request_id,
        "status": task_status,
        "intent": "order",
        "priority": "routine" if result.risk_band == "low" else "urgent",
        "description": f"Prior authorization evidence review for {result.service_name}",
        "for": {"reference": f"Patient/{result.patient.patient_id}"},
        "businessStatus": {
            "text": f"{result.outcome}; denial risk {result.risk_band}; score {result.score_percent}%"
        },
        "code": {
            "coding": [
                {
                    "system": "https://github.com/zoryktom/priorpacket",
                    "code": "prior-auth-evidence-review",
                    "display": "Prior authorization evidence review",
                }
            ],
            "text": "Prior authorization evidence review",
        },
        "input": [
            {
                "type": {"text": "Payer policy"},
                "valueString": result.policy_id,
            },
            {
                "type": {"text": "Requested service code"},
                "valueString": result.service_code,
            },
            {
                "type": {"text": "Best pathway"},
                "valueString": result.best_pathway.label,
            },
        ],
        "output": [
            {
                "type": {"text": "Missing evidence checklist"},
                "valueString": missing,
            }
        ],
    }
