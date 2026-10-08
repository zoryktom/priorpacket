# PriorPacket

PriorPacket is a validated local tool for checking whether a prior authorization packet has the required proof before submission.

It takes a FHIR Bundle, a policy pack, and a requested service code, then produces:

- Readiness status.
- Proof found in FHIR resources.
- Missing proof checklist.
- Denial-risk band.
- JSON, Markdown, and HTML evidence packets.
- FHIR `Task` work item for follow-up.
- Audit manifest with SHA-256 hashes for inputs and outputs.
- Batch CSV report for multiple packets.

The open-source core is deterministic, auditable, and local-first. It makes no external API calls and the repository uses synthetic examples only.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

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

PriorPacket includes a reproducible validation suite for an MSK imaging workflow:

- Ready packet: knee MRI.
- Missing required x-ray proof.
- Missing prior treatment evidence.
- Ready packet: acute injury pathway.
- Wrong policy selected for requested service code.

Expected result:

```text
Cases: 5/5
Passed: True
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

## Evaluation Docs

- [Health-system evaluation guide](docs/HEALTH_SYSTEM_EVALUATION.md)
- [Validation guide](docs/VALIDATION.md)
- [EHR integration path](docs/EHR_INTEGRATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Policy packs](docs/POLICY_PACKS.md)
- [Security](SECURITY.md)

## Standards

- [CMS Interoperability and Prior Authorization Final Rule](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f)
- [HL7 Da Vinci Prior Authorization Support](https://hl7.org/fhir/us/davinci-pas/STU1.1/index.html)
- [HL7 Da Vinci Burden Reduction reference implementations](https://github.com/HL7-DaVinci)

## Safety

PriorPacket does not determine coverage, make treatment recommendations, guarantee approval, or submit requests to payers. It organizes administrative proof for qualified staff review.

Do not use live protected health information unless PriorPacket is deployed inside an approved environment with appropriate legal, security, access-control, and retention processes.
