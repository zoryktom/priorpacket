# Founder Memo

## Company thesis

PriorPacket should become the evidence-completeness layer for prior authorization.

Most prior authorization products focus on portals, routing, submission, status checks, or payer-side utilization management. PriorPacket should focus on the missing pre-submission question:

> Is this request defensible before it is sent?

The first commercial wedge is radiology and MSK imaging prior authorization, starting with MRI and CT pathways for orthopedic and outpatient imaging workflows. These cases are high-volume, policy-driven, documentation-heavy, and operationally painful when evidence is incomplete.

## Why now

CMS finalized CMS-0057-F, requiring impacted payers to maintain FHIR APIs for prior authorization and generally giving payers until January 1, 2027 for API development and enhancement requirements. The rule also requires a Prior Authorization API that can identify documentation requirements, support request/response workflows, and communicate approvals, denials, denial reasons, or requests for more information. Source: [CMS final rule fact sheet](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f).

CMS is also telling providers to participate in FHIR API testing with EHR vendors and payer partners. Source: [CMS electronic prior authorization overview](https://www.cms.gov/priorities/electronic-prior-authorization/overview).

HL7 Da Vinci PAS is designed for direct prior authorization submission from EHR systems and works with CRD and DTR so authorizations are sent when needed and contain relevant information on initial submission. Source: [HL7 Da Vinci PAS](https://hl7.org/fhir/us/davinci-pas/STU1.1/index.html).

KFF's 2026 analysis of 2025 prior authorization metrics found that insurers denied at least 1 in 8 standard requests across Medicare Advantage, Medicaid managed care, and federally facilitated ACA Marketplace plans; it also found that 67% of appealed Medicare Advantage denials were overturned. Source: [KFF prior authorization metrics analysis](https://www.kff.org/patient-consumer-protections/prior-authorization-metrics-provide-new-insights-into-insurer-practices-but-gaps-remain/).

Axios reported in August 2026 that Epic is rolling out tooling to flag when procedures require prior authorization, but that the technology does not yet automate the documentation needed to establish medical necessity or submit the information for approval. That gap is PriorPacket's opening. Source: [Axios](https://www.axios.com/2026/08/17/health-insurer-reviews-digital-fix).

## Beachhead

Start with outpatient radiology and orthopedic MSK imaging:

- MRI knee without contrast.
- MRI lumbar spine.
- CT cervical spine.
- Shoulder MRI.
- Advanced imaging after required prior treatment evidence is documented.

This beachhead is better than "all prior auth" because the policy logic is repetitive, the requested evidence is usually present somewhere in the chart, and the buyer can measure rework and preventable denials quickly.

## Ideal customer profile

Primary ICP:

- 20-300 provider orthopedic groups.
- Independent imaging centers.
- Health-system outpatient imaging departments.
- Specialty groups with centralized prior authorization teams.

Economic buyer:

- VP Revenue Cycle.
- Director of Patient Access.
- Director of Prior Authorization.
- Specialty operations leader.

Champion:

- Prior authorization manager.
- Revenue-cycle analyst.
- Clinical informatics leader.
- Imaging operations manager.

User:

- Prior authorization specialist.
- Clinical support staff.
- Referral coordinator.
- RCM analyst.

## Product positioning

One-line positioning:

> PriorPacket checks whether a prior authorization packet is evidence-complete before submission.

Short pitch:

> PriorPacket reads FHIR data, payer policy packs, and procedure codes, then produces a transparent evidence packet: criteria met, evidence found, missing documentation, risk band, and a FHIR Task for staff follow-up.

What it is:

- Evidence packet generator.
- Missing-documentation detector.
- Policy-pack engine.
- FHIR-native integration layer.
- Audit trail for why a request was considered ready or not ready.

What it is not:

- It is not a payer decision engine.
- It is not a clinical treatment recommendation system.
- It is not a portal replacement.
- It is not a claims clearinghouse.
- It is not a black-box denial predictor.

## Product surface

Open-source core:

- FHIR Bundle ingestion.
- JSON policy packs.
- Transparent criteria matching.
- Evidence packets in JSON, Markdown, and HTML.
- FHIR Task output for missing-evidence queues.
- Synthetic examples and tests.

Commercial product:

- Hosted or VPC deployment.
- Epic/Cerner/athena/eClinicalWorks data adapters.
- Payer policy monitoring and policy-pack updates.
- Specialty policy library.
- Work queue and role assignment.
- Team analytics: missing evidence by payer, provider, CPT code, and site.
- Audit log and export package for appeals and compliance review.
- Services layer for implementation, custom policy packs, and RCM optimization.

## Moat

The moat should not be "we use AI." That will be copied instantly.

The moat should be:

- A growing policy-pack library by payer, procedure, and specialty.
- De-identified evidence-gap analytics across customers.
- Implementation playbooks for specific specialties.
- FHIR-native architecture that can plug into the CMS-0057-F transition.
- Trust from being open-source, auditable, and deterministic.
- Human-reviewed policy conversion pipeline.

## Business model

Start with pilots:

- $2,500-$7,500 setup.
- $2,000-$8,000 per month for one specialty/location.
- Optional usage tier: $1-$5 per analyzed authorization packet.

Expansion:

- $25,000-$150,000 annual contract by specialty volume and sites.
- Add-on policy-pack library by payer and specialty.
- Add-on analytics module for preventable denial analysis.
- Implementation services for enterprise EHR integration.

Avoid pure per-approval pricing at first. It creates sales friction and requires attribution proof you will not have early.

## First proof points

A pilot should prove:

- Time to assemble a packet drops by at least 30%.
- Missing-documentation cases are found before submission.
- First-pass request completeness improves.
- Staff can use the packet without engineering support.
- The buyer can identify specific CPT/payer combinations causing rework.

## The next build

The product should move from demo to pilot-ready by adding:

- Policy-pack schema validation.
- CLI command to score an entire folder of FHIR Bundles.
- Evidence-gap CSV export.
- Human-readable policy-pack authoring guide.
- Five more synthetic imaging scenarios.
- A simple web UI for packet review.
- Epic App Orchard research and SMART-on-FHIR app scaffold.
- Security posture docs: PHI handling, HIPAA boundary, BAA readiness, deployment modes.
