# EHR Integration Path

PriorPacket is designed to plug into EHR and revenue-cycle workflows without becoming a payer portal.

## Integration Surfaces

### FHIR Bundle Input

The current product accepts FHIR R4 Bundles. A deployment can map EHR data into a request-scoped bundle containing:

- `Patient`
- `ServiceRequest`
- `Condition`
- `Procedure`
- `Observation`
- `MedicationRequest`
- `DocumentReference`

### FHIR Task Output

PriorPacket emits a FHIR `Task`-style work item for missing-proof queues. This can support:

- Prior authorization work queues.
- Staff assignment.
- Missing-documentation follow-up.
- Audit trails.

### SMART on FHIR Review App

The local review console is a reference surface for a future SMART on FHIR app:

- Launch in patient or request context.
- Pull scoped FHIR resources.
- Run evidence analysis inside the approved deployment.
- Display packet readiness and missing-proof actions.
- Write a `Task` or internal work item for staff follow-up.

## Implementation Path

1. Keep the engine local and deterministic.
2. Add an HTTP API around `analyze_request`.
3. Add SMART launch scaffolding.
4. Add site-specific FHIR resource mapping.
5. Add work-queue export for `Task` resources.

## Fit

PriorPacket does not replace scheduling, ordering, claims, clearinghouses, or payer submission. It helps staff see missing proof before a request is submitted and creates structured work items when proof is missing.
