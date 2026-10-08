# Product Strategy

## Simple product statement

PriorPacket finds missing proof before a prior authorization request is submitted.

## Better than generic prior-auth automation

Most prior authorization tools optimize routing, payer lookup, portals, status checks, or submission. PriorPacket should own the step before submission:

- What proof does the payer policy require?
- Is that proof present in the chart?
- Where is the proof?
- What is missing?
- What should staff collect next?

## Product principles

- Make proof visible.
- Show exact missing actions.
- Keep logic inspectable.
- Run locally first.
- Use FHIR-native inputs and outputs.
- Treat AI as optional, not foundational.

## First winning workflow

MSK imaging prior authorization:

- High volume.
- Repetitive documentation requirements.
- Clear requested service codes.
- Common missing-proof patterns.
- Easy for operators to validate.

## Why a health system would care

Prior authorization staff spend time chasing notes, x-rays, treatment history, and payer-specific proof. PriorPacket gives them a packet score, evidence links, and a missing-proof checklist before submission.

## Why an EHR vendor would care

FHIR-based prior authorization APIs help identify requirements and exchange requests, but provider-side proof assembly is still hard. PriorPacket can turn request-scoped chart data into an auditable readiness packet and a FHIR `Task` when proof is missing.

## Commercial wedge

Sell the first version as:

> MSK Imaging Prior Auth Proof Audit

Pilot scope:

- One specialty.
- One CPT family.
- One payer policy pack.
- 30 days.
- Customer-controlled data.
- Human review before submission.

## What must be true to win

- Staff agree the missing-proof flags are useful.
- Batch reports reveal real rework patterns.
- Buyers can measure time saved or rework avoided.
- The tool fits existing work queues.
- Policy packs become a durable asset.
