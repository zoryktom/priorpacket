# EHR Integration Path

PriorPacket is designed to plug into EHR and revenue-cycle workflows without becoming a payer portal.

## Integration surfaces

### FHIR Bundle input

The current product accepts FHIR R4 Bundles. A production deployment should map EHR data into a request-scoped bundle containing:

- `Patient`
- `ServiceRequest`
- `Condition`
- `Procedure`
- `Observation`
- `MedicationRequest`
- `DocumentReference`

### FHIR Task output

PriorPacket emits a FHIR `Task`-style work item for missing-proof queues. This can support:

- Prior authorization work queues.
- Staff assignment.
- Missing-documentation follow-up.
- Audit trails.

### SMART on FHIR review app

The local review console is the first step toward a SMART on FHIR app:

- Launch in patient/request context.
- Pull scoped FHIR resources.
- Run evidence analysis inside the approved deployment.
- Display packet readiness and missing-proof actions.
- Write a `Task` or internal work item for staff follow-up.

## Near-term implementation path

1. Keep the open-source engine local and deterministic.
2. Add a small HTTP API around `analyze_request`.
3. Add SMART launch scaffolding.
4. Add customer-specific FHIR resource mapping.
5. Add work-queue export for `Task` resources.

## Positioning for EHR vendors

PriorPacket should be positioned as an evidence-completeness layer:

- It does not replace scheduling, ordering, claims, clearinghouses, or payer submission.
- It helps staff see missing proof before a request is submitted.
- It can create structured work items when proof is missing.
- It supports the industry transition toward FHIR-based prior authorization workflows.
