# Startup Playbook

PriorPacket is built around a measurable hospital problem: avoidable prior authorization denials and documentation rework.

## Buyer

- VP Revenue Cycle
- Chief Medical Information Officer
- Director of Prior Authorization
- Director of Clinical Documentation Improvement
- Specialty service-line administrators

## Wedge

Start with one high-volume specialty where evidence rules are repetitive and painful:

- Radiology prior authorization
- Specialty drugs
- Musculoskeletal procedures
- Sleep studies
- Cardiology imaging

## Open-source core

The public project should prove technical credibility:

- FHIR evidence extraction
- Transparent rules and scoring
- Synthetic demo bundles
- Clear HTML packets
- Tests and CI

## Commercial product

Sell the parts hospitals do not want to build:

- EHR integration
- Payer policy monitoring
- Specialty policy packs
- Work queues and team assignment
- Analytics dashboards
- On-prem, VPC, and HIPAA-ready deployment support

## First pilot metric

Track one operational metric for 30 days:

`avoidable denial rate before submission = requests missing required evidence / total reviewed requests`

The product wins when that number drops and staff rework time drops with it.
