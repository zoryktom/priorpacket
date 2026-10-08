# 90-Day Startup Plan

## Goal

Turn PriorPacket from an open-source demo into a pilot-ready startup wedge for radiology and MSK imaging prior authorization evidence completeness.

## Day 0-14: Credibility sprint

Product:

- Add JSON schema validation for policy packs.
- Add `priorpacket validate-policy`.
- Add `priorpacket batch-analyze` for a folder of FHIR Bundles.
- Add CSV output for evidence gaps.
- Add 5 synthetic imaging cases:
  - Ready knee MRI.
  - Missing x-ray.
  - Missing prior treatment evidence.
  - Trauma pathway.
  - Wrong CPT/policy mismatch.

Market:

- Interview 10 prior authorization specialists or RCM managers.
- Interview 3 imaging-center operators.
- Interview 3 orthopedic practice administrators.
- Ask for real de-identified denial letters and request-for-information examples.

Content:

- Publish a short technical post: "FHIR prior auth APIs do not solve evidence completeness."
- Record a 90-second demo video.
- Create a one-page PDF from the README and founder memo.

## Day 15-30: Pilot packaging

Product:

- Build a basic review UI: upload bundle + policy, get packet.
- Add policy-pack authoring guide.
- Add audit log file with inputs, policy version, criteria results, and output hashes.
- Add Dockerfile.
- Add security notes: local deployment, no external API calls, PHI handling.

Sales:

- Build a list of 100 target accounts.
- Run 50 founder-led outbound emails.
- Ask for 20-minute workflow interviews, not a product sale.
- Offer a free de-identified packet audit for 5 historical cases.

Pilot:

- Define pilot contract:
  - 30 days.
  - 1 CPT family.
  - 1 specialty workflow.
  - Customer-controlled data.
  - Weekly review.
  - Measured time savings and missing-evidence catch rate.

## Day 31-60: First pilot

Product:

- Customize one policy pack from actual customer policy.
- Add override reason capture.
- Add staff checklist export.
- Add payer/CPT/provider/site summary report.
- Add red/yellow/green dashboard.

Implementation:

- Run on de-identified cases first.
- Compare PriorPacket output to staff review.
- Tune policy pack only through reviewed configuration changes.
- Avoid using opaque model decisions in live workflow.

Sales:

- Convert first pilot to paid if they bring live workflow access.
- Ask for a narrow paid pilot: $2,500 setup + $2,000/month.
- Start 2 more parallel discovery tracks.

## Day 61-90: Repeatability

Product:

- Add a second CPT family.
- Add payer policy diff tracker.
- Add FHIR Task queue examples.
- Add SMART-on-FHIR app scaffold research notes.
- Add deployment guide for Docker and VPC.

Business:

- Package a repeatable "MSK Imaging Evidence Completeness" offer.
- Publish anonymized pilot results.
- Build RCM consultant partner channel.
- Prepare seed narrative:
  - Market is being forced to FHIR APIs.
  - Requirement lookup is not enough.
  - Evidence completeness remains manual.
  - PriorPacket creates an auditable evidence layer.

## Weekly operating cadence

Every week:

- Ship one visible GitHub improvement.
- Talk to at least 5 buyers/users.
- Convert one real payer policy into a policy pack.
- Add one synthetic case that captures a real-world failure mode.
- Write one public learning.

## Immediate issue backlog

P0:

- Policy-pack JSON schema.
- Batch analyzer.
- CSV gap export.
- Dockerfile.
- More synthetic cases.

P1:

- Review UI.
- Audit log.
- Policy pack authoring guide.
- Security and HIPAA deployment docs.
- De-identified case import template.

P2:

- SMART-on-FHIR scaffold.
- Payer policy monitor.
- Analytics dashboard.
- API server.
- Role-based work queue.

## Kill criteria

Stop or pivot if:

- 20+ buyer interviews show the problem is fully solved by their current tooling.
- Users cannot access the evidence needed from EHR exports.
- Staff do not trust pre-submission evidence checks even when transparent.
- The only buyer interest is unpaid curiosity.
- Procurement requires enterprise integrations before any narrow pilot.

## Strong signal criteria

Double down if:

- Staff say "I wish we had this yesterday."
- Teams send real denial/request-for-information examples.
- A buyer agrees to measure time or rework.
- A customer asks to add another CPT/payer policy.
- RCM consultants want to use it across clients.
