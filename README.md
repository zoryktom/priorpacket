# PriorPacket

PriorPacket finds missing proof before a prior authorization request is submitted.

It takes a FHIR Bundle, a payer policy pack, and a requested service code, then produces a defensible packet: proof found, proof missing, readiness status, denial-risk band, staff checklist, audit manifest, and FHIR `Task` work item.

The open-source core is deterministic and auditable. It is designed for hospital revenue-cycle, clinical informatics, and interoperability teams that need explainable workflows around prior authorization rather than another black-box tool.

## Why this matters

Prior authorization is becoming a standards-driven interoperability problem. CMS requires impacted payers to implement and maintain FHIR APIs for prior authorization workflows, while HL7 Da Vinci CRD, DTR, and PAS define building blocks for discovering requirements, gathering documentation, and submitting requests. PriorPacket sits on the provider side: it helps teams assemble the evidence before a request becomes a denial.

## What it does today

- Reads synthetic or de-identified FHIR R4 Bundles.
- Reads payer policy packs written as portable JSON.
- Maps policy criteria to FHIR evidence from `Condition`, `Observation`, `Procedure`, `MedicationRequest`, `DocumentReference`, and `ServiceRequest`.
- Scores denial risk using transparent pathway logic.
- Flags missing proof before submission.
- Produces JSON, Markdown, and HTML evidence packets.
- Exports a FHIR `Task` work item for missing-evidence queues.
- Generates audit manifests with input and output hashes.
- Runs a versioned product validation suite.
- Produces batch CSV reports for pilot audits.
- Includes a local browser review console.
- Runs fully local with no external API calls and no PHI leaving the environment.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
priorpacket analyze \
  --policy examples/policies/knee_mri_policy.json \
  --bundle examples/fhir/knee_mri_bundle.json \
  --service-code 73721 \
  --out demo-output
```

Open `demo-output/evidence_packet.html` in a browser.

The run also writes `demo-output/gap_task.fhir.json`, a FHIR `Task`-style work item that can feed an evidence completion queue.

## Product validation

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

The built-in validation suite covers ready packets, missing x-ray proof, missing prior treatment evidence, acute injury workflows, and wrong-policy mismatch.

## Review console

```bash
priorpacket serve
```

Open `http://127.0.0.1:8787`.

The console runs locally and loads the synthetic validation scenarios.

## Standards this tracks

- [CMS Interoperability and Prior Authorization Final Rule](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f)
- [HL7 Da Vinci Prior Authorization Support](https://hl7.org/fhir/us/davinci-pas/STU1.1/index.html)
- [HL7 Da Vinci Burden Reduction reference implementations](https://github.com/HL7-DaVinci)

## Example output

PriorPacket emits a packet with:

- Requested service and payer policy metadata.
- Patient-safe synthetic summary.
- Criteria satisfied, missing, and partially supported.
- Best qualifying pathway.
- Denial risk band.
- Missing evidence checklist.
- Draft internal appeal/evidence narrative.
- Machine-readable result JSON for downstream automation.

## Product direction

The open-source core should stay useful on its own. A commercial company can grow around:

- EHR and clearinghouse integrations.
- Payer policy monitoring.
- Specialty-specific policy libraries.
- Human-in-the-loop work queues.
- Analytics for denial leakage and avoidable resubmissions.
- On-prem or VPC deployments for health systems.

## Startup plan

The startup wedge is radiology and MSK imaging prior authorization evidence completeness. The goal is not to replace EHRs, clearinghouses, or payer portals; it is to make the packet defensible before submission.

- [Health-system evaluation guide](docs/HEALTH_SYSTEM_EVALUATION.md)
- [Validation guide](docs/VALIDATION.md)
- [EHR integration path](docs/EHR_INTEGRATION.md)
- [Product strategy](docs/PRODUCT_STRATEGY.md)
- [Founder memo](docs/FOUNDER_MEMO.md)
- [Competitive landscape](docs/COMPETITIVE_LANDSCAPE.md)
- [Pilot design](docs/PILOT_DESIGN.md)
- [90-day startup plan](docs/90_DAY_STARTUP_PLAN.md)

## Safety

PriorPacket is not a medical device, does not make treatment recommendations, and does not determine insurance coverage. It organizes documentation against administrative payer-policy criteria for qualified staff review.

## Repository status

This is an alpha-stage developer preview. The included policy and FHIR examples are synthetic and for demonstration only.
