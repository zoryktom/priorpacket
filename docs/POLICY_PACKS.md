# Policy Packs

Policy packs are JSON files that describe administrative evidence requirements for a requested service.

## Top-level fields

- `policy_id`: stable identifier for the policy pack.
- `payer`: payer or plan name.
- `service`: requested service metadata with `name` and supported `codes`.
- `criteria`: reusable evidence requirements.
- `pathways`: alternative ways to satisfy the policy.

## Criterion kinds

### `condition`

Matches FHIR `Condition.code`.

### `procedure`

Matches FHIR `Procedure.code`; supports `within_days`.

### `observation`

Matches FHIR `Observation.code`; optionally compares `valueQuantity.value` using `operator` and `value`.

### `document`

Searches FHIR `DocumentReference` metadata and description text for configured keywords.

### `medication`

Matches FHIR `MedicationRequest.medicationCodeableConcept`; can also use keyword matching.

## Pathways

A pathway lists the criterion IDs that must be met. PriorPacket evaluates every pathway and reports the strongest one.
