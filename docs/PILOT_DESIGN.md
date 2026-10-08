# Pilot Design

## Pilot offer

Run a 30-day evidence-completeness pilot for one imaging workflow.

Recommended first workflow:

- CPT 73721, MRI lower extremity joint without contrast.
- Start with knee MRI requests from orthopedic or outpatient imaging workflows.

## Pilot promise

PriorPacket will not promise approvals. It will promise visibility:

- Which packets are evidence-complete before submission.
- Which packets are missing documentation.
- Which criteria are most commonly missing.
- Which payer/CPT combinations create the most rework.
- How much time staff spend assembling packets before and after using the tool.

## Pilot scope

In scope:

- Synthetic demo in sales process.
- De-identified or test FHIR Bundles for technical validation.
- One live specialty workflow only after BAA and security review.
- Human review before any packet leaves the customer environment.

Out of scope:

- Treatment recommendations.
- Autonomous payer submission.
- Automated appeal filing.
- Payer decisioning.
- Medication prior authorization.

## Data needed

Minimum:

- CPT or requested service code.
- ICD-10 diagnosis.
- Service request date.
- Relevant notes or document metadata.
- Prior imaging/procedure evidence.
- Prior treatment documentation if required.

Preferred:

- FHIR R4 Bundle export.
- De-identified historical cases with final authorization outcome.
- Denial reason where available.
- Time-to-complete estimate from staff.

## Success metrics

Operational metrics:

- Median staff time to assemble packet.
- Percent of requests flagged as missing evidence before submission.
- Percent of missing-evidence flags accepted by staff as valid.
- First-pass packet completeness rate.
- Number of requests needing rework after initial submission.

Revenue-cycle metrics:

- Denials due to missing prior authorization.
- Denials due to medical necessity documentation.
- Requests for additional information.
- Peer-to-peer review rate.
- Appeal rate and overturn rate.

Product metrics:

- Policy criteria matched correctly.
- Evidence false positive rate.
- Evidence false negative rate.
- Number of manual overrides.
- Time from FHIR input to evidence packet.

## Security posture for first pilots

Best first pilot:

- Run local or customer-controlled environment.
- Use de-identified historical cases first.
- Do not send PHI to third-party model APIs.
- Produce static artifacts for staff review.

Before live PHI:

- Sign BAA.
- Document data flow.
- Add access logging.
- Add retention policy.
- Add security contact.
- Add deployment guide.

## Pilot deck outline

1. The problem: prior authorization is becoming electronic, but documentation still breaks.
2. Why now: CMS-0057-F, Da Vinci CRD/DTR/PAS, payer metrics transparency.
3. Demo: one FHIR Bundle, one policy pack, one evidence packet.
4. Workflow: how staff would use it before submission.
5. Metrics: what the pilot will measure.
6. Security: local-first, no external API calls, synthetic first.
7. Commercial path: one specialty, one payer mix, one monthly price.

## Discovery questions

- Which procedures create the most prior-auth rework?
- Which payers request the most additional documentation?
- How do staff know what evidence is required today?
- Where do staff search for PT notes, imaging, labs, or prior treatments?
- How often are requests delayed because documentation is missing?
- Which EHR fields or notes are easiest to export?
- How do you measure preventable denials today?
- Who signs off that a packet is ready?
- What would make this safe enough to use on live cases?

## First 10 prospects

Prioritize:

- Independent orthopedic groups.
- Outpatient imaging centers.
- RCM consultants serving specialty practices.
- Regional health-system imaging departments.
- Prior authorization outsourcing vendors that need better evidence review.

Avoid initially:

- National payers.
- Large academic medical centers with 12-month procurement cycles.
- Medication-only prior auth teams.
- Fully outsourced RCM groups that cannot change workflow.
