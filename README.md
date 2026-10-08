# PriorPacket

PriorPacket is a local-first prior authorization and denial-prevention engine for health systems. It takes a FHIR Bundle, a payer policy, and a requested service, then produces a defensible evidence packet: what is satisfied, what is missing, why the request is at risk, and which clinical artifacts should be collected before submission.

The open-source core is deterministic and auditable. It is designed for hospital revenue-cycle, clinical informatics, and interoperability teams that need explainable workflows around prior authorization rather than another black-box tool.

## Why this matters

Prior authorization is becoming a standards-driven interoperability problem. CMS requires impacted payers to implement and maintain FHIR APIs for prior authorization workflows, while HL7 Da Vinci CRD, DTR, and PAS define building blocks for discovering requirements, gathering documentation, and submitting requests. PriorPacket sits on the provider side: it helps teams assemble the evidence before a request becomes a denial.

## What it does today

- Reads synthetic or de-identified FHIR R4 Bundles.
- Reads payer policy packs written as portable JSON.
- Maps policy criteria to FHIR evidence from `Condition`, `Observation`, `Procedure`, `MedicationRequest`, `DocumentReference`, and `ServiceRequest`.
- Scores denial risk using transparent pathway logic.
- Flags missing documentation before submission.
- Produces JSON, Markdown, and HTML evidence packets.
- Exports a FHIR `Task` work item for missing-evidence queues.
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

## Safety

PriorPacket is not a medical device, does not make treatment recommendations, and does not determine insurance coverage. It organizes documentation against administrative payer-policy criteria for qualified staff review.

## Repository status

This is an alpha-stage developer preview. The included policy and FHIR examples are synthetic and for demonstration only.
