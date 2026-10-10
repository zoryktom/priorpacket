from __future__ import annotations

from typing import Any

from .models import AnalysisResult


def build_evidence_graph(result: AnalysisResult) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()

    def add_node(node_id: str, node_type: str, label: str, **properties: Any) -> None:
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "label": label,
                "properties": properties,
            }
        )

    def add_edge(source: str, target: str, relationship: str, **properties: Any) -> None:
        edges.append(
            {
                "source": source,
                "target": target,
                "relationship": relationship,
                "properties": properties,
            }
        )

    request_id = f"request:{result.request_id}"
    patient_id = f"patient:{result.patient.patient_id}"
    policy_id = f"policy:{result.policy_id}"
    service_id = f"service:{result.service_code}"
    pathway_id = f"pathway:{result.best_pathway.pathway_id}"

    add_node(
        request_id,
        "request",
        result.request_id,
        status=result.status,
        outcome=result.outcome,
        policy_version=result.policy_version,
        risk_band=result.risk_band,
        score=result.score,
        max_score=result.max_score,
        score_percent=result.score_percent,
    )
    add_node(
        patient_id,
        "patient",
        result.patient.display,
        patient_id=result.patient.patient_id,
        birth_date=result.patient.birth_date,
        sex=result.patient.sex,
    )
    add_node(policy_id, "policy", result.policy_id, payer=result.payer)
    add_node(service_id, "service", result.service_name, service_code=result.service_code)
    add_node(
        pathway_id,
        "pathway",
        result.best_pathway.label,
        completion_rate=result.best_pathway.completion_rate,
    )

    add_edge(request_id, patient_id, "for_patient")
    add_edge(request_id, policy_id, "evaluated_against")
    add_edge(request_id, service_id, "requests_service")
    add_edge(request_id, pathway_id, "best_pathway")

    for criterion in result.criteria:
        criterion_id = f"criterion:{criterion.criterion_id}"
        add_node(
            criterion_id,
            "criterion",
            criterion.label,
            status=criterion.status,
            required=criterion.required,
            inference=criterion.inference,
            weight=criterion.weight,
            earned_weight=criterion.earned_weight,
            rationale=criterion.rationale,
        )
        if criterion.criterion_id in result.best_pathway.required_criteria:
            add_edge(pathway_id, criterion_id, "requires")
        else:
            add_edge(policy_id, criterion_id, "defines_alternative_criterion")

        for hit in criterion.evidence:
            resource_id = f"fhir:{hit.resource_type}/{hit.resource_id}"
            add_node(
                resource_id,
                "fhir_resource",
                f"{hit.resource_type}/{hit.resource_id}",
                resource_type=hit.resource_type,
                resource_id=hit.resource_id,
                display=hit.label,
                detail=hit.detail,
                date=hit.date,
            )
            add_edge(
                criterion_id,
                resource_id,
                "supported_by",
                detail=hit.detail,
                date=hit.date,
                selection_reason=hit.selection_reason,
                attribution=hit.attribution,
                provenance="observed",
            )

        for rejected in criterion.rejected:
            resource_id = f"fhir:{rejected.resource_type}/{rejected.resource_id}"
            add_node(
                resource_id,
                "fhir_resource",
                f"{rejected.resource_type}/{rejected.resource_id}",
                resource_type=rejected.resource_type,
                resource_id=rejected.resource_id,
            )
            add_edge(
                criterion_id,
                resource_id,
                "rejected_resource",
                reason=rejected.reason_code,
                detail=rejected.detail,
                provenance="observed",
            )

        if not criterion.evidence and criterion.status != "met":
            absence_id = f"absence:{criterion.criterion_id}"
            add_node(
                absence_id,
                "evidence_absence",
                f"No qualifying evidence for {criterion.label}",
                note="Absence from the packet is not proof the event did not occur.",
            )
            add_edge(criterion_id, absence_id, "lacks_evidence", provenance="inferred")

        if criterion.missing_action:
            action_id = f"action:{criterion.criterion_id}"
            add_node(action_id, "missing_action", criterion.missing_action)
            add_edge(criterion_id, action_id, "needs_action")

    for index, issue in enumerate(result.issues):
        if issue.severity not in {"error", "warning"}:
            continue
        issue_id = f"issue:{index}:{issue.code}"
        add_node(issue_id, "issue", issue.code, severity=issue.severity, message=issue.message)
        add_edge(request_id, issue_id, "has_issue")

    return {
        "schema": "priorpacket.evidence_graph.v1",
        "request_id": result.request_id,
        "nodes": nodes,
        "edges": edges,
    }
