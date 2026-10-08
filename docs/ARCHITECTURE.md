# Architecture

PriorPacket uses a small deterministic agent chain. Each stage is inspectable and can be swapped later for institution-specific logic.

## Agent chain

1. **Intake agent** validates the FHIR Bundle and extracts patient-safe request metadata.
2. **Policy agent** validates the payer policy pack and service-code scope.
3. **Evidence agent** maps policy criteria to FHIR resources.
4. **Pathway agent** finds the strongest qualifying pathway.
5. **Gap agent** turns missing criteria into operational checklist items.
6. **Packet agent** renders JSON, Markdown, and HTML artifacts.

## Design principles

- Local-first processing.
- No external API calls in the open-source core.
- Deterministic output suitable for audit.
- Synthetic examples only.
- Policy packs are data, not hard-coded logic.

## Where this fits

PriorPacket is not a replacement for payer APIs or clearinghouses. It complements Da Vinci-style prior authorization workflows by helping provider teams know whether a request is evidence-complete before submission.
