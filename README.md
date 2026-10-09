# PriorPacket

PriorPacket is a deterministic, local-first prior authorization evidence engine for FHIR workflows. It can check whether a prior authorization packet has the required proof before submission, generate review artifacts, and build Da Vinci PAS-oriented authorization bundles for research and validation.

The open-source core is auditable and uses synthetic examples only. It makes no external API calls.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Da Vinci PAS Packet Build

Build an oncology biologic authorization packet from synthetic longitudinal FHIR input:

```bash
priorpacket build \
  --patient examples/oncology_patient.json \
  --rule examples/oncology_policy_rule.json \
  --out work/oncology_packet.json
```

Audit the packet against the payer policy rule:

```bash
priorpacket audit work/oncology_packet.json \
  --policy examples/oncology_policy_rule.json
```

Successful audits return JSON with `status: "pass"` and `score: 100`. Incomplete packets include deterministic issue codes such as `MISSING_DIAGNOSIS`, `MISSING_PROCEDURE`, `MISSING_LAB`, `LAB_OUT_OF_RANGE`, `MISSING_TREATMENT`, and `MISSING_NOTE`.

## Readiness Analysis

Analyze a FHIR Bundle against a policy pack and requested service code:

```bash
priorpacket validate-policy --policy examples/policies/knee_mri_policy.json

priorpacket validate-product \
  --manifest examples/cases/manifest.json \
  --out reports/validation

priorpacket analyze \
  --policy examples/policies/knee_mri_policy.json \
  --bundle examples/fhir/knee_mri_bundle.json \
  --service-code 73721 \
  --out demo-output
```

Open `demo-output/evidence_packet.html` in a browser.

## Local Review Console

```bash
priorpacket serve
```

Open `http://127.0.0.1:8787`.

The console runs locally and loads the synthetic validation scenarios.

## Validation Suite

PriorPacket includes reproducible validation scenarios for imaging and oncology prior authorization workflows:

- Ready packet: knee MRI.
- Missing required x-ray proof.
- Missing prior treatment evidence.
- Ready packet: acute injury pathway.
- Wrong policy selected for requested service code.
- Oncology biologic PAS bundle success, incomplete evidence, approved response, and rejected response cases.

Expected result:

```text
pytest tests/
```

## Batch Audit

```bash
priorpacket batch-analyze \
  --policy examples/policies/knee_mri_policy.json \
  --bundles examples/cases/fhir \
  --service-code 73721 \
  --out reports/batch
```

This writes:

- `batch_results.json`
- `evidence_gap_report.csv`
- `batch_summary.md`

## Evidence Graph

Each packet run writes `evidence_graph.json`, a machine-readable graph linking the request, selected pathway, required criteria, supporting FHIR resources, and missing-proof actions.

## Research Artifact Scope

- FHIR R4 Pydantic models: `Patient`, `Coverage`, `Condition`, `Observation`, `Encounter`, `Claim`, `ClaimResponse`, and `Bundle`.
- Da Vinci PAS-oriented request bundles with PAS Claim profile metadata and supporting evidence references.
- Deterministic evidence selection for diagnosis, labs, failed treatment history, and physician notes.
- Contract verification and completeness scoring for diagnosis codes, service codes, lab ranges, prerequisite treatments, notes, and payer `ClaimResponse` outcomes.
- CLI pipeline for `priorpacket build` and `priorpacket audit`.

## Evaluation Docs

- [Health-system evaluation guide](docs/HEALTH_SYSTEM_EVALUATION.md)
- [Validation guide](docs/VALIDATION.md)
- [Reproducibility guide](docs/REPRODUCIBILITY.md)
- [Evidence graph](docs/EVIDENCE_GRAPH.md)
- [EHR integration path](docs/EHR_INTEGRATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Policy packs](docs/POLICY_PACKS.md)
- [Security](SECURITY.md)

## Standards

- [CMS Interoperability and Prior Authorization Final Rule](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f)
- [HL7 Da Vinci Prior Authorization Support](https://hl7.org/fhir/us/davinci-pas/)
- [HL7 Da Vinci Documentation Templates and Rules](https://hl7.org/fhir/us/davinci-dtr/)
- [HL7 Da Vinci Burden Reduction reference implementations](https://github.com/HL7-DaVinci)

## Safety

PriorPacket does not determine coverage, make treatment recommendations, guarantee approval, or submit requests to payers. It organizes administrative proof for qualified staff review.

Do not use live protected health information unless PriorPacket is deployed inside an approved environment with appropriate legal, security, access-control, and retention processes.
