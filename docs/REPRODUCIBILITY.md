# Reproducibility

PriorPacket is built so evaluators can reproduce every shipped result from version-controlled synthetic inputs.

## Reproducible Inputs

- Policy packs are JSON files under `examples/policies/`.
- Synthetic FHIR Bundles are JSON files under `examples/cases/fhir/`.
- Expected outcomes are versioned in `examples/cases/manifest.json`.
- The policy-pack schema is stored in `schemas/policy-pack.schema.json`.

## Reproducible Commands

```bash
priorpacket validate-policy --policy examples/policies/knee_mri_policy.json

priorpacket validate-product \
  --manifest examples/cases/manifest.json \
  --out reports/validation

priorpacket batch-analyze \
  --policy examples/policies/knee_mri_policy.json \
  --bundles examples/cases/fhir \
  --service-code 73721 \
  --out reports/batch
```

## Reproducible Outputs

A single packet run writes:

- `result.json`
- `evidence_packet.md`
- `evidence_packet.html`
- `gap_task.fhir.json`
- `evidence_graph.json`
- `audit_manifest.json`

The audit manifest includes SHA-256 hashes for input and output files.

## Validation Metrics

`priorpacket validate-product` writes benchmark-style metrics:

- Overall pass count.
- Status accuracy.
- Risk-band accuracy.
- Score exact-match rate.
- Missing-criteria exact-match rate.
- Status confusion matrix.

The validation suite is intentionally synthetic. It is designed to verify system behavior without including protected health information.
