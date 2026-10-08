# Evidence Graph

PriorPacket emits a machine-readable evidence graph for each analyzed packet.

The graph answers:

- Which policy was evaluated?
- Which pathway was selected?
- Which criteria were required?
- Which FHIR resources supported each met criterion?
- Which criteria require staff action?

## Output

Run:

```bash
priorpacket analyze \
  --policy examples/policies/knee_mri_policy.json \
  --bundle examples/fhir/knee_mri_bundle.json \
  --service-code 73721 \
  --out demo-output
```

Open:

```text
demo-output/evidence_graph.json
```

## Graph Schema

Top-level fields:

- `schema`: graph schema identifier.
- `request_id`: analyzed request identifier.
- `nodes`: request, patient, policy, service, pathway, criterion, FHIR resource, and missing-action nodes.
- `edges`: typed relationships between nodes.

Relationship examples:

- `for_patient`
- `evaluated_against`
- `requests_service`
- `best_pathway`
- `requires`
- `supported_by`
- `needs_action`

## Why It Matters

Evidence packets are useful for humans. Evidence graphs are useful for informatics review, downstream analytics, and integration testing.

The graph makes the reasoning path inspectable without relying on hidden model state or free-text-only explanations.
